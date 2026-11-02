"""Plausibility score of each cell (layer 2), following docs/analysis_plan.md.

Pure Python arithmetic on floats: addition, subtraction, multiplication,
division, absolute value and sorting only. No logarithms, no numpy reductions,
so the same input gives the same bytes on every machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from egr import config
from egr.cells import Cell, Company

Values = dict[str, float]


@dataclass
class Score:
    """The plausibility test of one cell."""

    cell_id: str
    value: float
    prediction: float
    residual: float
    scale: float
    score: float
    candidates: dict[str, float] = field(default_factory=dict)
    source_cell_ids: list[str] = field(default_factory=list)
    history_n: int = 0


def median(values: list[float]) -> float:
    """Median of a non-empty list, the mean of the middle two for even counts."""
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def round_sig(x: float, digits: int = config.SCORE_DIGITS) -> float:
    """Round to a number of significant digits through correctly rounded formatting."""
    if x == 0.0:
        return 0.0
    return float(f"{x:.{digits}g}")


def _earlier(company: Company, cell: Cell) -> list[str]:
    """Earlier periods usable as history: same year-to-date length for durations."""
    out = []
    for p in company.periods:
        if p >= cell.period_end:
            break
        other = company.get(p, cell.item)
        if other is not None and (cell.ytd_months == 0 or other.ytd_months == cell.ytd_months):
            out.append(p)
    return out


def _value(company: Company, view: Values, period_end: str, item: str) -> float | None:
    cell = company.get(period_end, item)
    return None if cell is None else view[cell.cell_id]


def candidates_for(
    company: Company, cell: Cell, view: Values
) -> tuple[dict[str, float], list[str]]:
    """Candidate predictions for a cell and the cells they were computed from."""
    cands: dict[str, float] = {}
    sources: list[str] = []
    item = config.ITEM_BY_KEY[cell.item]
    periods = company.periods
    i = periods.index(cell.period_end)
    earlier = _earlier(company, cell)
    # 1. previous period of the same kind
    if earlier:
        prev = earlier[-1]
        prev_cell = company.get(prev, cell.item)
        assert prev_cell is not None
        cands["previous_period"] = view[prev_cell.cell_id]
        sources.append(prev_cell.cell_id)
    # 2. seasonal or scaled year-to-date
    if item.instant:
        if i >= 4:
            four_back = company.get(periods[i - 4], cell.item)
            if four_back is not None:
                cands["four_periods_earlier"] = view[four_back.cell_id]
                sources.append(four_back.cell_id)
    else:
        best: Cell | None = None
        for p in periods[:i]:
            other = company.get(p, cell.item)
            if (
                other is not None
                and other.period_start == cell.period_start
                and 0 < other.ytd_months < cell.ytd_months
                and (best is None or other.ytd_months > best.ytd_months)
            ):
                best = other
        if best is not None:
            cands["scaled_year_to_date"] = view[best.cell_id] * cell.ytd_months / best.ytd_months
            sources.append(best.cell_id)
    # 3. partner ratio
    if item.partner == "cashflow_sum":
        parts = [company.get(cell.period_end, k) for k in ("cfo", "cfi", "cff")]
        if all(part is not None for part in parts):
            fx = company.get(cell.period_end, "fx_effect")
            total = 0.0
            for part in parts:
                assert part is not None
                total += view[part.cell_id]
                sources.append(part.cell_id)
            if fx is not None:
                total += view[fx.cell_id]
                sources.append(fx.cell_id)
            cands["cash_flow_components"] = total
    else:
        partner_key = None
        for key in (item.partner, item.partner_fallback):
            if key is not None and company.get(cell.period_end, key) is not None:
                partner_key = key
                break
        if partner_key is not None:
            partner_now = _value(company, view, cell.period_end, partner_key)
            ratios = []
            for p in earlier:
                own = _value(company, view, p, cell.item)
                partner = _value(company, view, p, partner_key)
                if own is not None and partner is not None and partner != 0:
                    ratios.append(own / partner)
            if partner_now is not None and len(ratios) >= config.MIN_HISTORY:
                cands[f"ratio_to_{partner_key}"] = partner_now * median(ratios)
                partner_cell = company.get(cell.period_end, partner_key)
                assert partner_cell is not None
                sources.append(partner_cell.cell_id)
    return cands, sources


def score_company(company: Company, view: Values) -> dict[str, Score]:
    """Scores of every tested cell of a company, computed period by period."""
    scores: dict[str, Score] = {}
    residuals: dict[str, list[tuple[str, int, float]]] = {}  # item -> (period, ytd, |residual|)
    for period_end in company.periods:
        for item_key in sorted(company.cells[period_end]):
            cell = company.cells[period_end][item_key]
            if not cell.tested:
                continue
            cands, sources = candidates_for(company, cell, view)
            if not cands:
                continue
            value = view[cell.cell_id]
            prediction = median(list(cands.values()))
            residual = value - prediction
            earlier = _earlier(company, cell)
            earlier_values = [abs(view[company.cells[p][item_key].cell_id]) for p in earlier]
            hist = [
                r
                for (p, ytd, r) in residuals.get(item_key, [])
                if p < period_end and (cell.ytd_months == 0 or ytd == cell.ytd_months)
            ]
            floor = config.SCALE_FLOOR_ABS
            if earlier_values:
                floor = max(floor, config.SCALE_FLOOR_SHARE * median(earlier_values))
            if len(hist) >= config.MIN_HISTORY:
                scale = max(median(hist), floor)
            else:
                scale = max(config.NO_HISTORY_SCALE_SHARE * abs(prediction), floor)
            score = round_sig(abs(residual) / scale)
            scores[cell.cell_id] = Score(
                cell.cell_id, value, prediction, residual, scale, score, cands, sources, len(hist)
            )
            residuals.setdefault(item_key, []).append((period_end, cell.ytd_months, abs(residual)))
    return scores
