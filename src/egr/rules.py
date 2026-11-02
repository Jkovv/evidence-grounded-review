"""Accounting identity rules (layer 1), following docs/analysis_plan.md.

Each rule looks at the values of one company-period and returns a flag with
the cells that entered it and the computed quantities, or nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from egr import config
from egr.cells import Company

Values = dict[str, float]


@dataclass
class RuleFlag:
    """One violated identity in one company-period."""

    rule: str
    cik: int
    period_end: str
    cell_ids: list[str]
    computed: dict[str, float] = field(default_factory=dict)
    violation: float = 0.0  # relative size used to order rule flags under a budget


def tolerance(
    a: float, b: float, rel: float = config.REL_TOL, abs_tol: float = config.ABS_TOL
) -> float:
    """Tolerance for an equality between a and b."""
    return rel * max(abs(a), abs(b)) + abs_tol


def _ids(company: Company, period_end: str, *items: str) -> list[str]:
    return [f"{company.cik}|{period_end}|{item}" for item in items]


def _get(view: Values, company: Company, period_end: str, item: str) -> float | None:
    cell = company.get(period_end, item)
    return None if cell is None else view[cell.cell_id]


def check_period(company: Company, period_end: str, view: Values) -> list[RuleFlag]:
    """All rule flags of one company-period."""
    flags: list[RuleFlag] = []

    def v(item: str) -> float | None:
        return _get(view, company, period_end, item)

    def flag(rule: str, items: list[str], computed: dict[str, float], violation: float) -> None:
        flags.append(
            RuleFlag(
                rule,
                company.cik,
                period_end,
                _ids(company, period_end, *items),
                computed,
                violation,
            )
        )

    assets, lse = v("assets"), v("liabilities_and_equity")
    if assets is not None and lse is not None:
        diff = assets - lse
        tol = tolerance(assets, lse)
        if abs(diff) > tol:
            flag(
                "R1",
                ["assets", "liabilities_and_equity"],
                {"difference": diff, "tolerance": tol},
                abs(diff) / max(abs(assets), abs(lse), 1.0),
            )
    current_assets = v("assets_current")
    if assets is not None and current_assets is not None:
        excess = current_assets - assets
        tol = tolerance(assets, current_assets)
        if excess > tol:
            flag(
                "R2",
                ["assets_current", "assets"],
                {"excess": excess, "tolerance": tol},
                excess / max(abs(assets), 1.0),
            )
    liabilities, current_liabilities = v("liabilities"), v("liabilities_current")
    if liabilities is not None and current_liabilities is not None:
        excess = current_liabilities - liabilities
        tol = tolerance(liabilities, current_liabilities)
        if excess > tol:
            flag(
                "R3",
                ["liabilities_current", "liabilities"],
                {"excess": excess, "tolerance": tol},
                excess / max(abs(liabilities), 1.0),
            )
    cash = v("cash")
    if cash is not None and current_assets is not None:
        excess = cash - current_assets
        tol = tolerance(cash, current_assets)
        if excess > tol:
            flag(
                "R4",
                ["cash", "assets_current"],
                {"excess": excess, "tolerance": tol},
                excess / max(abs(current_assets), 1.0),
            )
    for item in config.ITEMS:
        if not item.nonnegative:
            continue
        value = v(item.key)
        if value is not None and value < 0:
            # a negative value where none is allowed is a full violation; ties are
            # broken by the absolute value when rule flags are cut to a budget
            flag("R5", [item.key], {"value": value}, 1.0 + min(abs(value) / 1e15, 0.999))
    revenue, cost, gross = v("revenue"), v("cost_of_revenue"), v("gross_profit")
    if revenue is not None and cost is not None and gross is not None:
        implied = revenue - cost
        diff = gross - implied
        tol = tolerance(gross, implied)
        if abs(diff) > tol:
            flag(
                "R6",
                ["gross_profit", "revenue", "cost_of_revenue"],
                {"implied_gross_profit": implied, "difference": diff, "tolerance": tol},
                abs(diff) / max(abs(revenue), 1.0),
            )
    cfo, cfi, cff, change = v("cfo"), v("cfi"), v("cff"), v("cash_change")
    if cfo is not None and cfi is not None and cff is not None and change is not None:
        fx = v("fx_effect")
        total = cfo + cfi + cff + (fx or 0.0)
        diff = change - total
        largest = max(abs(cfo), abs(cfi), abs(cff), abs(change), abs(fx or 0.0))
        tol = config.CASHFLOW_REL_TOL * largest + config.ABS_TOL
        if abs(diff) > tol:
            items = ["cash_change", "cfo", "cfi", "cff"] + (["fx_effect"] if fx is not None else [])
            flag(
                "R7",
                items,
                {"sum_of_components": total, "difference": diff, "tolerance": tol},
                abs(diff) / max(largest, 1.0),
            )
    return flags


def check_company(company: Company, view: Values) -> list[RuleFlag]:
    """Rule flags of every period of a company, in period order."""
    return [f for p in company.periods for f in check_period(company, p, view)]
