import pytest

from egr.cells import Companies
from egr.inject import values_view
from egr.rules import check_company, check_period, tolerance


def _view(companies: Companies) -> dict[str, float]:
    return values_view(companies, {})


@pytest.mark.req("REQ-002")
def test_consistent_statements_raise_no_rule_flags(companies):
    view = _view(companies)
    for company in companies.values():
        assert check_company(company, view) == []


@pytest.mark.req("REQ-002")
@pytest.mark.parametrize(
    ("item", "factor", "rule"),
    [
        ("assets", 1000.0, "R1"),
        ("assets_current", 10.0, "R2"),
        ("liabilities_current", 10.0, "R3"),
        ("cash", 10.0, "R4"),
        ("revenue", -1.0, "R5"),
        ("gross_profit", 1000.0, "R6"),
        ("cfo", 1000.0, "R7"),
    ],
)
def test_each_identity_fires_on_its_item(companies, item, factor, rule):
    company = companies[1006]
    period = company.periods[5]
    view = _view(companies)
    cell = company.get(period, item)
    assert cell is not None
    view[cell.cell_id] = cell.value * factor
    flags = check_period(company, period, view)
    assert rule in {f.rule for f in flags}
    flagged = next(f for f in flags if f.rule == rule)
    assert cell.cell_id in flagged.cell_ids
    assert flagged.violation > 0


@pytest.mark.req("REQ-002")
def test_tolerance_absorbs_rounding(companies):
    company = companies[1006]
    period = company.periods[3]
    view = _view(companies)
    cell = company.get(period, "assets")
    assert cell is not None
    view[cell.cell_id] = cell.value + 500.0
    assert check_period(company, period, view) == []
    assert tolerance(1e9, 1e9) == pytest.approx(1e6 + 1000.0)


@pytest.mark.req("REQ-002")
def test_cash_flow_rule_uses_exchange_rate_effect(companies):
    company = companies[1007]
    period = company.periods[2]
    view = _view(companies)
    fx = company.get(period, "fx_effect")
    assert fx is not None
    view[fx.cell_id] = fx.value + 5e8
    flags = check_period(company, period, view)
    assert [f.rule for f in flags] == ["R7"]
    assert fx.cell_id in flags[0].cell_ids
