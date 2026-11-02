import numpy as np
import pandas as pd
import pytest

from egr import config
from egr.evaluate import BudgetEvaluator, Run, budget_tables, company_weights, false_flag_table


def _frame() -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(0)
    for cik in range(5):
        for i in range(400):
            rows.append(
                {
                    "cell_id": f"{cik}|{i}",
                    "cik": cik,
                    "injected": bool(rng.random() < 0.05),
                    "amended_changed": False,
                    "error_type": "",
                    "rank_rules": 0,
                    "rank_plausibility": 0,
                    "rank_combined": 0,
                    "bh_05": False,
                    "bh_10": False,
                    "bh_20": False,
                }
            )
    frame = pd.DataFrame(rows)
    frame.loc[frame["injected"], "error_type"] = "sign_flip"
    order = np.argsort(-(frame["injected"].to_numpy() + rng.random(len(frame))))
    frame.loc[order[:200], "rank_combined"] = np.arange(1, 201)
    frame.loc[order[:200], "rank_plausibility"] = np.arange(1, 201)
    frame.loc[order[:50], "rank_rules"] = np.arange(1, 51)
    frame.loc[order[:30], "bh_10"] = True
    frame.loc[order[:10], "bh_05"] = True
    frame.loc[order[:60], "bh_20"] = True
    return frame


@pytest.mark.req("REQ-020")
def test_weights_row_zero_is_the_data_and_resamples_share_companies():
    w = company_weights(5, 10, 1)
    assert w.shape == (11, 5)
    assert (w[0] == 1).all()
    assert (w[1:].sum(axis=1) == 5).all()


@pytest.mark.req("REQ-020")
def test_budget_evaluator_reproduces_a_direct_count():
    frame = _frame()
    companies = sorted(frame["cik"].unique().tolist())
    w = company_weights(len(companies), 20, 2)
    ev = BudgetEvaluator(frame, "injected", w, companies)
    res = ev.at_budget("combined", 10)
    k = (10 * len(frame)) // 1000
    top = frame[(frame["rank_combined"] > 0) & (frame["rank_combined"] <= k)]
    assert res["k"][0] == k
    assert res["caught"][0] == top["injected"].sum()
    assert res["flags"][0] == len(top)
    assert ev.n_target[0] == frame["injected"].sum()
    assert res["caught"][1:].max() >= res["caught"][0] * 0.3


def test_budget_tables_and_false_flag_table_have_every_row():
    frame = _frame()
    companies = sorted(frame["cik"].unique().tolist())
    w = company_weights(len(companies), 20, 3)
    runs = [Run("primary", 0, frame, {}), Run("primary", 1, frame, {})]
    metrics, by_type, diffs = budget_tables(runs, "injected", w, companies)
    assert len(metrics) == len(config.BUDGETS_PER_1000) * 4
    assert len(by_type) == len(config.BUDGETS_PER_1000) * 4 * len(config.ERROR_TYPES)
    nothing = metrics[metrics["detector"] == "nothing"]
    assert (nothing["recall"] == 0).all()
    assert set(diffs["comparison"]) == {
        "combined minus rules",
        "plausibility minus rules",
        "combined minus plausibility",
    }
    ffr = false_flag_table(runs, w, companies, "test")
    assert len(ffr) == len(config.BH_TARGETS) * 2
    row = ffr[(ffr["target"] == 0.1) & (ffr["detector"] == "plausibility")].iloc[0]
    flagged = frame[frame["bh_10"]]
    assert row["flags"] == len(flagged)
    assert row["achieved_false_flag_rate"] == pytest.approx(1 - flagged["injected"].mean())
