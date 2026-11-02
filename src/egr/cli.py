"""Command line entry point: python -m egr.cli <command> or egr <command>."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

import egr
from egr import config
from egr.auditlog import AuditLog, verify
from egr.cells import Companies, load_companies
from egr.detect import RunResult, calibration_scores, run, write
from egr.evidence import Evidence, canonical, digest
from egr.inject import Injection, inject, shortfall, values_view

LOG_PATH = config.AUDIT_DIR / "audit.jsonl"


def sha256_file(path: Path) -> str:
    """SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    """The current commit, or unknown outside a repository."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=config.ROOT,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def retrieval_date() -> str:
    """The latest retrieval date in the data manifest."""
    if not config.MANIFEST_PATH.exists():
        return ""
    manifest = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    return max((e["retrieved"][:10] for e in manifest.values()), default="")


def run_context() -> dict[str, Any]:
    """Versions, platform, data and parameters, written at the start of every run."""
    manifest_hash = sha256_file(config.MANIFEST_PATH) if config.MANIFEST_PATH.exists() else ""
    split_path = config.PROCESSED_DIR / "companies.parquet"
    split_hash = sha256_file(split_path) if split_path.exists() else ""
    parameters = {
        k: v
        for k, v in vars(config).items()
        if k.isupper()
        and (
            isinstance(v, (int, float, str))
            or (isinstance(v, tuple) and all(isinstance(x, (int, float, str)) for x in v))
        )
    }
    return {
        "package_version": egr.__version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_commit": git_commit(),
        "quick": config.QUICK,
        "data_manifest_sha256": manifest_hash,
        "split_sha256": split_hash,
        "parameters": parameters,
    }


def load() -> Companies:
    """The prepared cells with the retrieval date attached to every source."""
    return load_companies(config.PROCESSED_DIR / "cells.parquet", retrieved=retrieval_date())


def cmd_prepare(_: argparse.Namespace) -> int:
    """Build the cell table, labels and split."""
    from egr.prepare import prepare

    summary = prepare()
    print(json.dumps(summary, indent=1))
    return 0


def _log_run(log: AuditLog, result: RunResult, files: dict[str, str], injection: Injection) -> None:
    out = config.CELLS_DIR
    log.append(
        "run_start",
        {
            "tag": result.tag,
            "replicate": result.replicate,
            "rate": result.rate,
            "injected_cells": len(injection),
            **run_context(),
        },
    )
    for record in result.evidence:
        log.append(
            "flag",
            {
                "flag_id": record["flag_id"],
                "detector": record["detector"],
                "rule": record["rule"],
                "cells": record["flagged_cell_ids"],
                "evidence_sha256": digest(record),
            },
        )
    log.append(
        "run_end",
        {
            "tag": result.tag,
            "replicate": result.replicate,
            "flags": len(result.evidence),
            "heldout_tested": result.n_heldout_tested,
            "timings": result.timings,
            "outputs": {name: sha256_file(out / f) for name, f in files.items()},
        },
    )


def cmd_detect(args: argparse.Namespace) -> int:
    """Clean run, primary replicates, sensitivity rates, pre-specified calibration variant."""
    companies = load()
    log = AuditLog(LOG_PATH)
    config.CELLS_DIR.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    clean_cal = calibration_scores(companies, values_view(companies, {}))
    print(f"clean calibration scores in {time.perf_counter() - t:.0f} s")
    jobs: list[tuple[str, float, int]] = [("clean", 0.0, 0)]
    jobs += [("primary", config.ERROR_RATE, r) for r in range(config.N_REPLICATES)]
    for rate in config.ERROR_RATES_SENSITIVITY:
        jobs += [(f"sens{rate}", rate, r) for r in range(config.N_REPLICATES)]
    jobs.append(("primary-injectedcal", config.ERROR_RATE, 0))
    if args.only:
        jobs = [j for j in jobs if j[0] in args.only.split(",")]
    n_tested = sum(
        1
        for c in companies.values()
        for p in c.periods
        for cell in c.cells[p].values()
        if cell.tested and not cell.amended_changed
    )
    shortfalls = []
    for tag, rate, replicate in jobs:
        t = time.perf_counter()
        injection = inject(companies, rate, replicate) if rate > 0 else {}
        if rate > 0:
            shortfalls.append(
                {"tag": tag, "replicate": replicate, **shortfall(injection, n_tested, rate)}
            )
        calibration = clean_cal
        if tag == "primary-injectedcal":
            calibration = calibration_scores(companies, values_view(companies, injection))
        result = run(companies, injection, tag, replicate, rate, calibration_from=calibration)
        files = write(result, config.CELLS_DIR)
        _log_run(log, result, files, injection)
        print(
            f"{tag} r{replicate:02d}: {len(result.evidence)} evidence records, "
            f"{time.perf_counter() - t:.0f} s"
        )
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(shortfalls).to_csv(config.TABLES_DIR / "injection_shortfall.csv", index=False)
    return 0


def cmd_determinism(args: argparse.Namespace) -> int:
    """Run the primary replicate twice and compare the output bytes; record the hashes."""
    companies = load()
    clean_cal = calibration_scores(companies, values_view(companies, {}))
    injection = inject(companies, config.ERROR_RATE, 0)
    hashes = []
    for attempt in range(2):
        result = run(companies, injection, "determinism", attempt, config.ERROR_RATE, clean_cal)
        flags = hashlib.sha256((result.flags_json + "\n").encode("utf-8")).hexdigest()
        evidence = hashlib.sha256(
            "".join(canonical(r) + "\n" for r in result.evidence).encode("utf-8")
        ).hexdigest()
        hashes.append({"attempt": attempt, "flags_sha256": flags, "evidence_sha256": evidence})
    same = hashes[0]["flags_sha256"] == hashes[1]["flags_sha256"] and (
        hashes[0]["evidence_sha256"] == hashes[1]["evidence_sha256"]
    )
    record = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "quick": config.QUICK,
        "data_manifest_sha256": sha256_file(config.MANIFEST_PATH)
        if config.MANIFEST_PATH.exists()
        else "",
        "two_runs_identical": same,
        **hashes[0],
    }
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    path = config.TABLES_DIR / "determinism.csv"
    frame = pd.DataFrame([record])
    if path.exists() and not args.reset:
        frame = pd.concat([pd.read_csv(path), frame], ignore_index=True)
    frame.to_csv(path, index=False)
    print(json.dumps(record, indent=1))
    if args.expect and args.expect != record["flags_sha256"]:
        print(f"flags hash differs from the expected {args.expect}", file=sys.stderr)
        return 1
    return 0 if same else 1


def cmd_texts(_: argparse.Namespace) -> int:
    """Template and language-model texts for a sample of primary flags, with the checker."""
    from egr.llm import make_backend
    from egr.texts import generate_all, select_flags, summarise, write_rows

    companies = load()
    injection = inject(companies, config.ERROR_RATE, 0)
    view = values_view(companies, injection)
    stem = config.CELLS_DIR / "primary_r00"
    cells = pd.read_parquet(f"{stem}_cells.parquet")
    evidence: list[Evidence] = [
        json.loads(line)
        for line in Path(f"{stem}_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    flags = select_flags(cells, evidence, config.N_TEXT_FLAGS)
    backend = make_backend()
    log = AuditLog(LOG_PATH)
    log.append(
        "texts_start",
        {
            "flags": len(flags),
            "backend": backend.name if backend else "none",
            "model": backend.model if backend else "",
            **run_context(),
        },
    )
    t = time.perf_counter()
    rows = generate_all(flags, companies, view, backend, log)
    summary = summarise(rows)
    config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(config.TABLES_DIR / "faithfulness.csv", index=False)
    write_rows(rows, config.CELLS_DIR / "texts.jsonl")
    examples = [r for r in rows if r.variant != "template" and r.accepted][: config.N_TEXT_EXAMPLES]
    by_flag = {record["flag_id"]: record for _, record in flags}
    with open(config.RESULTS_DIR / "text_examples.md", "w", encoding="utf-8", newline="\n") as f:
        f.write("# Accepted language-model texts with their evidence records\n\n")
        f.write(f"{len(examples)} texts, read in order of the combined ranking.\n\n")
        for i, r in enumerate(examples, start=1):
            f.write(f"## {i}. {r.flag_id} ({r.variant}, {r.model})\n\n{r.text}\n\n")
            f.write("```json\n" + json.dumps(by_flag[r.flag_id], indent=1) + "\n```\n\n")
    log.append(
        "texts_end",
        {
            "rows": len(rows),
            "seconds": time.perf_counter() - t,
            "summary": json.loads(summary.to_json(orient="records")),
        },
    )
    print(summary.to_string())
    return 0


def tamper_cases(original: Path, work: Path) -> list[dict[str, Any]]:
    """Apply each documented tampering to a copy of the log and verify it."""
    lines = original.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    if n < 4:
        raise ValueError("log too short for the tampering cases")
    cases: list[tuple[str, list[str]]] = []
    edited = json.loads(lines[1])
    edited["payload"]["tampered"] = True
    cases.append(("edit a payload field", [lines[0], canonical(edited), *lines[2:]]))
    cases.append(("delete an entry", [lines[0], *lines[2:]]))
    forged = json.loads(lines[1])
    forged["seq"] = 2
    cases.append(("insert an entry", [lines[0], lines[1], canonical(forged), *lines[2:]]))
    cases.append(("swap two entries", [lines[0], lines[2], lines[1], *lines[3:]]))
    cases.append(("truncate the tail", lines[: n - 1]))
    rehashed = json.loads(lines[1])
    rehashed["payload"]["tampered"] = True
    from egr.auditlog import entry_hash

    rehashed["hash"] = entry_hash(rehashed)
    cases.append(("edit and recompute one hash", [lines[0], canonical(rehashed), *lines[2:]]))
    results = []
    for name, content in cases:
        work.write_text("\n".join(content) + "\n", encoding="utf-8")
        v = verify(work, expected_entries=n)
        results.append(
            {
                "tampering": name,
                "detected": not v.ok,
                "first_bad_entry": v.first_bad,
                "reason": v.reason,
            }
        )
    work.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = verify(work, expected_entries=n)
    results.append(
        {
            "tampering": "none (control)",
            "detected": not v.ok,
            "first_bad_entry": v.first_bad,
            "reason": v.reason,
        }
    )
    return results


def cmd_verify_log(args: argparse.Namespace) -> int:
    """Verify the chain of an audit log; with --tamper, run the tampering cases too."""
    path = Path(args.path) if args.path else LOG_PATH
    v = verify(path)
    print(v)
    if args.tamper:
        work = path.with_name("audit_tamper_copy.jsonl")
        rows = tamper_cases(path, work)
        work.unlink(missing_ok=True)
        frame = pd.DataFrame(rows)
        config.TABLES_DIR.mkdir(parents=True, exist_ok=True)
        frame.to_csv(config.TABLES_DIR / "audit_tamper.csv", index=False)
        print(frame.to_string())
        head = path.read_text(encoding="utf-8").splitlines()[:20]
        (config.RESULTS_DIR / "audit_log_head.jsonl").write_text(
            "\n".join(head) + "\n", encoding="utf-8", newline="\n"
        )
        return (
            0
            if v.ok and frame["detected"].iloc[:-1].all() and not frame["detected"].iloc[-1]
            else 1
        )
    return 0 if v.ok else 1


def cmd_evaluate(_: argparse.Namespace) -> int:
    """Tables and summary on held-out companies."""
    from egr.evaluate import evaluate

    summary = evaluate()
    log = AuditLog(LOG_PATH)
    log.append(
        "evaluate",
        {"summary_sha256": sha256_file(config.RESULTS_DIR / "summary.json"), **run_context()},
    )
    print(json.dumps(summary["primary"], indent=1))
    return 0


def cmd_figures(_: argparse.Namespace) -> int:
    """Figures from the tables."""
    from egr.figures import make_figures

    for path in make_figures():
        print(path)
    return 0


def cmd_clean_quick(_: argparse.Namespace) -> int:
    """Remove the quick-mode outputs."""
    for d in (config.ROOT / "results-quick", config.DATA_DIR / "processed-quick"):
        shutil.rmtree(d, ignore_errors=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch."""
    parser = argparse.ArgumentParser(prog="egr", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="build the cell table, labels and split").set_defaults(
        func=cmd_prepare
    )
    p = sub.add_parser("detect", help="run every detection job")
    p.add_argument("--only", default="", help="comma separated tags to run")
    p.set_defaults(func=cmd_detect)
    p = sub.add_parser("determinism", help="run the primary replicate twice and compare")
    p.add_argument("--expect", default="", help="flags hash the run must reproduce")
    p.add_argument("--reset", action="store_true", help="start a new determinism table")
    p.set_defaults(func=cmd_determinism)
    sub.add_parser("texts", help="query texts and the faithfulness check").set_defaults(
        func=cmd_texts
    )
    p = sub.add_parser("verify-log", help="verify the audit log chain")
    p.add_argument("path", nargs="?", default="")
    p.add_argument("--tamper", action="store_true", help="also run the tampering cases")
    p.set_defaults(func=cmd_verify_log)
    sub.add_parser("evaluate", help="tables and summary").set_defaults(func=cmd_evaluate)
    sub.add_parser("figures", help="figures from the tables").set_defaults(func=cmd_figures)
    sub.add_parser("clean-quick", help="remove quick-mode outputs").set_defaults(
        func=cmd_clean_quick
    )
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
