"""Append-only, hash-chained audit log.

Each line of the log is a JSON object with a sequence number, a UTC timestamp,
a type, a payload, the hash of the previous entry and its own hash. The hash
covers everything but itself, so an edit, deletion, insertion, swap or
truncation after the fact changes the chain and is found by verify().
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from egr.evidence import canonical

GENESIS = "0" * 64


def entry_hash(entry: dict[str, Any]) -> str:
    """SHA-256 of the canonical entry without its own hash field."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


class AuditLog:
    """Writer that appends entries to a JSON lines file, continuing an existing chain."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.seq = 0
        self.prev_hash = GENESIS
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    last = json.loads(line)
                    self.seq = int(last["seq"]) + 1
                    self.prev_hash = str(last["hash"])

    def append(self, entry_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one entry and return it."""
        entry: dict[str, Any] = {
            "seq": self.seq,
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "type": entry_type,
            "payload": payload,
            "prev_hash": self.prev_hash,
        }
        entry["hash"] = entry_hash(entry)
        line = canonical(entry) + "\n"
        for attempt in range(20):
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
                break
            except PermissionError:
                # a file synchroniser or virus scanner can hold the file for a moment
                if attempt == 19:
                    raise
                time.sleep(0.5)
        self.seq += 1
        self.prev_hash = entry["hash"]
        return entry


@dataclass
class Verification:
    """Outcome of verifying a log file."""

    ok: bool
    entries: int
    first_bad: int | None = None
    reason: str = ""

    def __str__(self) -> str:
        if self.ok:
            return f"ok: {self.entries} entries, chain intact"
        return f"BROKEN at entry {self.first_bad}: {self.reason} ({self.entries} entries read)"


def verify(path: Path, expected_entries: int | None = None) -> Verification:
    """Recompute the chain and report the first entry that does not fit.

    Truncation of the tail cannot be seen from the file alone; pass the number
    of entries the run reported at its end (recorded elsewhere, for example in
    the results summary) to detect it.
    """
    prev = GENESIS
    n = 0
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            return Verification(False, n, index, f"not valid json: {e}")
        if entry.get("seq") != n:
            return Verification(
                False, n, index, f"sequence number {entry.get('seq')} where {n} was expected"
            )
        if entry.get("prev_hash") != prev:
            return Verification(False, n, index, "previous hash does not match the preceding entry")
        if entry_hash(entry) != entry.get("hash"):
            return Verification(False, n, index, "entry hash does not match its content")
        prev = str(entry["hash"])
        n += 1
    if expected_entries is not None and n != expected_entries:
        return Verification(False, n, n, f"{n} entries found, {expected_entries} expected")
    return Verification(True, n)
