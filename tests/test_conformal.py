import random
from fractions import Fraction

import pytest

from egr.conformal import Calibration, PValue, benjamini_hochberg, rank_by_p


@pytest.mark.req("REQ-004")
def test_p_value_counts_calibration_scores_at_least_as_large():
    cal = Calibration([1.0, 2.0, 3.0, 4.0])
    assert cal.p_value(5.0) == PValue(1, 5)
    assert cal.p_value(3.0) == PValue(3, 5)
    assert cal.p_value(0.0) == PValue(5, 5)


def _reference_bh(p_values: dict[str, PValue], q: Fraction) -> set[str]:
    ordered = sorted(p_values.items(), key=lambda kv: (Fraction(kv[1].num, kv[1].den), kv[0]))
    m = len(ordered)
    threshold = None
    for k, (_, p) in enumerate(ordered, start=1):
        if Fraction(p.num, p.den) <= q * k / m:
            threshold = Fraction(p.num, p.den)
    if threshold is None:
        return set()
    return {key for key, p in ordered if Fraction(p.num, p.den) <= threshold}


@pytest.mark.req("REQ-004")
@pytest.mark.parametrize("seed", range(5))
def test_benjamini_hochberg_matches_an_exact_fraction_implementation(seed):
    rng = random.Random(seed)
    dens = [rng.choice([51, 101, 1001]) for _ in range(3)]
    p_values = {
        f"c{i}": PValue(rng.randint(1, d), d) for i in range(300) for d in [rng.choice(dens)]
    }
    for q in (5, 10, 20):
        assert benjamini_hochberg(p_values, q) == _reference_bh(p_values, Fraction(q, 100))


@pytest.mark.req("REQ-004")
def test_rank_by_p_breaks_ties_by_score_then_id():
    p = {"a": PValue(1, 10), "b": PValue(1, 10), "c": PValue(2, 10)}
    scores = {"a": 5.0, "b": 9.0, "c": 50.0}
    assert rank_by_p(p, scores) == ["b", "a", "c"]


def test_empty_inputs():
    assert benjamini_hochberg({}, 10) == set()
    assert Calibration([]).p_value(1.0) == PValue(1, 1)
