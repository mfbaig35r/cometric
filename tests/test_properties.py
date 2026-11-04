"""Property tests (spec 9): allocation, tier continuity, monotonic MARGINAL fees, ALL_UNITS cliffs."""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from cometric.core.enums import TierMethod
from cometric.core.models import Tier
from cometric.core.money import allocate_exact
from cometric.core.tiers import all_units_cliffs, check_contiguous, price

money = st.decimals(min_value=0, max_value=10**9, places=2, allow_nan=False, allow_infinity=False)


@given(total=money, parts=st.integers(min_value=1, max_value=60))
def test_allocation_preserves_total(total, parts):
    shares = allocate_exact(total, parts, 2)
    assert sum(shares) == total
    assert max(shares) - min(shares) <= Decimal("0.01")


@st.composite
def schedules(draw):
    n = draw(st.integers(min_value=1, max_value=5))
    bounds = sorted(
        set(
            draw(
                st.lists(
                    st.integers(min_value=1, max_value=10000),
                    min_size=n - 1,
                    max_size=n - 1,
                    unique=True,
                )
            )
        )
    )
    rates = draw(
        st.lists(
            st.decimals(
                min_value=0, max_value=500, places=2, allow_nan=False, allow_infinity=False
            ),
            min_size=len(bounds) + 1,
            max_size=len(bounds) + 1,
        )
    )
    edges = [0, *bounds]
    tiers = []
    for i, start in enumerate(edges):
        end = edges[i + 1] if i + 1 < len(edges) else None
        tiers.append(
            Tier.model_validate(
                {"from": str(start), "to": None if end is None else str(end), "rate": str(rates[i])}
            )
        )
    return tiers


@settings(max_examples=200)
@given(
    tiers=schedules(),
    q=st.integers(min_value=0, max_value=20000),
    dq=st.integers(min_value=0, max_value=500),
)
def test_marginal_fee_is_monotonic(tiers, q, dq):
    assert check_contiguous(tiers) == []
    assert price(Decimal(q + dq), tiers, TierMethod.MARGINAL) >= price(
        Decimal(q), tiers, TierMethod.MARGINAL
    )


@settings(max_examples=200)
@given(
    tiers=schedules(),
    q=st.integers(min_value=0, max_value=20000),
    dq=st.integers(min_value=0, max_value=500),
)
def test_all_units_monotonic_outside_reported_cliffs(tiers, q, dq):
    cliffs = all_units_cliffs(tiers)

    def inside(x):
        return any(c["band_lower_exclusive"] < x < c["band_upper_exclusive"] for c in cliffs)

    a, b = Decimal(q), Decimal(q + dq)
    if price(b, tiers, TierMethod.ALL_UNITS) < price(a, tiers, TierMethod.ALL_UNITS):
        assert inside(a), (a, b, cliffs)
