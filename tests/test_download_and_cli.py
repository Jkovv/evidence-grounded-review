import importlib.util
import io
import json
import sys
import time
from itertools import pairwise
from pathlib import Path

import pytest

from egr import config
from egr.auditlog import AuditLog
from egr.cli import main, tamper_cases

SPEC = importlib.util.spec_from_file_location(
    "download_sec", config.ROOT / "data" / "download_sec.py"
)
assert SPEC is not None and SPEC.loader is not None
download_sec = importlib.util.module_from_spec(SPEC)
sys.modules["download_sec"] = download_sec
SPEC.loader.exec_module(download_sec)


class FakeResponse(io.BytesIO):
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.req("REQ-016")
def test_requests_declare_the_user_agent_and_are_spaced(tmp_path: Path, monkeypatch):
    seen = []

    def fake_urlopen(req, timeout):
        seen.append((req.full_url, req.headers, time.monotonic()))
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(download_sec.urllib.request, "urlopen", fake_urlopen)
    dl = download_sec.Downloader(tmp_path / "raw", tmp_path / "manifest.json")
    for i in range(3):
        assert dl.fetch(f"submissions/CIK{i:010d}.json", tmp_path / "raw" / f"{i}.json")
    assert all(h["User-agent"] == config.USER_AGENT for _, h, _ in seen)
    gaps = [b[2] - a[2] for a, b in pairwise(seen)]
    assert min(gaps) >= config.MIN_REQUEST_INTERVAL * 0.95


@pytest.mark.req("REQ-017")
def test_manifest_records_checksums_and_check_finds_changes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        download_sec.urllib.request, "urlopen", lambda req, timeout: FakeResponse(b'{"a": 1}')
    )
    dl = download_sec.Downloader(tmp_path / "raw", tmp_path / "manifest.json")
    dest = tmp_path / "raw" / "x.json"
    dl.fetch("submissions/x.json", dest)
    dl.save_manifest()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["x.json"]["sha256"] == download_sec.sha256(dest)
    assert manifest["x.json"]["retrieved"][:2] == "20"
    assert dl.have(dest)
    assert download_sec.check(dl) == 0
    dest.write_text('{"a": 2}')
    assert download_sec.check(dl) == 1
    assert not dl.have(dest)


def test_universe_selection_is_reproducible(tmp_path: Path):
    frames = tmp_path / "frames"
    frames.mkdir()
    data = [{"cik": i, "val": 2e8 if i % 3 else 1e7} for i in range(1, 700)]
    for frame in (config.FRAME_EARLY, config.FRAME_LATE):
        (frames / f"Assets_{frame}.json").write_text(json.dumps({"data": data}))
    first = download_sec.select_universe(tmp_path)
    assert first == download_sec.select_universe(tmp_path)
    assert len(first) == config.N_COMPANIES
    assert all(c % 3 for c in first)


@pytest.mark.req("REQ-014")
def test_tamper_cases_are_all_detected_and_the_control_is_not(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for i in range(6):
        log.append("flag", {"i": i})
    rows = tamper_cases(path, tmp_path / "copy.jsonl")
    assert len(rows) == 7
    assert all(r["detected"] for r in rows[:-1])
    assert not rows[-1]["detected"]
    assert main(["verify-log", str(path)]) == 0


def test_cli_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for command in (
        "prepare",
        "detect",
        "determinism",
        "texts",
        "verify-log",
        "evaluate",
        "figures",
    ):
        assert command in out


@pytest.mark.req("REQ-015")
def test_run_context_records_versions_data_and_parameters():
    from egr.cli import run_context

    context = run_context()
    for key in (
        "package_version",
        "python",
        "platform",
        "git_commit",
        "data_manifest_sha256",
        "split_sha256",
    ):
        assert key in context
    parameters = context["parameters"]
    for key in ("SEED", "ERROR_RATE", "BH_TARGETS", "BUDGETS_PER_1000", "REL_TOL", "MIN_HISTORY"):
        assert key in parameters
    json.dumps(context)
