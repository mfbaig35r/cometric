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
    OutcomeDirection,
    OutcomeForm,
    ProrationPolicy,
    Recognition,
    RoundingLevel,
    ShortfallRule,
    TerminationRule,
    TestedAgainst,
    ThresholdScope,
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
    contract_year,
    first_day,
    is_period_end,
    last_day,
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

ENGINE_VERSION = "0.3.0"

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
    full_month: bool = False  # True when a FULL_MONTH_FROM_* policy gave this version the month


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
        # A terminated scenario ends the engagement early; the original term still governs how
        # declared totals are spread and how many later minimum periods REMAINDER_DUE owes.
        self.orig_last = month_of(engagement.end_date)
        self.termination = scenario.termination_date
        self.end_date = (
            min(engagement.end_date, self.termination) if self.termination else engagement.end_date
        )
        self.eng_last = month_of(self.end_date)
        self.unamortized_written_off = ZERO
        hz_from = scenario.horizon.from_ if scenario.horizon else engagement.start_date
        hz_to = scenario.horizon.to if scenario.horizon else engagement.end_date
        self.anchor_day = engagement.start_date.day
        self.first = max(month_of(hz_from), self.anchor)
        self.last = min(month_of(hz_to), self.eng_last)
        # Reported months are the horizon. Simulation always starts at the engagement start so
        # allowances, tiers, minimums, caps, and outcome periods carry into the horizon.
        self.months = months_between(self.first, self.last)
        self.sim_months = months_between(self.anchor, self.last)
        self.reported = set(self.months)
        self.posted_once: set[tuple] = set()
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

    def pk(self, period, m: Month) -> tuple:
        return period_key(period, m, self.anchor, self.anchor_day)

    def is_end(self, period, m: Month) -> bool:
        return is_period_end(period, m, self.anchor, self.eng_last, self.anchor_day)

    def truncated(self, period, m: Month) -> bool:
        return period_truncated(period, m, self.anchor, self.last, self.eng_last, self.anchor_day)

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
            min(v.effective_to or self.end_date, self.end_date),
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
        filled: list[list] = []
        cursor = ms.start
        for span, v in raw:
            if span.start > cursor:
                filled.append(
                    [
                        DaySpan(cursor, span.start.fromordinal(span.start.toordinal() - 1)),
                        None,
                        False,
                    ]
                )
            filled.append([span, v, False])
            cursor = span.end.fromordinal(span.end.toordinal() + 1)
        if cursor <= ms.end:
            filled.append([DaySpan(cursor, ms.end), None, False])
        # apply proration policy at each mid-month boundary
        i = 1
        while i < len(filled):
            (sa, va, fa), (sb, vb, fb) = filled[i - 1], filled[i]
            policy = (vb.proration_policy if vb else None) or (va.proration_policy if va else None)
            if va is vb:
                filled[i - 1 : i + 1] = [[DaySpan(sa.start, sb.end), va, fa or fb]]
                continue
            if policy == ProrationPolicy.FULL_MONTH_FROM_NEXT:
                filled[i - 1 : i + 1] = [[DaySpan(sa.start, sb.end), va, True]]
                continue
            if policy == ProrationPolicy.FULL_MONTH_FROM_CURRENT:
                filled[i - 1 : i + 1] = [[DaySpan(sa.start, sb.end), vb, True]]
                continue
            i += 1
        dim = Decimal(ms.days)
        return [Segment(span, v, Decimal(span.days) / dim, full) for span, v, full in filled]

    # -- run ------------------------------------------------------------------------------

    def run(self) -> CalculationResult:
        term_months = months_between(self.anchor, self.orig_last)
        quantities = build_quantities(self.e, self.s, term_months, self.issues)
        if self.issues.has_errors:
            raise CometricError(self.issues)
        self.quantities = quantities
        self._check_triggers(quantities)
        self._check_termination()
        if self.first > self.anchor:
            pre = [m for m in self.sim_months if m not in self.reported]
            has_pre = any(
                quantities.values.get(n, {}).get(m) for n in quantities.values for m in pre
            )
            if has_pre:
                self.issues.info(
                    "PRE_HORIZON_SIMULATED",
                    f"months before the horizon ({month_str(pre[0])} to {month_str(pre[-1])}) were simulated so allowances, tiers, minimums, caps, and outcome periods carry into it; they are not reported",
                )
            else:
                self.issues.warn(
                    "PRE_HORIZON_QUANTITIES_MISSING",
                    f"the horizon starts after the engagement does, and the scenario has no quantities for {month_str(pre[0])} to {month_str(pre[-1])}; accumulators start the horizon as if nothing was consumed before it",
                    "/scenario/horizon",
                )
        plan = self.e.delivery_plan
        if plan is not None and plan.standard_rate_card:
            base = (plan.worked_hours_source or "").removeprefix("scenario.")
            if not base or not any(
                quantities.has(f"{base}.{rr.role}") for rr in plan.standard_rate_card
            ):
                self.issues.error(
                    "MISSING_ASSUMPTION",
                    f"a standard rate card needs worked hours as scenario quantities {base or '<worked_hours_source>'}.<role>",
                    pointer("engagement", "delivery_plan", "worked_hours_source"),
                )
                raise CometricError(self.issues)
        self._derive_demand_hours(quantities)
        per_month: dict[Month, dict] = {}
        for m in self.sim_months:
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
        reported = {month_str(m) for m in self.months}
        self.fee_lines = [ln for ln in self.fee_lines if ln.period in reported]
        self.cost_lines = [ln for ln in self.cost_lines if ln.period in reported]
        ledger = [
            e.as_dict()
            for led in self.ledgers.values()
            for e in led.entries
            if e.period in reported
        ]
        status = "ok" if self.feasible else "infeasible"
        result = CalculationResult(
            data, self.fee_lines, self.cost_lines, ledger, self.issues, self.feasible, status
        )
        if self.termination:
            last = month_str(self.eng_last)
            lines = [ln for ln in self.fee_lines if ln.period == last]
            result.extras["termination"] = {
                "date": self.termination,
                "original_end_date": self.e.end_date,
                "months_run": len(months_between(self.anchor, self.eng_last)),
                "months_not_run": len(months_between(self.eng_last, self.orig_last)) - 1,
                "minimum_charges": sum(
                    (ln.rounded for ln in lines if ln.kind == "minimum_shortfall"), ZERO
                ),
                "termination_fee": sum(
                    (ln.rounded for ln in lines if ln.kind == "termination_fee"), ZERO
                ),
                "unamortized_written_off": self.unamortized_written_off,
            }
        return result

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
                key = self.pk(ent.accumulation_period, m)
                led = self.ledgers.get(ent.id) or EntitlementLedger(ent)
                self.ledgers[ent.id] = led
                led.start_month(m, key, ent, v.id)
        for idx, seg in enumerate(priced):
            share = (lambda q, _i=idx: self._split(q, priced, _i)) if split else (lambda q: q)
            self._price_segment(m, seg, share, quantities)
        self._period_end_overage(m, last_version)
        self._period_end_outcome(m, last_version)
        self._indexation(m)
        self._adjustments(m, last_version)
        if self.termination and m == self.eng_last and last_version.termination_fee:
            self.fee(
                m,
                9,
                "termination_fee",
                None,
                "termination_fee",
                last_version.termination_fee,
                f"termination fee on {self.termination.isoformat()}",
                version=last_version.id,
            )

    def _split(self, q: Decimal, priced: list[Segment], idx: int) -> Decimal:
        weights = [Decimal(s.span.days) for s in priced]
        scale = 0 if q == q.to_integral_value() else 4
        shares = allocate_weighted(q, weights, scale)
        return shares[idx]

    def _price_segment(self, m: Month, seg: Segment, share, quantities: Quantities) -> None:
        v = seg.version
        assert v is not None
        schedules = {r.id: r for r in v.rate_schedules}
        ents = {e.id: e for e in v.entitlements}
        vi = self.e.arrangement_versions.index(v)
        label = f"{seg.span.start.isoformat()}..{seg.span.end.isoformat()}"
        # Components are processed in id order so results never depend on list order (the
        # fingerprint sorts components), e.g. when two components draw on one entitlement.
        for ci, c in sorted(enumerate(v.components), key=lambda t: t[1].id):
            path = pointer("engagement", "arrangement_versions", vi, "components", ci)
            cspan = DaySpan(c.effective_period.from_, c.effective_period.to or self.end_date)
            if seg.full_month:
                # FULL_MONTH_FROM_* gives the version the whole month: component dates inside the
                # month snap to it, so the component is either in for the month or out.
                if overlap(cspan, month_span(m)) is None:
                    continue
                factor = ONE
            else:
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
                cad = c.charge_cadence
                if cad == ChargeCadence.ONE_TIME:
                    if (c.id, "one_time") in self.posted_once:
                        continue
                    self.posted_once.add((c.id, "one_time"))
                    self.fee(m, 4, c.id, c.id, "fixed", base, "one-time fee", **kw)
                    continue
                # Monthly amounts prorate by the component's days; quarterly and annual shares are
                # anchored at the component start and keep their declared total, so they prorate
                # only by the version's share of a split month.
                f = (
                    factor
                    if cad == ChargeCadence.MONTHLY
                    else (ONE if seg.full_month else seg.factor)
                )
                self.fee(m, 4, c.id, c.id, "fixed", base * f, f"{base} x {f:.6f} of month", **kw)
            elif meth == CalculationMethod.FIXED_PROJECT:
                if (c.id, m) not in self.posted_once:
                    self.posted_once.add((c.id, m))
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
                key = ("tier", sched.id, self.pk(sched.accumulation_period, m))
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
                elig_key = ("elig", sched.id, self.pk(sched.accumulation_period, m))
                elig_before = self.acc_add(elig_key, q)
                if ent.overage_recognition == Recognition.PERIOD_END:
                    self.pending_overage[c.id] = self.pending_overage.get(c.id, ZERO) + excess
                    continue
                self._price_overage(m, c, sched, excess, elig_before + in_allow, **kw)
            elif meth == CalculationMethod.OUTCOME_ADJUSTMENT:
                o = c.outcome
                measured = share(self.qty(quantities, o.metric, m, path + "/outcome/metric"))
                self.acc_add(("outcome", c.id, self.pk(o.accumulation_period, m)), measured)
            else:
                self.issues.error(
                    "METHOD_NOT_SUPPORTED", f"{meth} is post-v1", path + "/calculation_method"
                )
                raise CometricError(self.issues)

    INDEXABLE_KINDS = ("fixed", "resource", "time", "unit", "overage")

    def _indexation(self, m: Month) -> None:
        """Indexation from the second contract year on every rate-based or recurring step-4 line,
        including period-end overage. Fixed project payments and outcome fees are not indexed."""
        years = contract_year(m, self.anchor, self.anchor_day)
        if years <= 0:
            return
        ps = month_str(m)
        versions = {v.id: v for v in self.e.arrangement_versions}
        for line in [
            ln
            for ln in self.fee_lines
            if ln.period == ps and ln.step == 4 and ln.kind in self.INDEXABLE_KINDS
        ]:
            v = versions.get(line.version or "")
            if v is None:
                continue
            for adj in v.adjustments:
                if adj.type != AdjustmentType.INDEXATION or adj.percent is None:
                    continue
                if adj.applies_to and line.component not in adj.applies_to:
                    continue
                mult = (ONE + adj.percent) ** years - ONE
                self.fee(
                    m,
                    4,
                    adj.id,
                    line.component,
                    "indexation",
                    line.amount * mult,
                    f"{line.amount} x ((1+{adj.percent})^{years} - 1)",
                    segment=line.segment,
                    version=v.id,
                )

    def _price_overage(
        self, m: Month, c: FeeComponent, sched, excess: Decimal, elig_position: Decimal, **kw
    ) -> None:
        if sched.tier_scope == TierScope.EXCESS_ONLY:
            key = ("tier", sched.id, self.pk(sched.accumulation_period, m))
            before = self.acc_add(key, excess)
            amt = incremental(before, excess, sched.tiers, sched.tier_method)
            formula = (
                f"{excess} excess units on {sched.tier_method} schedule {sched.id} from {before}"
            )
        else:
            amt = incremental(elig_position, excess, sched.tiers, sched.tier_method)
            formula = f"{excess} excess units priced at eligible positions {elig_position}..{elig_position + excess}"
        self.fee(m, 4, c.id, c.id, "overage", amt, formula, quantity=excess, unit=c.unit, **kw)

    def _period_end_outcome(self, m: Month, v: ArrangementVersion) -> None:
        """Outcome fees are measured over the accumulation period and charged at its end."""
        for c in v.components:
            if c.calculation_method != CalculationMethod.OUTCOME_ADJUSTMENT or c.outcome is None:
                continue
            o = c.outcome
            if self.ends_early(o.accumulation_period, m):
                self.issues.warn(
                    "TERMINATED_MID_PERIOD",
                    f"outcome fee for {c.id} is not charged: termination cuts its measurement period short; the contract decides what is owed",
                )
                continue
            if self.truncated(o.accumulation_period, m):
                self.issues.warn(
                    "TRUE_UP_OUTSIDE_HORIZON",
                    f"outcome fee for {c.id} is measured after the horizon",
                )
                continue
            if not self.is_end(o.accumulation_period, m):
                continue
            total = self.acc.get(("outcome", c.id, self.pk(o.accumulation_period, m)), ZERO)
            higher = o.direction == OutcomeDirection.HIGHER_IS_BETTER
            if o.form == OutcomeForm.SHARE:
                improvement = (total - o.baseline) if higher else (o.baseline - total)
                fee = o.share_percent * o.attribution_percent * max(ZERO, improvement)
                formula = f"{o.share_percent} share x {o.attribution_percent} attributed x max(0, improvement {improvement} vs baseline {o.baseline})"
            elif o.form == OutcomeForm.SUCCESS:
                met = total >= o.target if higher else total <= o.target
                fee = o.success_amount if met else ZERO
                formula = f"success amount {o.success_amount} if {o.metric} {total} {'>=' if higher else '<='} target {o.target}: {'met' if met else 'not met'}"
            else:
                fee = o.share_percent * o.attribution_percent * max(ZERO, total)
                formula = (
                    f"{o.share_percent} x {o.attribution_percent} attributed x outcome {total}"
                )
            if o.cap_amount is not None and fee > o.cap_amount:
                formula += f"; capped at {o.cap_amount}"
                fee = o.cap_amount
            self.fee(
                m, 4, c.id, c.id, "outcome", fee, formula, quantity=total, unit=o.unit, version=v.id
            )

    def _period_end_overage(self, m: Month, v: ArrangementVersion) -> None:
        schedules = {r.id: r for r in v.rate_schedules}
        ents = {e.id: e for e in v.entitlements}
        for c in v.components:
            if c.calculation_method != CalculationMethod.ALLOWANCE_OVERAGE:
                continue
            ent = ents.get(c.entitlement_id or "")
            if ent is None or ent.overage_recognition != Recognition.PERIOD_END:
                continue
            if self.truncated(ent.accumulation_period, m):
                self.issues.warn(
                    "TRUE_UP_OUTSIDE_HORIZON",
                    f"overage true-up for {c.id} falls after the horizon",
                    "",
                )
                continue
            if self.is_end(ent.accumulation_period, m):
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
            return allocate_exact(amt, 3, self.scale)[idx % 3]
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
            if c.calculation_method == CalculationMethod.WEIGHTED_UNIT_OUTPUT:
                q = self.weighted_qty(
                    self.quantities, c.quantity_source or "", c.weight_table_id, m, ""
                )
            else:
                q = self.qty(self.quantities, c.quantity_source, m, "")
            base, alt = schedules[c.rate_schedule_id], schedules[adj.outside_rate_schedule_id]
            # Step 4 priced this month's units at the schedule's cumulative position; remove the
            # same amount it charged for the repriced units, not a price measured from zero.
            after = self.acc.get(("tier", base.id, self.pk(base.accumulation_period, m)), q)
            before = after - q
            if adj.upper is not None and q > adj.upper:
                extra = q - adj.upper
                charged = price(before + q, base.tiers, base.tier_method) - price(
                    before + adj.upper, base.tiers, base.tier_method
                )
                amt = price(extra, alt.tiers, alt.tier_method) - charged
                self.fee(
                    m,
                    5,
                    adj.id,
                    c.id,
                    "collar",
                    amt,
                    f"{extra} units above band: remove {charged}, reprice on {alt.id}",
                    quantity=extra,
                )
            elif adj.lower is not None and q < adj.lower:
                charged = price(before + q, base.tiers, base.tier_method) - price(
                    before, base.tiers, base.tier_method
                )
                amt = price(q, alt.tiers, alt.tier_method) - charged
                self.fee(
                    m,
                    5,
                    adj.id,
                    c.id,
                    "collar",
                    amt,
                    f"{q} units below band: remove {charged}, reprice on {alt.id}",
                    quantity=q,
                )
        # step 6: discounts and rebates
        totals5 = self._component_totals(m, 5)
        for adj in v.adjustments:
            if adj.type == AdjustmentType.DISCOUNT and adj.percent is not None:
                in_scope = {
                    cid: amt
                    for cid, amt in totals5.items()
                    if not adj.applies_to or cid in adj.applies_to
                }
                if adj.threshold is None:
                    for cid, amt in in_scope.items():
                        self.fee(
                            m,
                            6,
                            adj.id,
                            cid,
                            "discount",
                            -adj.percent * amt,
                            f"-{adj.percent} x {amt}",
                        )
                    continue
                # Threshold discount, recognized cumulatively over its accumulation period: the
                # month that crosses the threshold takes any catch-up for the whole subtotal.
                month_total = sum(in_scope.values(), ZERO)
                key = ("discount", adj.id, self.pk(adj.accumulation_period, m))
                before = self.acc_add(key, month_total)
                after = before + month_total
                eligible = self._threshold_eligible(adj)
                # Round cumulatively so monthly discounts add up exactly to the period discount,
                # then split each month's amount across components without losing a cent.
                mode = str(self.money.rounding_mode)
                discount = quantize(adj.percent * eligible(after), self.scale, mode) - quantize(
                    adj.percent * eligible(before), self.scale, mode
                )
                if discount == 0 or month_total <= 0:
                    continue
                ids = list(in_scope)
                weights = [max(in_scope[cid], ZERO) for cid in ids]
                if sum(weights, ZERO) > 0:
                    shares = allocate_weighted(abs(discount), weights, self.scale)
                    shares = [x if discount > 0 else -x for x in shares]
                else:
                    shares = [discount * in_scope[cid] / month_total for cid in ids]
                for cid, share in zip(ids, shares, strict=True):
                    if share == 0:
                        continue
                    self.fee(
                        m,
                        6,
                        adj.id,
                        cid,
                        "discount",
                        -share,
                        f"-{adj.percent} x {adj.threshold_scope} above threshold {adj.threshold}; period subtotal {before} -> {after}",
                    )
            elif adj.type == AdjustmentType.REBATE and adj.percent is not None:
                scope = set(adj.applies_to) if adj.applies_to else None
                key = ("rebate", adj.id, self.pk(adj.accumulation_period, m))
                self.acc_add(key, self._subtotal(m, 5, scope, False))
                if self.ends_early(adj.accumulation_period, m):
                    self.issues.warn(
                        "TERMINATED_MID_PERIOD",
                        f"rebate {adj.id} is not settled: termination cuts its period short; the contract decides what is owed",
                    )
                elif self.truncated(adj.accumulation_period, m):
                    self.issues.warn(
                        "TRUE_UP_OUTSIDE_HORIZON", f"rebate {adj.id} is settled after the horizon"
                    )
                elif self.is_end(adj.accumulation_period, m):
                    period_total = self.acc[key]
                    base = (
                        period_total
                        if adj.threshold is None
                        else self._threshold_eligible(adj)(period_total)
                    )
                    if base > 0:
                        self.fee(
                            m,
                            6,
                            adj.id,
                            None,
                            "rebate",
                            -adj.percent * base,
                            f"-{adj.percent} x {base} (period subtotal {period_total}"
                            + (
                                f", {adj.threshold_scope} above {adj.threshold})"
                                if adj.threshold is not None
                                else ")"
                            ),
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
            key = ("cap", adj.id, self.pk(adj.accumulation_period, m))
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

    @staticmethod
    def _threshold_eligible(adj):
        """Amount a percentage applies to, given a cumulative subtotal x and the threshold scope."""
        t = adj.threshold
        if adj.threshold_scope == ThresholdScope.EXCESS_ONLY:
            return lambda x: max(ZERO, x - t)
        return lambda x: x if x >= t else ZERO

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
        key = ("min", com.id, self.pk(com.accumulation_period, m))
        if com.shortfall_rule == ShortfallRule.PER_SEGMENT:
            if (
                self.termination
                and m == self.eng_last
                and com.termination_rule == TerminationRule.REMAINDER_DUE
            ):
                later = len(self._later_period_keys(com.accumulation_period))
                if later:
                    self.fee(
                        m,
                        7,
                        com.id,
                        None,
                        "minimum_shortfall",
                        com.amount * later,
                        f"REMAINDER_DUE: {later} later periods x {com.amount}",
                    )
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
        if self.ends_early(com.accumulation_period, m):
            self._minimum_at_termination(m, com, key)
            return
        if self.truncated(com.accumulation_period, m):
            self.issues.warn(
                "TRUE_UP_OUTSIDE_HORIZON", f"minimum true-up for {com.id} falls after the horizon"
            )
            return
        if self.is_end(com.accumulation_period, m):
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
        if (
            self.termination
            and m == self.eng_last
            and com.termination_rule == TerminationRule.REMAINDER_DUE
        ):
            # termination on a period's natural end: later periods are still owed
            later = len(self._later_period_keys(com.accumulation_period))
            if later:
                self.fee(
                    m,
                    7,
                    com.id,
                    None,
                    "minimum_shortfall",
                    com.amount * later,
                    f"REMAINDER_DUE: {later} later periods x {com.amount}",
                )

    # -- termination ----------------------------------------------------------------------

    def ends_early(self, period, m: Month) -> bool:
        """True in the termination month when termination cuts this accumulation period short."""
        if not self.termination or m != self.eng_last:
            return False
        _start, end = self._period_bounds(period, m)
        return self.termination < end

    def _period_bounds(self, period, m: Month):
        """First and last day of m's accumulation period within the ORIGINAL term."""
        key = self.pk(period, m)
        months = [
            x for x in months_between(self.anchor, self.orig_last) if self.pk(period, x) == key
        ]
        start = max(first_day(months[0]), self.e.start_date)
        end = min(last_day(months[-1]), self.e.end_date)
        return start, end

    def _later_period_keys(self, period) -> list:
        current = self.pk(period, self.eng_last)
        later = []
        for x in months_between(self.eng_last, self.orig_last):
            k = self.pk(period, x)
            if k != current and k not in later:
                later.append(k)
        return later

    def _minimum_at_termination(self, m: Month, com, key) -> None:
        rule = com.termination_rule
        total = self.acc[key]
        if rule == TerminationRule.WAIVED:
            self.issues.info(
                "MINIMUM_WAIVED_ON_TERMINATION", f"minimum {com.id} is waived on termination"
            )
            return
        if rule == TerminationRule.PRORATE:
            start, end = self._period_bounds(com.accumulation_period, m)
            fraction = Decimal((self.termination - start).days + 1) / Decimal(
                (end - start).days + 1
            )
            required = com.amount * fraction
            shortfall = max(ZERO, required - total)
            if shortfall > 0:
                self.fee(
                    m,
                    7,
                    com.id,
                    None,
                    "minimum_shortfall",
                    shortfall,
                    f"PRORATE: minimum {com.amount} x {fraction:.6f} of period - period total {total}",
                )
            return
        later = self._later_period_keys(com.accumulation_period)
        current = max(ZERO, com.amount - total)
        owed = current + com.amount * len(later)
        if owed > 0:
            self.fee(
                m,
                7,
                com.id,
                None,
                "minimum_shortfall",
                owed,
                f"REMAINDER_DUE: {current} for this period + {len(later)} later periods x {com.amount}",
            )

    def _check_termination(self) -> None:
        if not self.termination:
            return
        for vi, v in enumerate(self.e.arrangement_versions):
            for ci, com in enumerate(v.commitments):
                if com.kind == CommitmentKind.MINIMUM_SPEND and com.termination_rule is None:
                    self.issues.error(
                        "TERMINATION_RULE_REQUIRED",
                        f"scenario terminates on {self.termination.isoformat()}, but minimum {com.id} has no termination_rule (PRORATE, REMAINDER_DUE, or WAIVED)",
                        pointer(
                            "engagement",
                            "arrangement_versions",
                            vi,
                            "commitments",
                            ci,
                            "termination_rule",
                        ),
                    )
        if self.issues.has_errors:
            raise CometricError(self.issues)

    # -- capacity -------------------------------------------------------------------------

    def _check_triggers(self, quantities: Quantities) -> None:
        """A performance trigger the scenario does not provide is an error, never a silent 0."""
        for vi, v in enumerate(self.e.arrangement_versions):
            for ai, adj in enumerate(v.adjustments):
                if adj.type not in (
                    AdjustmentType.SLA_CREDIT,
                    AdjustmentType.BONUS,
                    AdjustmentType.HOLDBACK,
                ):
                    continue
                if adj.trigger and not quantities.has(adj.trigger.removeprefix("scenario.")):
                    self.issues.error(
                        "MISSING_ASSUMPTION",
                        f'{adj.type} {adj.id} is triggered by {adj.trigger!r}, which the scenario does not provide; give it explicitly (for example "0" for TERM)',
                        pointer(
                            "engagement", "arrangement_versions", vi, "adjustments", ai, "trigger"
                        ),
                    )
        if self.issues.has_errors:
            raise CometricError(self.issues)

    def _derive_demand_hours(self, quantities: Quantities) -> None:
        plan = self.e.delivery_plan
        if plan is None or not plan.production_standards:
            return
        for m in self.sim_months:
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
            fresh = {
                "demand": ZERO,
                "served": ZERO,
                "overflow": ZERO,
                "capacity": ZERO,
                "periods": set(),
            }
            real = self.capacity_state.setdefault(lim.id, dict(fresh, periods=set()))
            # months before the horizon carry the accumulators but are not reported
            st = real if m in self.reported else fresh
            key = self.pk(lim.accumulation_period, m)
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
                cs = DaySpan(cc.effective_period.from_, cc.effective_period.to or self.end_date)
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
                key = ("ctier", cc.id, self.pk(cc.accumulation_period, m))
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
        start = (
            max(month_of(cc.effective_period.from_), self.anchor)
            if cc.effective_period
            else self.anchor
        )
        if cc.period == CostPeriod.ANNUAL:
            return allocate_exact(amt, 12, self.scale)[(month_index(m) - month_index(start)) % 12]
        # TERM: spread over the months the cost is in effect, so its declared total is kept
        end = self.orig_last
        if cc.effective_period and cc.effective_period.to:
            end = min(month_of(cc.effective_period.to), self.eng_last)
        active = months_between(start, end)
        return allocate_exact(amt, len(active), self.scale)[month_index(m) - month_index(start)]

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
            shares = allocate_exact(amount, n, self.scale)
            if 0 <= offset < n:
                amo += shares[offset]
            if self.termination and m == self.eng_last and offset < n - 1:
                remaining = sum(shares[max(offset + 1, 0) :], ZERO)
                amo += remaining
                self.unamortized_written_off += remaining
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
        in_contribution = (MarginLayer.DIRECT_DELIVERY, MarginLayer.ENGAGEMENT_AVOIDABLE)
        incurred_adj = sum(
            (
                (c.incurred - c.rounded)
                for c in costs
                if c.incurred is not None and c.layer in in_contribution
            ),
            ZERO,
        )
        worked, standard = self._worked_and_standard(m)
        return {
            "period": ps,
            "contractual_fee": tot(f.rounded for f in fees),
            "overage_fee": tot(f.rounded for f in fees if f.kind == "overage"),
            "outcome_fee": tot(f.rounded for f in fees if f.kind == "outcome"),
            "worked_hours": worked,
            "standard_value": standard,
            "commitment_shortfall": tot(f.rounded for f in fees if f.kind == "minimum_shortfall"),
            "layers": layers,
            "unavoidable_direct_cost": tot(
                c.rounded for c in costs if c.layer == MarginLayer.DIRECT_DELIVERY and c.unavoidable
            ),
            "by_category": _group(costs),
            "incurred_adjustment": incurred_adj,
        }

    def _worked_and_standard(self, m: Month) -> tuple[Decimal, Decimal]:
        """Hours worked and their value at standard rates (spec 3.4 realization prerequisite)."""
        plan = self.e.delivery_plan
        if plan is None or not plan.standard_rate_card or not plan.worked_hours_source:
            return ZERO, ZERO
        base = plan.worked_hours_source.removeprefix("scenario.")
        hours = ZERO
        value = ZERO
        for rr in plan.standard_rate_card:
            h = self.quantities.get(f"{base}.{rr.role}", m) or ZERO
            hours += h
            value += h * rr.rate
        return hours, quantize(value, self.scale, str(self.money.rounding_mode))

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

    def priced_quantities(self) -> list[tuple[str, str | None]]:
        """Distinct (quantity name, unit) pairs priced by output components."""
        found: dict[str, str | None] = {}
        for v in self.e.arrangement_versions:
            for c in v.components:
                if not c.quantity_source:
                    continue
                if c.calculation_method in (
                    CalculationMethod.UNIT_OUTPUT,
                    CalculationMethod.ALLOWANCE_OVERAGE,
                ):
                    found.setdefault(c.quantity_source.removeprefix("scenario."), c.unit)
                elif c.calculation_method == CalculationMethod.WEIGHTED_UNIT_OUTPUT:
                    name = (
                        "weighted:"
                        + c.quantity_source.removeprefix("scenario.")
                        + (f":{c.weight_table_id}" if c.weight_table_id else "")
                    )
                    found.setdefault(name, c.unit)
        return list(found.items())

    def client_value_quantity(self) -> str | None:
        """The quantity behind effective client unit price; None when it would be ambiguous."""
        if self.e.client_value_unit:
            return self.e.client_value_unit
        priced = self.priced_quantities()
        return priced[0][0] if len(priced) == 1 else None

    def _quantity_total(self, name: str, quantities: Quantities) -> Decimal | None:
        if name.startswith("weighted:"):
            base, _, table = name[len("weighted:") :].partition(":")
            try:
                return sum(
                    (
                        self.weighted_qty(quantities, base, table or None, m, "")
                        for m in self.months
                    ),
                    ZERO,
                )
            except CometricError:
                return None
        if quantities.has(name):
            return sum((quantities.get(name, m) or ZERO for m in self.months), ZERO)
        return None

    def _client_metrics(self, term: dict, quantities: Quantities) -> None:
        name = self.client_value_quantity()
        total_q = None
        priced = self.priced_quantities()
        if name is None and len(priced) > 1:
            listed = ", ".join(f"{n} ({u})" for n, u in priced)
            self.issues.warn(
                "AMBIGUOUS_UNIT_PRICE",
                f"several unit types are priced ({listed}); effective client unit price, cost per unit, and unit contribution are not reported. Set client_value_unit to one quantity, or join commensurable ones with +.",
                "/engagement/client_value_unit",
            )
        if name:
            parts = [p.strip() for p in name.split("+")]
            totals = [self._quantity_total(p, quantities) for p in parts]
            total_q = None if any(t is None for t in totals) else sum(totals, ZERO)
            units = {quantities.units.get(p) for p in parts if not p.startswith("weighted:")}
            if len(parts) > 1 and len(units) > 1:
                self.issues.warn(
                    "MIXED_UNITS_IN_PRICE",
                    f"client_value_unit sums quantities in different units ({sorted(u for u in units if u)}); the unit price treats them as one unit",
                    "/engagement/client_value_unit",
                )
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
        "outcome_fee": t["outcome_fee"],
        "commitment_shortfall": t["commitment_shortfall"],
        "worked_hours": t["worked_hours"],
        "standard_value": t["standard_value"],
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
    "outcome_fee",
    "worked_hours",
    "standard_value",
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
    if out["standard_value"] > 0:
        out["realization"] = safe_ratio(out["contractual_fee"], out["standard_value"])
        out["write_down"] = out["standard_value"] - out["contractual_fee"]
    else:
        out["realization"] = None
        out["write_down"] = None
    out["effective_billing_rate"] = (
        safe_ratio(out["contractual_fee"], out["worked_hours"]) if out["worked_hours"] > 0 else None
    )
    out["months"] = len(periods)
    if out["contractual_fee"] == 0:
        out["margin_note"] = "Contractual fee is zero, so margins are undefined."
    return out
