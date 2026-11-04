"""Calendar months, day segments, and accumulation-period keys (spec 4.3, 4.6)."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from .enums import AccumulationPeriod

Month = tuple[int, int]


def month_of(d: date) -> Month:
    return (d.year, d.month)


def month_str(m: Month) -> str:
    return f"{m[0]:04d}-{m[1]:02d}"


def parse_month(text: str) -> Month:
    y, m = text.split("-")
    return (int(y), int(m))


def month_index(m: Month) -> int:
    return m[0] * 12 + (m[1] - 1)


def from_index(i: int) -> Month:
    return (i // 12, i % 12 + 1)


def months_between(start: Month, end: Month) -> list[Month]:
    return [from_index(i) for i in range(month_index(start), month_index(end) + 1)]


def days_in_month(m: Month) -> int:
    return calendar.monthrange(m[0], m[1])[1]


def first_day(m: Month) -> date:
    return date(m[0], m[1], 1)


def last_day(m: Month) -> date:
    return date(m[0], m[1], days_in_month(m))


def period_key(period: AccumulationPeriod, m: Month, anchor: Month) -> tuple:
    if period == AccumulationPeriod.MONTH:
        return ("M", m)
    if period == AccumulationPeriod.QUARTER:
        return ("Q", m[0], (m[1] - 1) // 3)
    if period == AccumulationPeriod.YEAR:
        return ("Y", m[0])
    if period == AccumulationPeriod.CONTRACT_YEAR:
        return ("CY", (month_index(m) - month_index(anchor)) // 12)
    return ("T",)


def is_period_end(period: AccumulationPeriod, m: Month, anchor: Month, last: Month) -> bool:
    """True when m is the final month of its accumulation period within the engagement."""
    if m == last:
        return True
    nxt = from_index(month_index(m) + 1)
    return period_key(period, nxt, anchor) != period_key(period, m, anchor)


def period_truncated(
    period: AccumulationPeriod, m: Month, anchor: Month, horizon_last: Month, engagement_last: Month
) -> bool:
    """True when the horizon ends before this period's natural end (true-up falls outside)."""
    if m != horizon_last or m == engagement_last:
        return False
    nxt = from_index(month_index(m) + 1)
    return period_key(period, nxt, anchor) == period_key(period, m, anchor)


@dataclass(frozen=True)
class DaySpan:
    start: date
    end: date  # inclusive

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def overlap(a: DaySpan, b: DaySpan) -> DaySpan | None:
    s = max(a.start, b.start)
    e = min(a.end, b.end)
    return DaySpan(s, e) if s <= e else None


def month_span(m: Month) -> DaySpan:
    return DaySpan(first_day(m), last_day(m))


def day_before(d: date) -> date:
    return d - timedelta(days=1)
