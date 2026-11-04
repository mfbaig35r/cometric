"""Input models: engagements, arrangements, delivery, scenarios, and policies (spec 3, 4, 5, 6)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AccumulationPeriod,
    AdjustmentType,
    AggregationScope,
    Avoidability,
    BillingBasis,
    BreachMode,
    CalculationMethod,
    ChargeCadence,
    ClassificationAuthority,
    CommitmentKind,
    CostBehavior,
    CostCategory,
    CostPeriod,
    Distribution,
    MarginLayer,
    Origin,
    PartyRole,
    ProrationPolicy,
    Recognition,
    RiskBearer,
    RolloverPolicy,
    RoundingLevel,
    RoundingMode,
    ShortfallRule,
    TestedAgainst,
    TierMethod,
    TierScope,
    Topology,
    TransitionView,
    UnitKind,
)
from .money import Dec

SCHEMA_VERSION = "0.2"
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


def _check_month(value: str) -> str:
    if not MONTH_RE.match(value):
        raise ValueError(f"expected a month as YYYY-MM, got {value!r}")
    return value


Month = Annotated[str, AfterValidator(_check_month)]


# --- money and packs ---------------------------------------------------------------------


class MoneyPolicy(Model):
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    rounding_scale: int | None = Field(default=None, ge=0, le=6)
    rounding_level: RoundingLevel = RoundingLevel.LINE_ITEM


class PackRef(Model):
    id: str
    version: str | None = None


# --- parties, units, services ------------------------------------------------------------


class Party(Model):
    id: str
    role: PartyRole
    provider_type: str | None = None
    jurisdiction: str | None = None
    regulated_status: str | None = None


class UnitDefinition(Model):
    code: str
    kind: UnitKind = UnitKind.COUNT
    name: str | None = None
    counting_rule: str | None = None
    acceptance_rule: str | None = None
    exclusions: list[str] = []


class WeightBand(Model):
    code: str
    weight: Dec
    criteria: str | None = None


class ComplexityWeightTable(Model):
    id: str
    raw_unit: str
    weighted_unit: str
    bands: list[WeightBand] = Field(min_length=1)
    classification_authority: ClassificationAuthority
    audit_rule: str | None = None


class Service(Model):
    id: str
    unit_definition_id: str
    service_category: str | None = None
    scope: str | None = None


# --- arrangement -------------------------------------------------------------------------


class EffectivePeriod(Model):
    from_: date = Field(alias="from")
    to: date | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Tier(Model):
    from_: Dec = Field(alias="from")
    to: Dec | None = None
    rate: Dec

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RateSchedule(Model):
    id: str
    currency: str
    unit: str
    tier_method: TierMethod = TierMethod.MARGINAL
    tier_scope: TierScope = TierScope.ALL_ELIGIBLE
    accumulation_period: AccumulationPeriod = AccumulationPeriod.MONTH
    tiers: list[Tier] = Field(min_length=1)


class RoleRate(Model):
    role: str
    rate: Dec


class ResourceLine(Model):
    role: str
    fte: Dec
    rate_per_fte_month: Dec


class PaymentLine(Model):
    month: Month
    amount: Dec


class FeeComponent(Model):
    id: str
    service_id: str
    calculation_method: CalculationMethod
    billing_basis: BillingBasis
    charge_cadence: ChargeCadence
    currency: str
    quantity_source: str | None = None
    unit: str | None = None
    effective_period: EffectivePeriod
    depends_on: list[str] = []
    fixed_amount: Dec | None = None
    rate_schedule_id: str | None = None
    entitlement_id: str | None = None
    weight_table_id: str | None = None
    role_rates: list[RoleRate] = []
    resources: list[ResourceLine] = []
    project_fee: Dec | None = None
    payment_schedule: list[PaymentLine] = []


class Rollover(Model):
    policy: RolloverPolicy = RolloverPolicy.NONE
    ceiling: Dec | None = None


class Entitlement(Model):
    id: str
    granted_by: str
    unit: str
    included_quantity: Dec
    accumulation_period: AccumulationPeriod
    overage_recognition: Recognition
    rollover: Rollover = Rollover()


class Commitment(Model):
    id: str
    kind: CommitmentKind
    amount: Dec
    aggregation_scope: AggregationScope = AggregationScope.ENGAGEMENT
    component_ids: list[str] = []
    service_id: str | None = None
    accumulation_period: AccumulationPeriod
    tested_against: TestedAgainst
    shortfall_rule: ShortfallRule


class Adjustment(Model):
    id: str
    type: AdjustmentType
    applies_to: list[str] = []
    percent: Dec | None = None
    amount: Dec | None = None
    cap_percent: Dec | None = None
    trigger: str | None = None
    threshold: Dec | None = None
    accumulation_period: AccumulationPeriod = AccumulationPeriod.MONTH
    component_id: str | None = None
    lower: Dec | None = None
    upper: Dec | None = None
    outside_rate_schedule_id: str | None = None


class ArrangementVersion(Model):
    id: str
    effective_from: date
    effective_to: date | None = None
    supersedes_id: str | None = None
    retroactive: bool = False
    proration_policy: ProrationPolicy | None = None
    adjustment_order: Literal["DEFAULT"] = "DEFAULT"
    components: list[FeeComponent] = Field(min_length=1)
    entitlements: list[Entitlement] = []
    rate_schedules: list[RateSchedule] = []
    commitments: list[Commitment] = []
    adjustments: list[Adjustment] = []


# --- delivery and cost -------------------------------------------------------------------


class CostTier(Model):
    from_: Dec = Field(alias="from")
    to: Dec | None = None
    rate: Dec

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class IncurredLine(Model):
    month: Month
    amount: Dec


class CostComponent(Model):
    id: str
    category: CostCategory
    behavior: CostBehavior
    amount: Dec | None = None
    period: CostPeriod | None = None
    driver: str | None = None
    rate: Dec | None = None
    step_size: Dec | None = None
    step_cost: Dec | None = None
    tiers: list[CostTier] = []
    accumulation_period: AccumulationPeriod = AccumulationPeriod.MONTH
    incurred_schedule: list[IncurredLine] = []
    amortize_months: int | None = Field(default=None, ge=1)
    dedicated: bool = True
    avoidability: Avoidability = Avoidability.UNKNOWN
    origin: Origin = Origin.ESTIMATED
    effective_period: EffectivePeriod | None = None


class CapacityLimit(Model):
    id: str
    quantity: str
    amount: Dec
    accumulation_period: AccumulationPeriod
    overflow_cost_rate: Dec | None = None
    overflow_replaces: list[str] = []


class ResourceRole(Model):
    role: str
    fte: Dec
    available_hours_per_fte_year: Dec
    productive_ratio: Dec = Decimal(1)
    safe_utilization_ceiling: Dec | None = None


class ProductionStandard(Model):
    unit: str
    hours_per_unit: Dec
    role: str | None = None
    band: str | None = None
    origin: Origin = Origin.ESTIMATED


class DeliveryPlan(Model):
    topology: Topology | None = None
    breach_mode: BreachMode | None = None
    capacity: list[CapacityLimit] = []
    roles: list[ResourceRole] = []
    production_standards: list[ProductionStandard] = []
    demand_hours_source: str | None = None
    cost_components: list[CostComponent] = []


class RiskAllocation(Model):
    risk_type: Literal["VOLUME", "COST", "PERFORMANCE", "SCOPE", "TECHNOLOGY", "EFFORT", "CAPACITY"]
    declared_bearer: RiskBearer
    driver: str | None = None
    note: str | None = None


class Engagement(Model):
    schema_version: Literal["0.2"]
    engagement_id: str
    name: str | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    start_date: date
    end_date: date
    packs: list[PackRef] = []
    money_policy: MoneyPolicy | None = None
    parties: list[Party] = []
    unit_definitions: list[UnitDefinition] = Field(min_length=1)
    weight_tables: list[ComplexityWeightTable] = []
    services: list[Service] = Field(min_length=1)
    arrangement_versions: list[ArrangementVersion] = Field(min_length=1)
    delivery_plan: DeliveryPlan | None = None
    risk_allocations: list[RiskAllocation] = []
    descriptors: dict[str, str] = {}
    client_value_unit: str | None = None


# --- scenarios and policies --------------------------------------------------------------


class Horizon(Model):
    from_: date = Field(alias="from")
    to: date

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Assumption(Model):
    name: str
    value: Dec
    unit: str
    time_period: str
    origin: Origin
    distribution: Distribution = Distribution.FLAT
    profile: list[Dec] = []

    @field_validator("time_period")
    @classmethod
    def _period(cls, v: str) -> str:
        if (
            v == "TERM"
            or MONTH_RE.match(v)
            or re.match(r"^\d{4}$", v)
            or re.match(r"^\d{4}-(0[1-9]|1[0-2])\.\.\d{4}-(0[1-9]|1[0-2])$", v)
        ):
            return v
        raise ValueError("time_period must be YYYY-MM, YYYY, YYYY-MM..YYYY-MM, or TERM")


class Scenario(Model):
    id: str
    horizon: Horizon | None = None
    assumptions: list[Assumption] = []
    breach_mode: BreachMode | None = None
    probability_label: str | None = None
    deviation_driver: str | None = None


class CostPolicy(Model):
    id: str
    version: str = "1"
    owner: str | None = None
    mapping: dict[CostCategory, MarginLayer]
    transition_view: TransitionView = TransitionView.INCURRED


class TolerancePolicy(Model):
    provider_relative: Dec = Field(description="Fraction of base contribution treated as adverse")
    client_relative: Dec = Field(description="Fraction of base unit price treated as adverse")


REFERENCE_COST_POLICY = CostPolicy(
    id="reference",
    version="0.2",
    owner="cometric",
    mapping={
        CostCategory.DEDICATED_LABOR: MarginLayer.DIRECT_DELIVERY,
        CostCategory.POOLED_LABOR: MarginLayer.DIRECT_DELIVERY,
        CostCategory.DELIVERY_MANAGEMENT: MarginLayer.DIRECT_DELIVERY,
        CostCategory.QA_REWORK: MarginLayer.DIRECT_DELIVERY,
        CostCategory.AI_INFERENCE: MarginLayer.DIRECT_DELIVERY,
        CostCategory.PLATFORM_OPERATIONS: MarginLayer.DIRECT_DELIVERY,
        CostCategory.THIRD_PARTY: MarginLayer.DIRECT_DELIVERY,
        CostCategory.CLIENT_IMPLEMENTATION: MarginLayer.ENGAGEMENT_AVOIDABLE,
        CostCategory.TRANSITION: MarginLayer.ENGAGEMENT_AVOIDABLE,
        CostCategory.ENGAGEMENT_OVERHEAD: MarginLayer.ENGAGEMENT_AVOIDABLE,
        CostCategory.REUSABLE_ENGINEERING: MarginLayer.PORTFOLIO_SHARED,
        CostCategory.IDLE_POOLED_CAPACITY: MarginLayer.PORTFOLIO_SHARED,
        CostCategory.CORPORATE_OVERHEAD: MarginLayer.CORPORATE_OVERHEAD,
    },
    transition_view=TransitionView.AMORTIZED,
)

BUILTIN_COST_POLICIES = {"reference": REFERENCE_COST_POLICY}
