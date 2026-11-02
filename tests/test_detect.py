import hashlib
import json
from pathlib import Path

import pytest

from egr import config
from egr.detect import calibration_scores, run, write
from egr.evidence import canonical, validate
from egr.inject import inject, values_view


@pytest.fixture(scope="module")
def result(companies):
    injection = inject(companies, 0.02, 0)
    return run(companies, injection, "test", 0, 0.02), injection


@pytest.mark.req("REQ-001")
def test_two_runs_give_identical_bytes(companies, result):
    first, injection = result
    second = run(companies, injection, "test", 0, 0.02)
    assert first.flags_json == second.flags_json
    assert [canonical(r) for r in first.evidence] == [canonical(r) for r in second.evidence]
    assert (
        first.flags_json == run(companies, inject(companies, 0.02, 0), "test", 0, 0.02).flags_json
    )


@pytest.mark.req("REQ-007")
def test_every_ranked_flag_within_the_largest_budget_has_evidence(result):
    res, _ = result
    k = (max(config.BUDGETS_PER_1000) * res.n_heldout_tested) // 1000
    cells = res.cells
    covered = {cid for r in res.evidence for cid in r["flagged_cell_ids"]}
    for col in ("rank_rules", "rank_plausibility", "rank_combined"):
        top = cells[(cells[col] > 0) & (cells[col] <= k)]
        assert set(top["cell_id"]) <= covered
    for record in res.evidence:
        validate(record)


@pytest.mark.req("REQ-005")
def test_only_heldout_cells_are_tested_and_calibration_is_development(companies, result):
    res, _ = result
    assert set(res.cells["cik"]) == {cik for cik, c in companies.items() if c.split == "heldout"}
    cal = calibration_scores(companies, values_view(companies, {}))
    assert res.calibration_n == {k: len(v) for k, v in cal.items()}
    assert all(n > 0 for n in res.calibration_n.values())


def test_injected_errors_rank_ahead_of_clean_cells(result):
    res, _ = result
    cells = res.cells
    k = (config.BUDGET_PRIMARY * len(cells)) // 1000
    top = cells[(cells["rank_combined"] > 0) & (cells["rank_combined"] <= k)]
    assert top["injected"].mean() > 10 * cells["injected"].mean()


def test_bh_flags_are_a_subset_of_scored_cells_and_nested(result):
    res, _ = result
    cells = res.cells
    assert cells.loc[cells["bh_05"], "scored"].all()
    assert set(cells.loc[cells["bh_05"], "cell_id"]) <= set(cells.loc[cells["bh_10"], "cell_id"])
    assert set(cells.loc[cells["bh_10"], "cell_id"]) <= set(cells.loc[cells["bh_20"], "cell_id"])


def test_write_round_trip(tmp_path: Path, result):
    res, _ = result
    files = write(res, tmp_path)
    flags = (tmp_path / files["flags"]).read_text(encoding="utf-8")
    assert flags == res.flags_json + "\n"
    lines = (tmp_path / files["evidence"]).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == res.evidence
    assert (
        hashlib.sha256(flags.encode()).hexdigest()
        == hashlib.sha256((res.flags_json + "\n").encode()).hexdigest()
    )
    meta = json.loads((tmp_path / "test_r00_meta.json").read_text())
    assert meta["n_heldout_tested"] == res.n_heldout_tested
