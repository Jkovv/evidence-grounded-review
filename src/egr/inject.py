"""Error injection with documented rates, following docs/analysis_plan.md.

An injection is a mapping from cell id to the injected value, together with
the type and the original value. The clean cells are never modified; the
detectors receive a values view built from the injection.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from egr import config
from egr.cells import Cell, Companies, all_cells


@dataclass(frozen=True)
class Injected:
    """One injected error."""

    cell_id: str
    error_type: str
    original: float
    injected: float
    partner_cell_id: str = ""


Injection = dict[str, Injected]


def transpose_digits(value: float, rng: random.Random) -> float | None:
    """Exchange two adjacent digits among the first significant digits of the integer value."""
    sign = -1.0 if value < 0 else 1.0
    digits = str(int(abs(value)))
    if len(digits) < 2:
        return None
    limit = min(config.TRANSPOSITION_DIGITS, len(digits))
    positions = [i for i in range(limit - 1) if digits[i] != digits[i + 1]]
    if not positions:
        return None
    i = rng.choice(positions)
    swapped = digits[:i] + digits[i + 1] + digits[i] + digits[i + 2 :]
    if swapped[0] == "0":
        return None
    return sign * float(int(swapped))


def previous_same_length(company_cells: list[Cell], cell: Cell) -> Cell | None:
    """The latest earlier cell of the same item with the same year-to-date length."""
    best: Cell | None = None
    for other in company_cells:
        if (
            other.item == cell.item
            and other.period_end < cell.period_end
            and other.ytd_months == cell.ytd_months
            and (best is None or other.period_end > best.period_end)
        ):
            best = other
    return best


def inject(companies: Companies, rate: float, replicate: int, seed: int = config.SEED) -> Injection:
    """Draw an injection of the given rate over all tested, non-amended cells.

    The seed combines the base seed, the replicate and the rate so that every
    (rate, replicate) pair has its own reproducible draw.
    """
    rng = random.Random(f"{seed}|{replicate}|{rate}")
    cells = [c for c in all_cells(companies) if c.tested and not c.amended_changed]
    by_company: dict[int, list[Cell]] = {}
    for c in cells:
        by_company.setdefault(c.cik, []).append(c)
    n_total = round(rate * len(cells))
    per_type = n_total // len(config.ERROR_TYPES)
    remainder = n_total - per_type * len(config.ERROR_TYPES)
    shares = {t: per_type + (1 if i < remainder else 0) for i, t in enumerate(config.ERROR_TYPES)}
    injection: Injection = {}
    used: set[str] = set()

    def take(candidates: list[Cell], n: int) -> list[Cell]:
        pool = [c for c in candidates if c.cell_id not in used]
        chosen = rng.sample(pool, min(n, len(pool)))
        for c in chosen:
            used.add(c.cell_id)
        return chosen

    nonzero = [c for c in cells if c.value != 0]
    for c in take(nonzero, shares["sign_flip"]):
        injection[c.cell_id] = Injected(c.cell_id, "sign_flip", c.value, -c.value)
    for c in take(nonzero, shares["scale_slip"]):
        if rng.random() < 0.5:
            new = c.value * config.SCALE_FACTOR
        else:
            new = float(round(c.value / config.SCALE_FACTOR))
        if new == c.value:
            new = c.value * config.SCALE_FACTOR
        injection[c.cell_id] = Injected(c.cell_id, "scale_slip", c.value, new)
    # transposition and copy-forward need a per-cell eligibility check, so draw
    # from a shuffled pool until the share is met
    pool = [c for c in cells if c.cell_id not in used and abs(c.value) >= 10]
    rng.shuffle(pool)
    n_done = 0
    for c in pool:
        if n_done >= shares["digit_transposition"]:
            break
        transposed = transpose_digits(c.value, rng)
        if transposed is None or transposed == c.value:
            continue
        used.add(c.cell_id)
        injection[c.cell_id] = Injected(c.cell_id, "digit_transposition", c.value, transposed)
        n_done += 1
    pool = [c for c in cells if c.cell_id not in used]
    rng.shuffle(pool)
    n_done = 0
    for c in pool:
        if n_done >= shares["copy_forward"]:
            break
        prev = previous_same_length(by_company[c.cik], c)
        if prev is None or prev.value == c.value:
            continue
        used.add(c.cell_id)
        injection[c.cell_id] = Injected(
            c.cell_id, "copy_forward", c.value, prev.value, prev.cell_id
        )
        n_done += 1
    # swaps: pairs of companies in the same split with the same item and period end
    groups: dict[tuple[str, str, str], list[Cell]] = {}
    for c in cells:
        if c.cell_id not in used:
            groups.setdefault((c.split, c.item, c.period_end), []).append(c)
    pairs: list[tuple[Cell, Cell]] = []
    for key in sorted(groups):
        members = groups[key]
        rng.shuffle(members)
        for a, b in zip(members[0::2], members[1::2], strict=False):
            if a.value != b.value:
                pairs.append((a, b))
    rng.shuffle(pairs)
    n_done = 0
    for a, b in pairs:
        if n_done >= shares["cross_company_swap"]:
            break
        if a.cell_id in used or b.cell_id in used:
            continue
        used.update((a.cell_id, b.cell_id))
        injection[a.cell_id] = Injected(
            a.cell_id, "cross_company_swap", a.value, b.value, b.cell_id
        )
        injection[b.cell_id] = Injected(
            b.cell_id, "cross_company_swap", b.value, a.value, a.cell_id
        )
        n_done += 2
    return injection


def shortfall(injection: Injection, n_tested: int, rate: float) -> dict[str, int]:
    """Cells short of the planned share, per type (swaps count both cells)."""
    n_total = round(rate * n_tested)
    per_type = n_total // len(config.ERROR_TYPES)
    counts = {t: 0 for t in config.ERROR_TYPES}
    for inj in injection.values():
        counts[inj.error_type] += 1
    return {t: max(0, per_type - counts[t]) for t in config.ERROR_TYPES}


def values_view(companies: Companies, injection: Injection) -> dict[str, float]:
    """Cell id to value after injection."""
    view = {c.cell_id: c.value for c in all_cells(companies)}
    for cell_id, inj in injection.items():
        view[cell_id] = inj.injected
    return view
