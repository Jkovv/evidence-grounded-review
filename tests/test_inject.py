import random
from collections import Counter

import pytest

from egr import config
from egr.cells import all_cells
from egr.inject import inject, shortfall, transpose_digits, values_view


@pytest.mark.req("REQ-019")
def test_rate_and_equal_shares(companies):
    injection = inject(companies, 0.05, 0)
    tested = [c for c in all_cells(companies) if c.tested]
    assert abs(len(injection) - round(0.05 * len(tested))) <= 1
    counts = Counter(i.error_type for i in injection.values())
    assert set(counts) == set(config.ERROR_TYPES)
    assert max(counts.values()) - min(counts.values()) <= 2
    assert shortfall(injection, len(tested), 0.05) == dict.fromkeys(config.ERROR_TYPES, 0)


@pytest.mark.req("REQ-019")
def test_every_injected_value_differs_and_no_cell_is_hit_twice(companies):
    injection = inject(companies, 0.05, 1)
    for inj in injection.values():
        assert inj.injected != inj.original
    assert len(injection) == len(set(injection))
    view = values_view(companies, injection)
    for cid, inj in injection.items():
        assert view[cid] == inj.injected


@pytest.mark.req("REQ-019")
def test_swaps_are_symmetric_and_within_split(companies):
    injection = inject(companies, 0.05, 2)
    swaps = {k: v for k, v in injection.items() if v.error_type == "cross_company_swap"}
    assert swaps
    for cid, inj in swaps.items():
        partner = injection[inj.partner_cell_id]
        assert partner.partner_cell_id == cid
        assert partner.injected == inj.original
        a, b = cid.split("|"), inj.partner_cell_id.split("|")
        assert a[1:] == b[1:]
        assert companies[int(a[0])].split == companies[int(b[0])].split


@pytest.mark.req("REQ-019")
def test_copy_forward_takes_the_previous_value_of_the_same_length(companies):
    injection = inject(companies, 0.05, 3)
    copies = [v for v in injection.values() if v.error_type == "copy_forward"]
    assert copies
    for inj in copies:
        cik, period, item = inj.cell_id.split("|")
        pcik, pperiod, pitem = inj.partner_cell_id.split("|")
        assert (cik, item) == (pcik, pitem) and pperiod < period
        src = companies[int(cik)].get(pperiod, item)
        dst = companies[int(cik)].get(period, item)
        assert src is not None and dst is not None
        assert src.ytd_months == dst.ytd_months
        assert inj.injected == src.value


@pytest.mark.req("REQ-001")
def test_injection_is_reproducible_and_replicates_differ(companies):
    a = inject(companies, 0.02, 0)
    b = inject(companies, 0.02, 0)
    c = inject(companies, 0.02, 1)
    assert a == b
    assert a != c


def test_transpose_digits_changes_leading_digits_only():
    rng = random.Random(0)
    for _ in range(50):
        out = transpose_digits(123456789.0, rng)
        assert out is not None
        assert sorted(str(int(out))) == sorted("123456789")
        assert str(int(out))[4:] == "56789"
    assert transpose_digits(7.0, rng) is None
    assert transpose_digits(1111.0, rng) is None
    assert transpose_digits(-1200.0, rng) == -2100.0
