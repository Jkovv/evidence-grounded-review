"""Synthetic companies with consistent statements, for tests that need no SEC data."""

from __future__ import annotations

import random
from datetime import date

import pytest

from egr import config
from egr.cells import Cell, Companies, Company, Source

QUARTER_ENDS = ("03-31", "06-30", "09-30", "12-31")


def make_company(cik: int, split: str, n_years: int = 8, seed: int = 0, name: str = "") -> Company:
    """A company whose balance sheet, income statement and cash flows tie out."""
    rng = random.Random(seed + cik)
    company = Company(cik, name or f"Company {cik}", split)
    assets = 1_000_000_000.0 * (1 + rng.random())
    cash = 0.1 * assets
    annual_revenue = 0.8 * assets
    for year in range(2010, 2010 + n_years):
        fy_start = f"{year}-01-01"
        ytd_rev = 0.0
        ytd_cfo = ytd_cfi = ytd_cff = 0.0
        for q, end in enumerate(QUARTER_ENDS, start=1):
            period_end = f"{year}-{end}"
            growth = 1 + rng.uniform(-0.02, 0.04)
            assets = round(assets * growth)
            liabilities = round(0.55 * assets)
            equity = assets - liabilities
            current_assets = round(0.35 * assets)
            current_liabilities = round(0.25 * assets)
            quarter_rev = round(annual_revenue / 4 * (1 + 0.1 * (q == 4)) * growth)
            ytd_rev += quarter_rev
            cost = round(0.6 * ytd_rev)
            gross = ytd_rev - cost
            operating = round(0.5 * gross)
            tax = round(0.21 * operating)
            net = operating - tax
            cfo_q = round(net / q * 1.1)
            cfi_q = -round(0.05 * assets / 4)
            cff_q = -round(0.3 * cfo_q)
            ytd_cfo += cfo_q
            ytd_cfi += cfi_q
            ytd_cff += cff_q
            if q == 1:
                cash_begin = cash
            cash = round(0.1 * assets)
            change = cash - cash_begin
            fx = change - (ytd_cfo + ytd_cfi + ytd_cff)
            form = "10-K" if q == 4 else "10-Q"
            accn = f"{cik:010d}-{year % 100:02d}-{q:06d}"
            filed = (date.fromisoformat(period_end).replace(day=28)).isoformat()
            values = {
                "assets": assets,
                "assets_current": current_assets,
                "liabilities": liabilities,
                "liabilities_current": current_liabilities,
                "equity": equity,
                "liabilities_and_equity": assets,
                "cash": cash,
                "revenue": ytd_rev,
                "cost_of_revenue": cost,
                "gross_profit": gross,
                "operating_income": operating,
                "income_tax": tax,
                "net_income": net,
                "cfo": ytd_cfo,
                "cfi": ytd_cfi,
                "cff": ytd_cff,
                "cash_change": change,
                "fx_effect": fx,
                "dda": round(0.02 * assets * q / 4),
                "capex": -cfi_q * q,
            }
            company.periods.append(period_end)
            company.cells[period_end] = {}
            for key, value in values.items():
                item = config.ITEM_BY_KEY[key]
                company.cells[period_end][key] = Cell(
                    cik=cik,
                    name=company.name,
                    period_end=period_end,
                    period_start="" if item.instant else fy_start,
                    ytd_months=0 if item.instant else 3 * q,
                    item=key,
                    value=float(value),
                    source=Source(accn, form, filed, item.elements[0], "2026-11-02"),
                    split=split,
                )
    return company


@pytest.fixture(scope="session")
def companies() -> Companies:
    """Six development and six held-out synthetic companies."""
    out: Companies = {}
    for i in range(12):
        cik = 1000 + i
        out[cik] = make_company(cik, "development" if i < 6 else "heldout", seed=7)
    return out
