"""In-memory form of the cell table used by the deterministic core.

The detection core works on plain Python objects, sorted explicitly, so that
its output does not depend on the platform. Pandas is used only to read and
write parquet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from egr import config


@dataclass(frozen=True)
class Source:
    """Where a value came from, as recorded in the evidence."""

    accn: str
    form: str
    filed: str
    element: str
    retrieved: str


@dataclass
class Cell:
    """One as-reported value of one item at one period of one company."""

    cik: int
    name: str
    period_end: str
    period_start: str
    ytd_months: int
    item: str
    value: float
    source: Source
    split: str
    amended_changed: bool = False
    amended_value: float | None = None
    revised_later: bool = False

    @property
    def cell_id(self) -> str:
        """Stable identifier used in every output."""
        return f"{self.cik}|{self.period_end}|{self.item}"

    @property
    def tested(self) -> bool:
        """Whether the item is under test (the exchange rate effect is context only)."""
        return config.ITEM_BY_KEY[self.item].tested


@dataclass
class Company:
    """All cells of one company, by period end and item."""

    cik: int
    name: str
    split: str
    periods: list[str] = field(default_factory=list)
    cells: dict[str, dict[str, Cell]] = field(default_factory=dict)

    def get(self, period_end: str, item: str) -> Cell | None:
        """The cell at a period for an item, or None."""
        return self.cells.get(period_end, {}).get(item)


Companies = dict[int, Company]


def load_companies(path: Path, retrieved: str = "") -> Companies:
    """Read cells.parquet into Company objects, sorted by CIK, period and item."""
    frame = pd.read_parquet(path)
    frame = frame.sort_values(["cik", "period_end", "item"], kind="mergesort")
    out: Companies = {}
    for row in frame.to_dict("records"):
        cik = int(row["cik"])
        company = out.get(cik)
        if company is None:
            company = Company(cik, str(row["name"]), str(row["split"]))
            out[cik] = company
        amended = None if pd.isna(row["amended_value"]) else float(row["amended_value"])
        cell = Cell(
            cik=cik,
            name=str(row["name"]),
            period_end=str(row["period_end"]),
            period_start=str(row["period_start"]),
            ytd_months=int(row["ytd_months"]),
            item=str(row["item"]),
            value=float(row["value"]),
            source=Source(
                str(row["accn"]),
                str(row["form"]),
                str(row["filed"]),
                str(row["element"]),
                retrieved,
            ),
            split=str(row["split"]),
            amended_changed=bool(row["amended_changed"]),
            amended_value=amended,
            revised_later=bool(row["revised_later"]),
        )
        if cell.period_end not in company.cells:
            company.cells[cell.period_end] = {}
            company.periods.append(cell.period_end)
        company.cells[cell.period_end][cell.item] = cell
    for company in out.values():
        company.periods.sort()
    return dict(sorted(out.items()))


def all_cells(companies: Companies) -> list[Cell]:
    """Every cell in a fixed order."""
    return [
        company.cells[p][item]
        for company in companies.values()
        for p in company.periods
        for item in sorted(company.cells[p])
    ]
