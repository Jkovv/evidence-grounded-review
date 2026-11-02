import pytest

from egr.inject import values_view
from egr.plausibility import median, round_sig, score_company


def test_median_odd_and_even():
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([4.0, 1.0, 3.0, 2.0]) == 2.5


def test_round_sig_is_stable():
    assert round_sig(1.23456789012345) == 1.23456789
    assert round_sig(0.0) == 0.0
    assert round_sig(123456789012.0) == 123456789000.0


@pytest.mark.req("REQ-003")
def test_clean_history_gives_small_scores(companies):
    company = companies[1008]
    scores = score_company(company, values_view(companies, {}))
    late = [s.score for s in scores.values() if s.cell_id.split("|")[1] >= "2014-01-01"]
    assert late
    assert sorted(late)[len(late) // 2] < 5


@pytest.mark.req("REQ-003")
def test_scale_slip_gets_a_large_score(companies):
    company = companies[1008]
    view = values_view(companies, {})
    cell = company.get("2015-06-30", "net_income")
    assert cell is not None
    base = score_company(company, view)[cell.cell_id].score
    view[cell.cell_id] = cell.value * 1000
    slipped = score_company(company, view)[cell.cell_id]
    assert slipped.score > 100 * max(base, 1.0)
    assert cell.cell_id not in slipped.source_cell_ids
    assert slipped.candidates


@pytest.mark.req("REQ-003")
def test_score_depends_only_on_earlier_periods_and_the_same_period(companies):
    company = companies[1009]
    view = values_view(companies, {})
    before = score_company(company, view)
    later = company.get("2016-12-31", "assets")
    assert later is not None
    view[later.cell_id] = later.value * 50
    after = score_company(company, view)
    for cid, s in before.items():
        if cid.split("|")[1] < "2016-12-31":
            assert after[cid].score == s.score


@pytest.mark.req("REQ-003")
def test_sources_are_earlier_or_same_period(companies):
    company = companies[1010]
    scores = score_company(company, values_view(companies, {}))
    for s in scores.values():
        period = s.cell_id.split("|")[1]
        for src in s.source_cell_ids:
            assert src.split("|")[1] <= period
