"""Monthly calculation engine: evaluation order (4.5), costs (5.2), capacity (5.3), metrics (5.4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

from .enums import (
    AdjustmentType,
    AggregationScope,
    Avoidability,
    BreachMode,
    CalculationMethod,
    ChargeCadence,
    CommitmentKind,
    CostBehavior,
    CostPeriod,
    MarginLayer,
    ProrationPolicy,
    Recognition,
    RoundingLevel,
    ShortfallRule,
    TestedAgainst,
    TierScope,
    TransitionView,
)
from .issues import CometricError, Issues, pointer
from .ledger import EntitlementLedger
from .models import (
    ArrangementVersion,
    CostComponent,
    CostPolicy,
    Engagement,
    FeeComponent,
    MoneyPolicy,
    Scenario,
)
from .money import MINOR_UNITS, ONE, ZERO, allocate_exact, allocate_weighted, quantize, safe_ratio
from .periods import (
    DaySpan,
    Month,
    is_period_end,
    month_index,
    month_of,
    month_span,
    month_str,
    months_between,
    overlap,
    period_key,
    period_truncated,
)
from .quantities import Quantities, build_quantities
from .tiers import incremental, price

ENGINE_VERSION = "0.1.0"

STEP_NAMES = {
    4: "price",
    5: "collar",
    6: "discount",
    7: "minimum",
    8: "performance",
    9: "cap",
}


@dataclass
class FeeLine:
    period: str
    step: int
    ref: str
    component: str | None
    kind: str
    amount: Decimal
    rounded: Decimal
    formula: str
    quantity: Decimal | None = None
    unit: str | None = None
    rate: Decimal | None = None
    segment: str | None = None
    version: str | None = None

    def as_dict(self) -> dict:
        return {
            "period": self.period,
            "step": self.step,
            "stage": STEP_NAMES.get(self.step, str(self.step)),
            "ref": self.ref,
            "component": self.component,
            "kind": self.kind,
            "quantity": self.quantity,
            "unit": self.unit,
            "rate": self.rate,
            "amount_unrounded": self.amount,
            "amount": self.rounded,
            "formula": self.formula,
            "segment": self.segment,
            "version": self.version,
        }


@dataclass
class CostLine:
    period: str
    ref: str
    category: str
    layer: MarginLayer
    amount: Decimal
    rounded: Decimal
    formula: str
    incurred: Decimal | None = None
    amortized: Decimal | None = None
    unavoidable: bool = False
    driver_quantity: Decimal | None = None

    def as_dict(self) -> dict:
        return {
            "period": self.period,
            "ref": self.ref,
            "category": self.category,
            "layer": str(self.layer),
            "amount_unrounded": self.amount,
            "amount": self.rounded,
            "formula": self.formula,
            "incurred": self.incurred,
            "amortized": self.amortized,
            "driver_quantity": self.driver_quantity,
        }


@dataclass
class Segment:
    span: DaySpan
    version: ArrangementVersion | None
    factor: Decimal  # share of the month's days


@dataclass
class CalculationResult:
    data: dict
    fee_lines: list[FeeLine]
    cost_lines: list[CostLine]
    ledger: list[dict]
    issues: Issues
    feasible: bool
    status: str = "ok"
    extras: dict = field(default_factory=dict)


def effective_money_policy(engagement: Engagement) -> MoneyPolicy:
    mp = engagement.money_policy or MoneyPolicy()
    scale = (
        mp.rounding_scale
        if mp.rounding_scale is not None
        else MINOR_UNITS.get(engagement.currency, 2)
    )
    return MoneyPolicy(
        rounding_mode=mp.rounding_mode, rounding_scale=scale, rounding_level=mp.rounding_level
    )


class Calculator:
    def __init__(
        self,
        engagement: Engagement,
        scenario: Scenario,
        cost_policy: CostPolicy | None,
        issues: Issues | None = None,
    ):
        self.e = engagement
        self.s = scenario
        self.policy = cost_policy
        self.issues = issues if issues is not None else Issues()
        self.money = effective_money_policy(engagement)
        self.scale = self.money.rounding_scale
        self.anchor = month_of(engagement.start_date)
        self.eng_last = month_of(engagement.end_date)
        hz_from = scenario.horizon.from_ if scenario.horizon else engagement.start_date
        hz_to = scenario.horizon.to if scenario.horizon else engagement.end_date
        self.first = max(month_of(hz_from), self.anchor)
        self.last = min(month_of(hz_to), self.eng_last)
        self.months = months_between(self.first, self.last)
        self.fee_lines: list[FeeLine] = []
        self.cost_lines: list[CostLine] = []
        self.ledgers: dict[str, EntitlementLedger] = {}
        self.acc: dict[tuple, Decimal] = {}
        self.pending_overage: dict[str, Decimal] = {}
        self.feasible = True
        self.capacity_state: dict[str, dict] = {}
        self.backlog: dict[str, Decimal] = {}
        self.overflow: dict[tuple[str, Month], Decimal] = {}
        self.unit_kinds = {u.code: u.kind for u in engagement.unit_definitions}

    # -- helpers --------------------------------------------------------------------------

    def r(self, amount: Decimal) -> Decimal:
        if self.money.rounding_level == RoundingLevel.LINE_ITEM:
            return quantize(amount, self.scale, str(self.money.rounding_mode))
        return amount

    def fee(
        self,
        m: Month,
        step: int,
        ref: str,
        component: str | None,
        kind: str,
        amount: Decimal,
        formula: str,
        **kw,
    ) -> FeeLine:
        line = FeeLine(
            month_str(m), step, ref, component, kind, amount, self.r(amount), formula, **kw
        )
        self.fee_lines.append(line)
        return line

    def acc_add(self, key: tuple, value: Decimal) -> Decimal:
        before = self.acc.get(key, ZERO)
        self.acc[key] = before + value
        return before

    def qty(self, quantities: Quantities, name: str | None, m: Month, path: str) -> Decimal:
        if name is None:
            self.issues.error("MISSING_QUANTITY_SOURCE", "component needs a quantity_source", path)
            raise CometricError(self.issues)
        key = name[len("scenario.") :] if name.startswith("scenario.") else name
        v = quantities.get(key, m)
        if v is None:
            self.issues.error(
                "MISSING_ASSUMPTION", f"scenario has no assumption named {key!r}", path
            )
            raise CometricError(self.issues)
        return v

    def weighted_qty(
        self, quantities: Quantities, base: str, table_id: str | None, m: Month, path: str
    ) -> Decimal:
        key = base[len("scenario.") :] if base.startswith("scenario.") else base
        tables = [t for t in self.e.weight_tables if table_id is None or t.id == table_id]
        if not tables:
            self.issues.error("UNKNOWN_WEIGHT_TABLE", f"no weight table {table_id!r}", path)
            raise CometricError(self.issues)
        table = tables[0]
        total = ZERO
        found = False
        for band in table.bands:
            v = quantities.get(f"{key}.{band.code}", m)
            if v is not None:
                found = True
                total += v * band.weight
        if not found:
            self.issues.error(
                "MISSING_ASSUMPTION", f"scenario has no band quantities named {key}.<band>", path
            )
            raise CometricError(self.issues)
        return total

    # -- segments -------------------------------------------------------------------------

    def version_span(self, v: ArrangementVersion) -> DaySpan:
        return DaySpan(
            max(v.effective_from, self.e.start_date),
            min(v.effective_to or self.e.end_date, self.e.end_date),
        )

    def segments(self, m: Month) -> list[Segment]:
        ms = month_span(m)
        raw: list[tuple[DaySpan, ArrangementVersion | None]] = []
        for v in self.e.arrangement_versions:
            ov = overlap(self.version_span(v), ms)
            if ov:
                raw.append((ov, v))
        raw.sort(key=lambda x: x[0].start)
        # fill gaps with unpriced spans so boundaries are explicit
        filled: list[tuple[DaySpan, ArrangementVersion | None]] = []
        cursor = ms.start
        for span, v in raw:
            if span.start > cursor:
                filled.append(
                    (DaySpan(cursor, span.start.fromordinal(span.start.toordinal() - 1)), None)
                )
            filled.append((span, v))
            cursor = span.end.fromordinal(span.end.toordinal() + 1)
        if cursor <= ms.end:
            filled.append((DaySpan(cursor, ms.end), None))
        # apply proration policy at each mid-month boundary
        i = 1
        while i < len(filled):
            (sa, va), (sb, vb) = filled[i - 1], filled[i]
            policy = (vb.proration_policy if vb else None) or (va.proration_policy if va else None)
            if va is vb:
                filled[i - 1 : i + 1] = [(DaySpan(sa.start, sb.end), va)]
                continue
            if policy == ProrationPolicy.FULL_MONTH_FROM_NEXT:
                filled[i - 1 : i + 1] = [(DaySpan(sa.start, sb.end), va)]
                continue
            if policy == ProrationPolicy.FULL_MONTH_FROM_CURRENT:
                filled[i - 1 : i + 1] = [(DaySpan(sa.start, sb.end), vb)]
                continue
            i += 1
        dim = Decimal(ms.days)
        return [Segment(span, v, Decimal(span.days) / dim) for span, v in filled]

    # -- run ------------------------------------------------------------------------------

    def run(self) -> CalculationResult:
        quantities = build_quantities(self.e, self.s, self.months, self.issues)
        if self.issues.has_errors:
            raise CometricError(self.issues)
        self.quantities = quantities
        self._derive_demand_hours(quantities)
        per_month: dict[Month, dict] = {}
        for m in self.months:
            self._capacity(m, quantities)
            segs = self.segments(m)
            self._fees_for_month(m, segs, quantities)
            self._costs_for_month(m, quantities)
        ended = self.last == self.eng_last
        for led in self.ledgers.values():
            led.finish(self.last, ended)
            for p in led.check_invariant():
                self.issues.error("LEDGER_INVARIANT", p)
        for m in self.months:
            per_month[m] = self._month_totals(m)
        data = self._aggregate(per_month, quantities)
        ledger = [e.as_dict() for led in self.ledgers.values() for e in led.entries]
        status = "ok" if self.feasible else "infeasible"
        return CalculationResult(
            data, self.fee_lines, self.cost_lines, ledger, self.issues, self.feasible, status
        )

    # -- fees -----------------------------------------------------------------------------

    def _fees_for_month(self, m: Month, segs: list[Segment], quantities: Quantities) -> None:
        priced = [s for s in segs if s.version is not None]
        if not priced:
            return
        split = len(priced) > 1
        if split:
            self.issues.info(
                "SEGMENTED_MONTH",
                f"{month_str(m)} spans {len(priced)} contract versions",
                "",
                month=month_str(m),
            )
        last_version = priced[-1].version
        # open entitlement periods for this month (once per month)
        for v in {id(s.version): s.version for s in priced}.values():
            for ent in v.entitlements:
                key = period_key(ent.accumulation_period, m, self.anchor)
                led = self.ledgers.get(ent.id) or EntitlementLedger(ent)
                self.ledgers[ent.id] = led
                led.start_month(m, key, ent, v.id)
        for idx, seg in enumerate(priced):
            share = (lambda q, _i=idx: self._split(q, priced, _i)) if split else (lambda q: q)
            self._price_segment(m, seg, share, quantities, first=idx == 0)
        self._period_end_overage(m, last_version)
        self._adjustments(m, last_version)

    def _split(self, q: Decimal, priced: list[Segment], idx: int) -> Decimal:
        weights = [Decimal(s.span.days) for s in priced]
        scale = 0 if q == q.to_integral_value() else 4
        shares = allocate_weighted(q, weights, scale)
        return shares[idx]

    def _price_segment(
        self, m: Month, seg: Segment, share, quantities: Quantities, first: bool = True
    ) -> None:
        v = seg.version
        assert v is not None
        schedules = {r.id: r for r in v.rate_schedules}
        ents = {e.id: e for e in v.entitlements}
        vi = self.e.arrangement_versions.index(v)
        label = f"{seg.span.start.isoformat()}..{seg.span.end.isoformat()}"
        for ci, c in enumerate(v.components):
            path = pointer("engagement", "arrangement_versions", vi, "components", ci)
            cspan = DaySpan(c.effective_period.from_, c.effective_period.to or self.e.end_date)
            ov = overlap(cspan, seg.span)
            if ov is None:
                continue
            factor = Decimal(ov.days) / Decimal(month_span(m).days)
            kw = {"segment": label, "version": v.id}
            meth = c.calculation_method
            if meth == CalculationMethod.FIXED_RECURRING:
                base = self._fixed_month_amount(c, m)
                if base is None:
                    continue
                amt = base * factor
                self.fee(m, 4, c.id, c.id, "fixed", amt, f"{base} x {factor:.6f} of month", **kw)
            elif meth == CalculationMethod.FIXED_PROJECT:
                if first:
                    for p in c.payment_schedule:
                        if p.month == month_str(m):
                            self.fee(
                                m,
                                4,
                                c.id,
                                c.id,
                                "project_payment",
                                p.amount,
                                "scheduled project payment",
                                **kw,
                            )
            elif meth == CalculationMethod.DEDICATED_RESOURCE:
                for res in c.resources:
                    amt = res.fte * res.rate_per_fte_month * factor
                    self.fee(
                        m,
                        4,
                        c.id,
                        c.id,
                        "resource",
                        amt,
                        f"{res.fte} FTE x {res.rate_per_fte_month} x {factor:.6f}",
                        quantity=res.fte,
                        unit="FTE",
                        rate=res.rate_per_fte_month,
                        **kw,
                    )
            elif meth == CalculationMethod.TIME:
                base_name = c.quantity_source or ""
                for rr in c.role_rates:
                    hours = share(
                        self.qty(quantities, f"{base_name}.{rr.role}", m, path + "/quantity_source")
                    )
                    self.fee(
                        m,
                        4,
                        c.id,
                        c.id,
                        "time",
                        hours * rr.rate,
                        f"{hours} h x {rr.rate}",
                        quantity=hours,
                        unit="hours",
                        rate=rr.rate,
                        **kw,
                    )
            elif meth in (CalculationMethod.UNIT_OUTPUT, CalculationMethod.WEIGHTED_UNIT_OUTPUT):
                if meth == CalculationMethod.UNIT_OUTPUT:
                    q = share(self.qty(quantities, c.quantity_source, m, path + "/quantity_source"))
                else:
                    q = share(
                        self.weighted_qty(
                            quantities,
                            c.quantity_source or "",
                            c.weight_table_id,
                            m,
                            path + "/quantity_source",
                        )
                    )
                sched = schedules[c.rate_schedule_id]
                key = ("tier", sched.id, period_key(sched.accumulation_period, m, self.anchor))
                before = self.acc_add(key, q)
                amt = incremental(before, q, sched.tiers, sched.tier_method)
                self.fee(
                    m,
                    4,
                    c.id,
                    c.id,
                    "unit",
                    amt,
                    f"{sched.tier_method} schedule {sched.id} over units {before}..{before + q}",
                    quantity=q,
                    unit=c.unit,
                    **kw,
                )
            elif meth == CalculationMethod.ALLOWANCE_OVERAGE:
                ent = ents[c.entitlement_id]
                q = share(self.qty(quantities, c.quantity_source, m, path + "/quantity_source"))
                led = self.ledgers[ent.id]
                in_allow, excess = led.consume(m, q)
                sched = schedules[c.rate_schedule_id]
                elig_key = ("elig", sched.id, period_key(sched.accumulation_period, m, self.anchor))
                elig_before = self.acc_add(elig_key, q)
                if ent.overage_recognition == Recognition.PERIOD_END:
                    self.pending_overage[c.id] = self.pending_overage.get(c.id, ZERO) + excess
                    continue
                self._price_overage(m, c, sched, excess, elig_before + in_allow, **kw)
            else:
                self.issues.error(
                    "METHOD_NOT_SUPPORTED", f"{meth} is post-v1", path + "/calculation_method"
                )
                raise CometricError(self.issues)
        # indexation applies to this segment's priced lines
        for adj in v.adjustments:
            if adj.type != AdjustmentType.INDEXATION or adj.percent is None:
                continue
            years = (month_index(m) - month_index(self.anchor)) // 12
            if years <= 0:
                continue
            mult = (ONE + adj.percent) ** years - ONE
            for line in [
                ln
                for ln in self.fee_lines
                if ln.period == month_str(m)
                and ln.step == 4
                and ln.segment == label
                and ln.kind != "indexation"
            ]:
                if adj.applies_to and line.component not in adj.applies_to:
                    continue
                self.fee(
                    m,
                    4,
                    adj.id,
                    line.component,
                    "indexation",
                    line.amount * mult,
                    f"{line.amount} x ((1+{adj.percent})^{years} - 1)",
                    segment=label,
                    version=v.id,
                )

    def _price_overage(
        self, m: Month, c: FeeComponent, sched, excess: Decimal, elig_position: Decimal, **kw
    ) -> None:
        if sched.tier_scope == TierScope.EXCESS_ONLY:
            key = ("tier", sched.id, period_key(sched.accumulation_period, m, self.anchor))
            before = self.acc_add(key, excess)
            amt = incremental(before, excess, sched.tiers, sched.tier_method)
            formula = (
                f"{excess} excess units on {sched.tier_method} schedule {sched.id} from {before}"
            )
        else:
            amt = incremental(elig_position, excess, sched.tiers, sched.tier_method)
            formula = f"{excess} excess units priced at eligible positions {elig_position}..{elig_position + excess}"
        self.fee(m, 4, c.id, c.id, "overage", amt, formula, quantity=excess, unit=c.unit, **kw)

    def _period_end_overage(self, m: Month, v: ArrangementVersion) -> None:
        schedules = {r.id: r for r in v.rate_schedules}
        ents = {e.id: e for e in v.entitlements}
        for c in v.components:
            if c.calculation_method != CalculationMethod.ALLOWANCE_OVERAGE:
                continue
            ent = ents.get(c.entitlement_id or "")
            if ent is None or ent.overage_recognition != Recognition.PERIOD_END:
                continue
            if period_truncated(ent.accumulation_period, m, self.anchor, self.last, self.eng_last):
                self.issues.warn(
                    "TRUE_UP_OUTSIDE_HORIZON",
                    f"overage true-up for {c.id} falls after the horizon",
                    "",
                )
                continue
            if is_period_end(ent.accumulation_period, m, self.anchor, self.eng_last):
                pending = self.pending_overage.pop(c.id, ZERO)
                self._price_overage(
                    m, c, schedules[c.rate_schedule_id], pending, ZERO, version=v.id
                )

    def _fixed_month_amount(self, c: FeeComponent, m: Month) -> Decimal | None:
        amt = c.fixed_amount or ZERO
        start = month_of(c.effective_period.from_)
        idx = month_index(m) - month_index(start)
        if idx < 0:
            return None
        cad = c.charge_cadence
        if cad == ChargeCadence.MONTHLY:
            return amt
        if cad == ChargeCadence.QUARTERLY:
            return allocate_exact(amt, 3, self.scale)[(m[1] - 1) % 3]
        if cad == ChargeCadence.ANNUAL:
            return allocate_exact(amt, 12, self.scale)[idx % 12]
        if cad == ChargeCadence.ONE_TIME:
            return amt if idx == 0 else None
        return None

    # -- adjustments (steps 5 to 9) --------------------------------------------------------

    def _subtotal(
        self, m: Month, max_step: int, components: set[str] | None, include_unattributed: bool
    ) -> Decimal:
        ps = month_str(m)
        total = ZERO
        for ln in self.fee_lines:
            if ln.period != ps or ln.step > max_step:
                continue
            if ln.component is None:
                if include_unattributed:
                    total += ln.rounded
            elif components is None or ln.component in components:
                total += ln.rounded
        return total

    def _component_totals(self, m: Month, max_step: int) -> dict[str, Decimal]:
        ps = month_str(m)
        out: dict[str, Decimal] = {}
        for ln in self.fee_lines:
            if ln.period == ps and ln.step <= max_step and ln.component is not None:
                out[ln.component] = out.get(ln.component, ZERO) + ln.rounded
        return out

    def _adjustments(self, m: Month, v: ArrangementVersion) -> None:
        schedules = {r.id: r for r in v.rate_schedules}
        comps = {c.id: c for c in v.components}
        # step 5: collars
        for adj in v.adjustments:
            if adj.type != AdjustmentType.COLLAR:
                continue
            c = comps[adj.component_id]
            q = self.qty(self.quantities, c.quantity_source, m, "")
            base, alt = schedules[c.rate_schedule_id], schedules[adj.outside_rate_schedule_id]
            if adj.upper is not None and q > adj.upper:
                extra = q - adj.upper
                amt = price(extra, alt.tiers, alt.tier_method) - (
                    price(q, base.tiers, base.tier_method)
                    - price(adj.upper, base.tiers, base.tier_method)
                )
                self.fee(
                    m,
                    5,
                    adj.id,
                    c.id,
                    "collar",
                    amt,
                    f"{extra} units above band repriced on {alt.id}",
                    quantity=extra,
                )
            elif adj.lower is not None and q < adj.lower:
                amt = price(q, alt.tiers, alt.tier_method) - price(q, base.tiers, base.tier_method)
                self.fee(
                    m,
                    5,
                    adj.id,
                    c.id,
                    "collar",
                    amt,
                    f"{q} units below band repriced on {alt.id}",
                    quantity=q,
                )
        # step 6: discounts and rebates
        totals5 = self._component_totals(m, 5)
        for adj in v.adjustments:
            if adj.type == AdjustmentType.DISCOUNT and adj.percent is not None:
                for cid, amt in totals5.items():
                    if adj.applies_to and cid not in adj.applies_to:
                        continue
                    self.fee(
                        m, 6, adj.id, cid, "discount", -adj.percent * amt, f"-{adj.percent} x {amt}"
                    )
            elif adj.type == AdjustmentType.REBATE and adj.percent is not None:
                scope = set(adj.applies_to) if adj.applies_to else None
                key = ("rebate", adj.id, period_key(adj.accumulation_period, m, self.anchor))
                self.acc_add(key, self._subtotal(m, 5, scope, False))
                if is_period_end(adj.accumulation_period, m, self.anchor, self.eng_last):
                    period_total = self.acc[key]
                    if adj.threshold is None or period_total >= adj.threshold:
                        self.fee(
                            m,
                            6,
                            adj.id,
                            None,
                            "rebate",
                            -adj.percent * period_total,
                            f"-{adj.percent} x period subtotal {period_total}",
                        )
        # step 7: minimums tested gross or net of discounts
        for com in v.commitments:
            if (
                com.kind == CommitmentKind.MINIMUM_SPEND
                and com.tested_against != TestedAgainst.NET_OF_CREDITS
            ):
                self._minimum(m, com, v)
        # step 8: performance
        scope_all = None
        sub7 = self._subtotal(m, 7, scope_all, True)
        for adj in v.adjustments:
            if adj.type not in (
                AdjustmentType.SLA_CREDIT,
                AdjustmentType.BONUS,
                AdjustmentType.HOLDBACK,
            ):
                continue
            scope = set(adj.applies_to) if adj.applies_to else None
            base = self._subtotal(m, 7, scope, scope is None)
            trig = self.quantities.get(adj.trigger, m) if adj.trigger else None
            trig = trig if trig is not None else ZERO
            pct = adj.percent or ZERO
            if adj.type == AdjustmentType.HOLDBACK:
                released = min(trig, ONE)
                amt = -pct * base * (ONE - released)
                formula = f"-{pct} x {base} withheld unless released ({released})"
            else:
                raw = pct * base * trig
                if adj.cap_percent is not None:
                    raw = min(raw, adj.cap_percent * base)
                amt = -raw if adj.type == AdjustmentType.SLA_CREDIT else raw
                formula = f"{pct} x {base} x {trig} events, cap {adj.cap_percent}"
            if amt != 0:
                self.fee(m, 8, adj.id, None, adj.type.lower(), amt, formula)
        _ = sub7
        # step 7b: minimums tested net of credits
        for com in v.commitments:
            if (
                com.kind == CommitmentKind.MINIMUM_SPEND
                and com.tested_against == TestedAgainst.NET_OF_CREDITS
            ):
                self._minimum(m, com, v, step_basis=8)
        # step 9: caps
        for adj in v.adjustments:
            if adj.type != AdjustmentType.CAP or adj.amount is None:
                continue
            scope = set(adj.applies_to) if adj.applies_to else None
            month_total = self._subtotal(m, 8, scope, scope is None)
            key = ("cap", adj.id, period_key(adj.accumulation_period, m, self.anchor))
            before = self.acc_add(key, month_total)
            after = before + month_total
            reduction = max(ZERO, after - adj.amount) - max(ZERO, before - adj.amount)
            if reduction != 0:
                self.fee(
                    m,
                    9,
                    adj.id,
                    None,
                    "cap",
                    -reduction,
                    f"cap {adj.amount} per {adj.accumulation_period}; cumulative {after}",
                )

    def _minimum(self, m: Month, com, v: ArrangementVersion, step_basis: int | None = None) -> None:
        if com.aggregation_scope == AggregationScope.ENGAGEMENT:
            scope, unattributed = None, True
        elif com.aggregation_scope == AggregationScope.COMPONENT:
            scope, unattributed = set(com.component_ids), False
        else:
            scope, unattributed = (
                {c.id for c in v.components if c.service_id == com.service_id},
                False,
            )
        basis = step_basis or (5 if com.tested_against == TestedAgainst.GROSS else 6)
        tested = self._subtotal(m, basis, scope, unattributed)
        key = ("min", com.id, period_key(com.accumulation_period, m, self.anchor))
        if com.shortfall_rule == ShortfallRule.PER_SEGMENT:
            shortfall = max(ZERO, com.amount - tested)
            if shortfall > 0:
                self.fee(
                    m,
                    7,
                    com.id,
                    None,
                    "minimum_shortfall",
                    shortfall,
                    f"minimum {com.amount} - tested {tested}",
                )
            return
        self.acc_add(key, tested)
        if period_truncated(com.accumulation_period, m, self.anchor, self.last, self.eng_last):
            self.issues.warn(
                "TRUE_UP_OUTSIDE_HORIZON", f"minimum true-up for {com.id} falls after the horizon"
            )
            return
        if is_period_end(com.accumulation_period, m, self.anchor, self.eng_last):
            total = self.acc[key]
            shortfall = max(ZERO, com.amount - total)
            if shortfall > 0:
                self.fee(
                    m,
                    7,
                    com.id,
                    None,
                    "minimum_shortfall",
                    shortfall,
                    f"minimum {com.amount} - period total {total}",
                )

    # -- capacity -------------------------------------------------------------------------

    def _derive_demand_hours(self, quantities: Quantities) -> None:
        plan = self.e.delivery_plan
        if plan is None or not plan.production_standards:
            return
        for m in self.months:
            hours = ZERO
            for ps in plan.production_standards:
                name = f"{ps.unit}.{ps.band}" if ps.band else ps.unit
                q = quantities.get(name, m)
                if q is not None:
                    hours += q * ps.hours_per_unit
            quantities.set("demand_hours", m, hours)
        quantities.units["demand_hours"] = "hours"

    def _breach_mode(self) -> BreachMode | None:
        if self.s.breach_mode is not None:
            return self.s.breach_mode
        return self.e.delivery_plan.breach_mode if self.e.delivery_plan else None

    def _capacity(self, m: Month, quantities: Quantities) -> None:
        plan = self.e.delivery_plan
        if plan is None:
            return
        mode = self._breach_mode()
        for li, lim in enumerate(plan.capacity):
            st = self.capacity_state.setdefault(
                lim.id,
                {
                    "demand": ZERO,
                    "served": ZERO,
                    "overflow": ZERO,
                    "capacity": ZERO,
                    "periods": set(),
                },
            )
            key = period_key(lim.accumulation_period, m, self.anchor)
            if key not in st["periods"]:
                st["periods"].add(key)
                st["capacity"] += lim.amount
            base = quantities.get(lim.quantity, m)
            if base is None:
                self.issues.error(
                    "MISSING_ASSUMPTION",
                    f"capacity {lim.id} measures {lim.quantity!r}, which the scenario does not provide",
                    pointer("engagement", "delivery_plan", "capacity", li, "quantity"),
                )
                raise CometricError(self.issues)
            carried = self.backlog.get(lim.id, ZERO)
            demand = base + carried
            acc_key = ("cap_use", lim.id, key)
            before = self.acc.get(acc_key, ZERO)
            over = max(ZERO, before + demand - lim.amount) - max(ZERO, before - lim.amount)
            st["demand"] += base
            if over <= 0:
                self.acc[acc_key] = before + demand
                st["served"] += demand
                self.backlog[lim.id] = ZERO
                if carried:
                    quantities.set(lim.quantity, m, demand)
                continue
            if mode == BreachMode.OVERFLOW_COST:
                self.acc[acc_key] = before + demand
                st["served"] += demand
                st["overflow"] += over
                self.overflow[(lim.id, m)] = over
                if lim.overflow_cost_rate is None:
                    self.issues.error(
                        "OVERFLOW_RATE_REQUIRED",
                        f"capacity {lim.id} breached under OVERFLOW_COST but has no overflow_cost_rate",
                        pointer(
                            "engagement", "delivery_plan", "capacity", li, "overflow_cost_rate"
                        ),
                    )
                    raise CometricError(self.issues)
                self.issues.warn(
                    "CAPACITY_BREACH",
                    f"{month_str(m)}: {over} {lim.quantity} above capacity {lim.id}; overflow cost applied",
                    "",
                    month=month_str(m),
                    overflow=str(over),
                    mode="OVERFLOW_COST",
                )
            elif mode == BreachMode.BACKLOG:
                served = demand - over
                self.acc[acc_key] = before + served
                st["served"] += served
                self.backlog[lim.id] = over
                quantities.set(lim.quantity, m, served)
                self.issues.warn(
                    "CAPACITY_BREACH",
                    f"{month_str(m)}: {over} {lim.quantity} carried as backlog; SLA risk",
                    "",
                    month=month_str(m),
                    backlog=str(over),
                    mode="BACKLOG",
                )
            else:
                self.acc[acc_key] = before + demand
                st["served"] += demand
                st["overflow"] += over
                self.feasible = False
                self.issues.error(
                    "CAPACITY_BREACH",
                    f"{month_str(m)}: demand exceeds capacity {lim.id} by {over} and no breach handling is declared"
                    if mode is None
                    else f"{month_str(m)}: demand exceeds capacity {lim.id} by {over}; scenario infeasible",
                    "",
                    month=month_str(m),
                    overflow=str(over),
                    mode=str(mode) if mode else None,
                )

    # -- costs ----------------------------------------------------------------------------

    def _layer(self, cc: CostComponent) -> MarginLayer:
        assert self.policy is not None
        return self.policy.mapping[cc.category]

    def _driver(self, quantities: Quantities, driver: str | None, m: Month, path: str) -> Decimal:
        if driver is None:
            self.issues.error("DRIVER_REQUIRED", "variable cost needs a driver", path)
            raise CometricError(self.issues)
        if driver.startswith("weighted:"):
            rest = driver[len("weighted:") :]
            base, _, table = rest.partition(":")
            return self.weighted_qty(quantities, base, table or None, m, path)
        return self.qty(quantities, driver, m, path)

    def _costs_for_month(self, m: Month, quantities: Quantities) -> None:
        plan = self.e.delivery_plan
        if plan is None or self.policy is None:
            return
        ps = month_str(m)
        replaced: dict[str, Decimal] = {}
        for lim in plan.capacity:
            over = self.overflow.get((lim.id, m), ZERO)
            for cid in lim.overflow_replaces:
                replaced[cid] = replaced.get(cid, ZERO) + over
        for ci, cc in enumerate(plan.cost_components):
            path = pointer("engagement", "delivery_plan", "cost_components", ci)
            if cc.effective_period is not None:
                cs = DaySpan(cc.effective_period.from_, cc.effective_period.to or self.e.end_date)
                if overlap(cs, month_span(m)) is None:
                    continue
            layer = self._layer(cc)
            unavoidable = cc.avoidability == Avoidability.UNAVOIDABLE
            b = cc.behavior
            if b == CostBehavior.FIXED:
                amt = self._fixed_cost_month(cc, m)
                self._cost(ps, cc, layer, amt, f"fixed {cc.amount} per {cc.period}", unavoidable)
            elif b == CostBehavior.VARIABLE:
                q = self._driver(quantities, cc.driver, m, path + "/driver")
                over = replaced.get(cc.id, ZERO)
                self._cost(
                    ps,
                    cc,
                    layer,
                    (q - over) * (cc.rate or ZERO),
                    f"{q - over} x {cc.rate}",
                    unavoidable,
                    q - over,
                )
                if over > 0:
                    lim = next(lm for lm in plan.capacity if cc.id in lm.overflow_replaces)
                    self.cost_lines.append(
                        CostLine(
                            ps,
                            f"{lim.id}:overflow",
                            str(cc.category),
                            layer,
                            over * lim.overflow_cost_rate,
                            self.r(over * lim.overflow_cost_rate),
                            f"{over} overflow x {lim.overflow_cost_rate}",
                            driver_quantity=over,
                            unavoidable=unavoidable,
                        )
                    )
            elif b == CostBehavior.STEP:
                q = self._driver(quantities, cc.driver, m, path + "/driver")
                steps = Decimal(math.ceil(q / cc.step_size)) if cc.step_size else ZERO
                self._cost(
                    ps,
                    cc,
                    layer,
                    steps * (cc.step_cost or ZERO),
                    f"ceil({q}/{cc.step_size}) x {cc.step_cost}",
                    unavoidable,
                    q,
                )
            elif b == CostBehavior.TIERED_VARIABLE:
                q = self._driver(quantities, cc.driver, m, path + "/driver")
                key = ("ctier", cc.id, period_key(cc.accumulation_period, m, self.anchor))
                before = self.acc_add(key, q)
                from .enums import TierMethod

                amt = incremental(before, q, cc.tiers, TierMethod.MARGINAL)
                self._cost(
                    ps,
                    cc,
                    layer,
                    amt,
                    f"marginal tiers over {before}..{before + q}",
                    unavoidable,
                    q,
                )
            elif b == CostBehavior.ONE_TIME:
                inc, amo = self._one_time(cc, m)
                view = self.policy.transition_view
                amt = amo if view == TransitionView.AMORTIZED else inc
                if inc != 0 or amo != 0:
                    line = self._cost(
                        ps, cc, layer, amt, f"one-time cost ({view.lower()} view)", unavoidable
                    )
                    line.incurred, line.amortized = self.r(inc), self.r(amo)

    def _cost(
        self,
        ps: str,
        cc: CostComponent,
        layer: MarginLayer,
        amt: Decimal,
        formula: str,
        unavoidable: bool,
        q: Decimal | None = None,
    ) -> CostLine:
        line = CostLine(
            ps,
            cc.id,
            str(cc.category),
            layer,
            amt,
            self.r(amt),
            formula,
            unavoidable=unavoidable,
            driver_quantity=q,
        )
        self.cost_lines.append(line)
        return line

    def _fixed_cost_month(self, cc: CostComponent, m: Month) -> Decimal:
        amt = cc.amount or ZERO
        if cc.period == CostPeriod.MONTHLY:
            return amt
        anchor = month_of(cc.effective_period.from_) if cc.effective_period else self.anchor
        idx = month_index(m) - month_index(anchor)
        if cc.period == CostPeriod.ANNUAL:
            return allocate_exact(amt, 12, self.scale)[idx % 12]
        term_months = months_between(self.anchor, self.eng_last)
        return allocate_exact(amt, len(term_months), self.scale)[
            month_index(m) - month_index(self.anchor)
        ]

    def _one_time(self, cc: CostComponent, m: Month) -> tuple[Decimal, Decimal]:
        schedule = [(ln.month, ln.amount) for ln in cc.incurred_schedule] or [
            (month_str(self.anchor), cc.amount or ZERO)
        ]
        inc = ZERO
        amo = ZERO
        for month_text, amount in schedule:
            y, mo = month_text.split("-")
            start = (int(y), int(mo))
            if start == m:
                inc += amount
            n = cc.amortize_months or 1
            offset = month_index(m) - month_index(start)
            if 0 <= offset < n:
                amo += allocate_exact(amount, n, self.scale)[offset]
        return inc, amo

    # -- aggregation ----------------------------------------------------------------------

    def _month_totals(self, m: Month) -> dict:
        ps = month_str(m)
        fees = [ln for ln in self.fee_lines if ln.period == ps]
        costs = [ln for ln in self.cost_lines if ln.period == ps]

        def tot(values) -> Decimal:
            s = sum(values, ZERO)
            if self.money.rounding_level == RoundingLevel.PERIOD_TOTAL:
                return quantize(s, self.scale, str(self.money.rounding_mode))
            return s

        layers = {layer: tot(c.rounded for c in costs if c.layer == layer) for layer in MarginLayer}
        incurred_adj = sum(
            ((c.incurred - c.rounded) for c in costs if c.incurred is not None), ZERO
        )
        return {
            "period": ps,
            "contractual_fee": tot(f.rounded for f in fees),
            "overage_fee": tot(f.rounded for f in fees if f.kind == "overage"),
            "commitment_shortfall": tot(f.rounded for f in fees if f.kind == "minimum_shortfall"),
            "layers": layers,
            "unavoidable_direct_cost": tot(
                c.rounded for c in costs if c.layer == MarginLayer.DIRECT_DELIVERY and c.unavoidable
            ),
            "by_category": _group(costs),
            "incurred_adjustment": incurred_adj,
        }

    def _aggregate(self, per_month: dict[Month, dict], quantities: Quantities) -> dict:
        periods = []
        cumulative = ZERO
        cumulative_incurred = ZERO
        payback = None
        first_one_time = self._first_one_time_month()
        went_negative = False
        for m in self.months:
            t = per_month[m]
            metrics = _metrics(t)
            cumulative += metrics["contribution_profit"]
            cumulative_incurred += metrics["contribution_profit"] - t["incurred_adjustment"]
            metrics["cumulative_contribution"] = cumulative
            metrics["cumulative_contribution_incurred"] = cumulative_incurred
            periods.append(metrics)
            if first_one_time is not None and month_index(m) >= month_index(first_one_time):
                if cumulative_incurred < 0:
                    went_negative = True
                elif payback is None and went_negative:
                    payback = month_str(m)
        years: dict[str, dict] = {}
        for y in sorted({m[0] for m in self.months}):
            years[str(y)] = _sum_metrics(
                [p for p, m in zip(periods, self.months, strict=True) if m[0] == y]
            )
        term = _sum_metrics(periods)
        term["transition_payback_month"] = payback
        self._client_metrics(term, quantities)
        return {"periods": periods, "years": years, "term": term}

    def _first_one_time_month(self) -> Month | None:
        plan = self.e.delivery_plan
        if plan is None:
            return None
        months = []
        for cc in plan.cost_components:
            if cc.behavior == CostBehavior.ONE_TIME:
                for ln in cc.incurred_schedule or []:
                    y, mo = ln.month.split("-")
                    months.append((int(y), int(mo)))
                if not cc.incurred_schedule:
                    months.append(self.anchor)
        return min(months) if months else None

    def client_value_quantity(self) -> str | None:
        if self.e.client_value_unit:
            return self.e.client_value_unit
        for v in self.e.arrangement_versions:
            for c in v.components:
                if (
                    c.calculation_method
                    in (CalculationMethod.UNIT_OUTPUT, CalculationMethod.ALLOWANCE_OVERAGE)
                    and c.quantity_source
                ):
                    return c.quantity_source.removeprefix("scenario.")
                if (
                    c.calculation_method == CalculationMethod.WEIGHTED_UNIT_OUTPUT
                    and c.quantity_source
                ):
                    return (
                        "weighted:"
                        + c.quantity_source.removeprefix("scenario.")
                        + (f":{c.weight_table_id}" if c.weight_table_id else "")
                    )
        return None

    def _client_metrics(self, term: dict, quantities: Quantities) -> None:
        name = self.client_value_quantity()
        total_q = None
        if name:
            if name.startswith("weighted:"):
                rest = name[len("weighted:") :]
                base, _, table = rest.partition(":")
                try:
                    total_q = sum(
                        (
                            self.weighted_qty(quantities, base, table or None, m, "")
                            for m in self.months
                        ),
                        ZERO,
                    )
                except CometricError:
                    total_q = None
            elif quantities.has(name):
                total_q = sum((quantities.get(name, m) or ZERO for m in self.months), ZERO)
        fee = term["contractual_fee"]
        cost = term["direct_delivery_cost"] + term["engagement_avoidable_cost"]
        term["client_value_quantity"] = name
        term["client_consumed_quantity"] = total_q
        term["effective_client_unit_price"] = (
            safe_ratio(fee, total_q) if total_q is not None else None
        )
        term["cost_per_unit"] = safe_ratio(cost, total_q) if total_q is not None else None
        term["unit_contribution"] = (
            safe_ratio(term["contribution_profit"], total_q) if total_q is not None else None
        )
        # commitment utilization (CHI-001) across entitlement grants
        granted = sum((led.granted() for led in self.ledgers.values()), ZERO)
        consumed = sum((led.consumed() for led in self.ledgers.values()), ZERO)
        term["allowance_granted"] = granted if self.ledgers else None
        term["allowance_consumed"] = consumed if self.ledgers else None
        term["commitment_utilization"] = safe_ratio(consumed, granted) if self.ledgers else None
        # capacity (CHI-003, CHI-011)
        cap = []
        for lim_id, st in self.capacity_state.items():
            cap.append(
                {
                    "id": lim_id,
                    "demand": st["demand"],
                    "served": st["served"],
                    "capacity": st["capacity"],
                    "overflow": st["overflow"],
                    "backlog_end": self.backlog.get(lim_id, ZERO),
                    "capacity_utilization": safe_ratio(st["served"], st["capacity"]),
                    "capacity_service_mismatch": st["capacity"] - st["demand"],
                }
            )
        term["capacity"] = cap
        plan = self.e.delivery_plan
        if plan and plan.roles:
            months = Decimal(len(self.months))
            productive = sum(
                (
                    r.fte * r.available_hours_per_fte_year * r.productive_ratio * months / 12
                    for r in plan.roles
                ),
                ZERO,
            )
            safe = None
            if all(r.safe_utilization_ceiling is not None for r in plan.roles):
                safe = sum(
                    (
                        r.fte
                        * r.available_hours_per_fte_year
                        * r.productive_ratio
                        * r.safe_utilization_ceiling
                        * months
                        / 12
                        for r in plan.roles
                    ),
                    ZERO,
                )
            hours_name = plan.demand_hours_source or (
                "demand_hours" if quantities.has("demand_hours") else None
            )
            used = (
                quantities.total(hours_name) if hours_name and quantities.has(hours_name) else None
            )
            term["productive_hours"] = productive
            term["safe_capacity_hours"] = safe
            term["demand_hours"] = used
            term["productive_hours_utilization"] = (
                safe_ratio(used, productive) if used is not None else None
            )
            term["effective_client_price_per_used_hour"] = safe_ratio(fee, used) if used else None
            if safe is not None and used is not None and used > safe:
                self.issues.warn(
                    "SAFE_CAPACITY_EXCEEDED", f"demand hours {used} exceed safe capacity {safe}"
                )


def _group(costs: list[CostLine]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for c in costs:
        out[c.category] = out.get(c.category, ZERO) + c.rounded
    return out


def _metrics(t: dict) -> dict:
    fee = t["contractual_fee"]
    L = t["layers"]
    direct = L[MarginLayer.DIRECT_DELIVERY]
    avoid = L[MarginLayer.ENGAGEMENT_AVOIDABLE]
    gp = fee - direct
    cp = gp - avoid
    return {
        "period": t.get("period"),
        "contractual_fee": fee,
        "overage_fee": t["overage_fee"],
        "commitment_shortfall": t["commitment_shortfall"],
        "direct_delivery_cost": direct,
        "engagement_avoidable_cost": avoid,
        "portfolio_shared_cost": L[MarginLayer.PORTFOLIO_SHARED],
        "corporate_overhead_cost": L[MarginLayer.CORPORATE_OVERHEAD],
        "unavoidable_direct_cost": t["unavoidable_direct_cost"],
        "costs_by_category": t["by_category"],
        "gross_profit": gp,
        "contribution_profit": cp,
        "full_cost_profit": cp
        - L[MarginLayer.PORTFOLIO_SHARED]
        - L[MarginLayer.CORPORATE_OVERHEAD],
        "gross_margin": safe_ratio(gp, fee),
        "contribution_margin": safe_ratio(cp, fee),
        "incurred_adjustment": t["incurred_adjustment"],
    }


SUM_KEYS = [
    "contractual_fee",
    "overage_fee",
    "commitment_shortfall",
    "direct_delivery_cost",
    "engagement_avoidable_cost",
    "portfolio_shared_cost",
    "corporate_overhead_cost",
    "unavoidable_direct_cost",
    "gross_profit",
    "contribution_profit",
    "full_cost_profit",
]


def _sum_metrics(periods: list[dict]) -> dict:
    out: dict = {k: sum((p[k] for p in periods), ZERO) for k in SUM_KEYS}
    cats: dict[str, Decimal] = {}
    for p in periods:
        for k, v in p["costs_by_category"].items():
            cats[k] = cats.get(k, ZERO) + v
    out["costs_by_category"] = cats
    out["gross_margin"] = safe_ratio(out["gross_profit"], out["contractual_fee"])
    out["contribution_margin"] = safe_ratio(out["contribution_profit"], out["contractual_fee"])
    out["months"] = len(periods)
    if out["contractual_fee"] == 0:
        out["margin_note"] = "Contractual fee is zero, so margins are undefined."
    return out
