import json
from pathlib import Path

import jsonschema
import pytest

from egr.auditlog import GENESIS, AuditLog, entry_hash, verify
from egr.evidence import canonical, digest, from_rule, from_score, validate
from egr.inject import values_view
from egr.plausibility import score_company
from egr.rules import check_period


def _rule_record(companies):
    company = companies[1006]
    period = company.periods[6]
    view = values_view(companies, {})
    cell = company.get(period, "assets")
    view[cell.cell_id] = cell.value * 2
    flag = check_period(company, period, view)[0]
    return from_rule(flag, companies, view), view


@pytest.mark.req("REQ-006")
def test_rule_record_validates_and_lists_only_the_cells_of_the_identity(companies):
    record, view = _rule_record(companies)
    validate(record)
    assert record["detector"] == "rule" and record["rule"] == "R1"
    assert {s["item"] for s in record["sources"]} == {"assets", "liabilities_and_equity"}
    for s in record["sources"]:
        assert s["value"] == view[s["cell_id"]]
        assert s["accession_number"] and s["retrieved"] == "2026-11-02"
    assert set(record["computed"]) == {"difference", "tolerance"}


@pytest.mark.req("REQ-006")
def test_score_record_validates_and_sources_cover_every_candidate(companies):
    company = companies[1007]
    view = values_view(companies, {})
    scores = score_company(company, view)
    score = scores[f"1007|{company.periods[-1]}|net_income"]
    record = from_score(score, 0.01, companies, view)
    validate(record)
    assert record["flagged_cell_ids"] == [score.cell_id]
    assert {s["cell_id"] for s in record["sources"]} == {score.cell_id, *score.source_cell_ids}
    assert record["computed"]["p_value"] == 0.01
    assert any(k.startswith("candidate_") for k in record["computed"])


@pytest.mark.req("REQ-006")
def test_schema_rejects_extra_fields_and_missing_sources(companies):
    record, _ = _rule_record(companies)
    bad = dict(record)
    bad["note"] = "anything"
    with pytest.raises(jsonschema.ValidationError):
        validate(bad)
    bad = dict(record)
    bad["sources"] = []
    with pytest.raises(jsonschema.ValidationError):
        validate(bad)


def test_canonical_json_is_order_independent():
    assert canonical({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'
    assert digest({"b": 1, "a": 2}) == digest({"a": 2, "b": 1})


@pytest.mark.req("REQ-014")
def test_audit_log_chain_verifies_and_continues(tmp_path: Path):
    path = tmp_path / "log.jsonl"
    log = AuditLog(path)
    first = log.append("run_start", {"a": 1})
    assert first["prev_hash"] == GENESIS and first["seq"] == 0
    log.append("flag", {"id": "x"})
    again = AuditLog(path)
    assert again.seq == 2
    again.append("run_end", {})
    v = verify(path)
    assert v.ok and v.entries == 3
    assert verify(path, expected_entries=3).ok
    assert not verify(path, expected_entries=4).ok


@pytest.mark.req("REQ-014")
@pytest.mark.parametrize(
    "tamper",
    ["edit", "delete", "insert", "swap", "truncate", "rehash"],
)
def test_each_tampering_is_detected(tmp_path: Path, tamper: str):
    path = tmp_path / "log.jsonl"
    log = AuditLog(path)
    for i in range(5):
        log.append("flag", {"i": i})
    lines = path.read_text(encoding="utf-8").splitlines()
    if tamper == "edit":
        e = json.loads(lines[2])
        e["payload"]["i"] = 99
        lines[2] = canonical(e)
    elif tamper == "delete":
        del lines[2]
    elif tamper == "insert":
        lines.insert(2, lines[2])
    elif tamper == "swap":
        lines[1], lines[2] = lines[2], lines[1]
    elif tamper == "truncate":
        lines = lines[:-1]
    else:
        e = json.loads(lines[2])
        e["payload"]["i"] = 99
        e["hash"] = entry_hash(e)
        lines[2] = canonical(e)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = verify(path, expected_entries=5)
    assert not v.ok
    assert v.first_bad is not None
