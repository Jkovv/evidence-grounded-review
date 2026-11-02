"""Conformal p-values and Benjamini-Hochberg with integer arithmetic.

A p-value is the fraction (1 + number of calibration scores at least as large)
over (number of calibration scores + 1), kept as a numerator and denominator.
Benjamini-Hochberg compares these fractions with k q / m using integers only,
so no floating point comparison decides a flag. Sorting uses the float value
of the fraction, which orders distinct fractions with these denominators
correctly and gives equal keys to equal fractions.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import NamedTuple


class PValue(NamedTuple):
    """A conformal p-value as an exact fraction."""

    num: int
    den: int

    def __float__(self) -> float:
        return self.num / self.den


class Calibration:
    """Sorted calibration scores of one item."""

    def __init__(self, scores: list[float]) -> None:
        self.sorted = sorted(scores)
        self.n = len(self.sorted)

    def p_value(self, score: float) -> PValue:
        """Conformal p-value of a score against the calibration set."""
        at_least = self.n - bisect_left(self.sorted, score)
        return PValue(1 + at_least, self.n + 1)


def benjamini_hochberg(p_values: dict[str, PValue], q_percent: int) -> set[str]:
    """Keys rejected by the step-up procedure at level q_percent / 100."""
    if not p_values:
        return set()
    ordered = sorted(p_values.items(), key=lambda kv: (float(kv[1]), kv[0]))
    m = len(ordered)
    threshold: PValue | None = None
    for k, (_, p) in enumerate(ordered, start=1):
        # p <= q k / m  with  p = num / den  and  q = q_percent / 100
        if p.num * m * 100 <= q_percent * k * p.den:
            threshold = p
    if threshold is None:
        return set()
    limit = float(threshold)
    return {key for key, p in ordered if float(p) <= limit}


def rank_by_p(p_values: dict[str, PValue], scores: dict[str, float]) -> list[str]:
    """Cell ids from most to least surprising: smallest p, then largest score, then id."""
    return sorted(p_values, key=lambda k: (float(p_values[k]), -scores[k], k))
