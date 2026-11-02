from pathlib import Path

import pandas as pd
import pytest

from egr import config
from egr.auditlog import AuditLog, verify
from egr.detect import run
from egr.evidence import canonical
from egr.inject import inject, values_view
from egr.llm import Generation, OpenAICompatibleBackend, evidence_prompt, make_backend, raw_prompt
from egr.texts import generate_all, raw_table, select_flags, summarise


class FakeBackend:
    name = "fake"
    model = "fake-1"

    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> Generation:
        self.prompts.append((system, user))
        return Generation(self.text, self.model, self.name, "h", "{}")


@pytest.fixture(scope="module")
def run_result(companies):
    injection = inject(companies, 0.02, 0)
    return run(companies, injection, "t", 0, 0.02), values_view(companies, injection)


@pytest.mark.req("REQ-013")
def test_flags_are_selected_from_the_ranking_and_the_model_only_sees_the_record(
    companies, run_result, tmp_path: Path
):
    res, view = run_result
    flags = select_flags(res.cells, res.evidence, 5)
    assert len(flags) == 5
    k = (config.BUDGET_PRIMARY * len(res.cells)) // 1000
    ranks = res.cells.set_index("cell_id")["rank_combined"]
    assert all(0 < ranks[cid] <= k for cid, _ in flags)
    backend = FakeBackend("We refer to the filing.")
    log = AuditLog(tmp_path / "log.jsonl")
    rows = generate_all(flags, companies, view, backend, log)
    assert len(rows) == 15
    evidence_prompts = backend.prompts[0::2]
    for (system, user), (_, record) in zip(evidence_prompts, flags, strict=True):
        assert user == "Evidence record:\n" + canonical(record)
        assert "flag" not in system.lower().replace("flagged", "")
    assert verify(tmp_path / "log.jsonl").ok


@pytest.mark.req("REQ-012")
def test_rejected_model_text_falls_back_to_the_template(companies, run_result, tmp_path: Path):
    res, view = run_result
    flags = select_flags(res.cells, res.evidence, 3)
    backend = FakeBackend("Net income of $99,999,999 was reported on January 1, 1990.")
    log = AuditLog(tmp_path / "log.jsonl")
    rows = generate_all(flags, companies, view, backend, log)
    model_rows = [r for r in rows if r.variant != "template"]
    assert model_rows and all(not r.accepted for r in model_rows)
    templates = {r.flag_id: r.text for r in rows if r.variant == "template"}
    assert all(r.final_text == templates[r.flag_id] for r in model_rows)
    summary = summarise(rows)
    assert summary.loc[summary["variant"] == "llm_evidence", "rejection_rate"].iloc[0] == 1.0
    log_text = (tmp_path / "log.jsonl").read_text(encoding="utf-8")
    assert '"type":"rejection"' in log_text


def test_summary_without_a_backend(companies, run_result, tmp_path: Path):
    res, view = run_result
    flags = select_flags(res.cells, res.evidence, 3)
    rows = generate_all(flags, companies, view, None, AuditLog(tmp_path / "log.jsonl"))
    summary = summarise(rows)
    assert list(summary["variant"]) == ["template", "llm_evidence", "llm_raw"]
    assert summary.loc[summary["variant"] == "template", "claims_verified_share"].iloc[0] == 1.0
    assert not summary.loc[summary["variant"] == "llm_raw", "run"].iloc[0]


def test_raw_prompt_lists_periods_and_items(companies, run_result):
    res, view = run_result
    flags = select_flags(res.cells, res.evidence, 1)
    cid, record = flags[0]
    table = raw_table(companies, cid, view)
    assert 1 <= len(table) <= config.RAW_CONTEXT_PERIODS + 1
    _, user = raw_prompt(record, table)
    assert "Flagged item" in user and "accession number" in user
    assert evidence_prompt(record)[1].startswith("Evidence record:")


def test_unreachable_server_is_an_error_not_an_exception():
    backend = OpenAICompatibleBackend("qwen3:0b", base_url="http://127.0.0.1:9/v1")
    gen = backend.generate("s", "u")
    assert gen.text == "" and gen.error
    assert make_backend("", "") is None


def test_summarise_frame_columns(companies, run_result, tmp_path: Path):
    res, view = run_result
    flags = select_flags(res.cells, res.evidence, 2)
    rows = generate_all(flags, companies, view, FakeBackend("x"), AuditLog(tmp_path / "l.jsonl"))
    frame = summarise(rows)
    assert isinstance(frame, pd.DataFrame) and "rejection_rate" in frame
