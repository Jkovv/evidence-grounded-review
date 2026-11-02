"""Download the SEC EDGAR XBRL records used here.

    python data/download_sec.py            # full universe into data/raw/
    python data/download_sec.py --quick    # the 24-company quick universe
    python data/download_sec.py --check    # compare files on disk with the manifest

Respects the SEC access policy: a declared user agent and a wait between
requests. Every file is recorded in the manifest with URL, retrieval date and
SHA-256. See data/README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if "EGR_QUICK" not in os.environ and "--quick" in sys.argv:
    os.environ["EGR_QUICK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from egr import config  # noqa: E402

RETRY_STATUSES = {429, 500, 502, 503, 504}


def sha256(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Downloader:
    """Fetches URLs with the declared user agent, a minimum spacing and retries."""

    def __init__(self, raw_dir: Path, manifest_path: Path) -> None:
        self.raw_dir = raw_dir
        self.manifest_path = manifest_path
        self.manifest: dict[str, dict[str, str]] = {}
        if manifest_path.exists():
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < config.MIN_REQUEST_INTERVAL:
            time.sleep(config.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.monotonic()

    def fetch(self, rel_url: str, dest: Path, retries: int = 6) -> bool:
        """Download rel_url (relative to the SEC base) into dest and record it.

        Returns False when the server answers 404, which happens for a few
        companies without company facts; everything else is retried and then
        raised.
        """
        url = config.SEC_BASE + "/" + rel_url.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, retries + 1):
            self._wait()
            req = urllib.request.Request(
                url, headers={"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip, deflate"}
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        import gzip

                        body = gzip.decompress(body)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return False
                if e.code in RETRY_STATUSES and attempt < retries:
                    print(f"  {rel_url}: HTTP {e.code}, retry {attempt}", file=sys.stderr)
                    time.sleep(3 * attempt)
                    continue
                raise
            except OSError as e:
                if attempt < retries:
                    print(f"  {rel_url}: {e}, retry {attempt}", file=sys.stderr)
                    time.sleep(3 * attempt)
                    continue
                raise
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(body)
            tmp.replace(dest)
            self.manifest[str(dest.relative_to(self.raw_dir)).replace("\\", "/")] = {
                "url": url,
                "retrieved": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sha256": sha256(dest),
                "bytes": str(dest.stat().st_size),
            }
            return True
        raise RuntimeError(f"gave up on {url}")

    def have(self, dest: Path) -> bool:
        """True when dest exists and matches the manifest checksum."""
        key = str(dest.relative_to(self.raw_dir)).replace("\\", "/")
        entry = self.manifest.get(key)
        return dest.exists() and entry is not None and sha256(dest) == entry["sha256"]

    def save_manifest(self) -> None:
        """Write the manifest sorted by path."""
        ordered = {k: self.manifest[k] for k in sorted(self.manifest)}
        self.manifest_path.write_text(json.dumps(ordered, indent=1) + "\n", encoding="utf-8")


def select_universe(raw_dir: Path) -> list[int]:
    """CIKs present in both frames with assets above the floor, sampled with the seed.

    The sample is drawn from the CIK-sorted candidate list with random.Random
    (a Mersenne twister with a fixed integer seed), so it is the same on every
    machine and Python version.
    """
    early = json.loads((raw_dir / "frames" / f"Assets_{config.FRAME_EARLY}.json").read_text())
    late = json.loads((raw_dir / "frames" / f"Assets_{config.FRAME_LATE}.json").read_text())
    early_vals = {d["cik"]: d["val"] for d in early["data"]}
    late_vals = {d["cik"]: d["val"] for d in late["data"]}
    candidates = sorted(
        c
        for c in early_vals
        if c in late_vals and early_vals[c] >= config.MIN_ASSETS and late_vals[c] >= config.MIN_ASSETS
    )
    rng = random.Random(config.SEED)
    return sorted(rng.sample(candidates, config.N_COMPANIES))


def cik_path(cik: int) -> str:
    """Zero padded CIK as used in SEC URLs."""
    return f"CIK{cik:010d}"


def download_all(dl: Downloader, universe_path: Path) -> None:
    """Frames, universe, then company facts and submissions for every company."""
    frames_dir = dl.raw_dir / "frames"
    for frame in (config.FRAME_EARLY, config.FRAME_LATE):
        dest = frames_dir / f"Assets_{frame}.json"
        if not dl.have(dest):
            print(f"frames {frame}")
            dl.fetch(f"api/xbrl/frames/us-gaap/Assets/USD/{frame}.json", dest)
    dl.save_manifest()
    universe = select_universe(dl.raw_dir)
    universe_path.parent.mkdir(parents=True, exist_ok=True)
    universe_path.write_text(json.dumps(universe) + "\n", encoding="utf-8")
    print(f"universe: {len(universe)} companies")
    missing: list[int] = []
    for i, cik in enumerate(universe, start=1):
        facts = dl.raw_dir / "companyfacts" / f"{cik_path(cik)}.json"
        if not dl.have(facts) and not dl.fetch(f"api/xbrl/companyfacts/{cik_path(cik)}.json", facts):
            missing.append(cik)
            continue
        subs = dl.raw_dir / "submissions" / f"{cik_path(cik)}.json"
        if not dl.have(subs):
            dl.fetch(f"submissions/{cik_path(cik)}.json", subs)
        extra: list[dict[str, Any]] = json.loads(subs.read_text(encoding="utf-8"))["filings"].get(
            "files", []
        )
        for part in extra:
            dest = dl.raw_dir / "submissions" / part["name"]
            if not dl.have(dest):
                dl.fetch(f"submissions/{part['name']}", dest)
        if i % 20 == 0 or i == len(universe):
            print(f"  {i}/{len(universe)}")
            dl.save_manifest()
    dl.save_manifest()
    if missing:
        print(f"no company facts for {len(missing)} companies: {missing}")


def check(dl: Downloader) -> int:
    """Compare the files on disk with the manifest; return the number of differences."""
    differences = 0
    for key, entry in dl.manifest.items():
        path = dl.raw_dir / key
        if not path.exists():
            print(f"missing: {key}")
            differences += 1
        elif sha256(path) != entry["sha256"]:
            print(f"changed: {key} (manifest {entry['retrieved']})")
            differences += 1
    print(f"{len(dl.manifest)} files in manifest, {differences} differences")
    return differences


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="the small universe used by CI")
    parser.add_argument("--check", action="store_true", help="compare disk with the manifest")
    parser.add_argument("--strict", action="store_true", help="with --check: differences fail")
    args = parser.parse_args()
    raw_dir = config.RAW_DIR
    dl = Downloader(raw_dir, config.MANIFEST_PATH)
    if args.check:
        differences = check(dl)
        return 1 if args.strict and differences else 0
    download_all(dl, config.PROCESSED_DIR / "universe.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
