import pytest

from egr import config
from egr.prepare import (
    choose_element,
    company_cells,
    differs,
    filings_by_accn,
    filings_of_record,
    make_split,
    pick_fact,
)


def _fact(end, val, accn, form, filed, start=None):
    f = {"end": end, "val": val, "accn": accn, "form": form, "filed": filed}
    if start:
        f["start"] = start
    return f


@pytest.fixture
def facts():
    a1, a2, am = "0000000001-20-000001", "0000000001-20-000002", "0000000001-20-000009"
    return {
        "entityName": "Test Co",
        "us-gaap": {
            "Assets": {
                "units": {
                    "USD": [
                        _fact("2020-03-31", 100e6, a1, "10-Q", "2020-05-01"),
                        _fact("2020-06-30", 110.0, a2, "10-Q", "2020-08-01"),
                        _fact("2020-03-31", 101e6, a2, "10-Q", "2020-08-01"),
                        _fact("2020-03-31", 150e6, am, "10-Q/A", "2020-09-01"),
                    ]
                }
            },
            "LiabilitiesAndStockholdersEquity": {
                "units": {
                    "USD": [
                        _fact("2020-03-31", 100e6, a1, "10-Q", "2020-05-01"),
                        _fact("2020-06-30", 110.0, a2, "10-Q", "2020-08-01"),
                    ]
                }
            },
            "Revenues": {
                "units": {
                    "USD": [
                        _fact("2020-03-31", 10.0, a1, "10-Q", "2020-05-01", "2020-01-01"),
                        _fact("2020-06-30", 12.0, a2, "10-Q", "2020-08-01", "2020-04-01"),
                        _fact("2020-06-30", 22.0, a2, "10-Q", "2020-08-01", "2020-01-01"),
                    ]
                }
            },
            "SalesRevenueNet": {
                "units": {
                    "USD": [
                        _fact("2020-03-31", 10.0, a1, "10-Q", "2020-05-01", "2020-01-01"),
                    ]
                }
            },
        },
    }


@pytest.mark.req("REQ-018")
def test_filing_of_record_is_the_earliest_original_with_that_period_end(facts):
    filings = filings_by_accn(facts)
    assert filings["0000000001-20-000002"].own_end == "2020-06-30"
    record = filings_of_record(filings)
    assert record["2020-03-31"].accn == "0000000001-20-000001"
    assert set(record) == {"2020-03-31", "2020-06-30"}


def test_longest_duration_in_the_filing_is_the_year_to_date_value(facts):
    revs = facts["us-gaap"]["Revenues"]["units"]["USD"]
    chosen = pick_fact(
        [f for f in revs if f["accn"] == "0000000001-20-000002"], "2020-06-30", False
    )
    assert chosen is not None and chosen["val"] == 22.0
    assert pick_fact(revs, "2020-06-30", True) is None


def test_element_with_most_original_facts_is_chosen(facts):
    assert choose_element(facts, config.ITEM_BY_KEY["revenue"]) == "Revenues"
    assert choose_element(facts, config.ITEM_BY_KEY["capex"]) is None


def test_amended_value_labels_the_as_reported_cell(facts):
    rows, elements = company_cells(1, facts)
    assets = {r["period_end"]: r for r in rows if r["item"] == "assets"}
    assert assets["2020-03-31"]["value"] == 100e6
    assert assets["2020-03-31"]["amended_changed"] is True
    assert assets["2020-03-31"]["amended_value"] == 150e6
    assert assets["2020-03-31"]["revised_later"] is True
    assert assets["2020-06-30"]["amended_changed"] is False
    revenue = {r["period_end"]: r for r in rows if r["item"] == "revenue"}
    assert revenue["2020-06-30"]["value"] == 22.0 and revenue["2020-06-30"]["ytd_months"] == 6
    assert elements["revenue"] == "Revenues"


def test_differs_thresholds():
    assert not differs(1_000_000.0, 1_000_500.0)
    assert not differs(10_000_000_000.0, 10_005_000_000.0)
    assert differs(1_000_000.0, 1_100_000.0)


@pytest.mark.req("REQ-018")
def test_split_is_half_and_reproducible():
    ciks = list(range(1, 101))
    split = make_split(ciks)
    assert sum(1 for s in split.values() if s == "development") == 50
    assert split == make_split(list(reversed(ciks)))
