"""Core controlled vocabularies. Domain vocabulary lives in packs (P-09)."""

from __future__ import annotations

from enum import StrEnum


class BillingBasis(StrEnum):
    TIME = "TIME"
    RESOURCE = "RESOURCE"
    CAPACITY = "CAPACITY"
    OUTPUT = "OUTPUT"
    USAGE = "USAGE"
    FIXED = "FIXED"
    COST = "COST"
    OUTCOME = "OUTCOME"


class ChargeCadence(StrEnum):
    ONE_TIME = "ONE_TIME"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"
    EVENT = "EVENT"
    USAGE_TRIGGERED = "USAGE_TRIGGERED"


class CalculationMethod(StrEnum):
    FIXED_RECURRING = "FIXED_RECURRING"
    TIME = "TIME"
    DEDICATED_RESOURCE = "DEDICATED_RESOURCE"
    UNIT_OUTPUT = "UNIT_OUTPUT"
    WEIGHTED_UNIT_OUTPUT = "WEIGHTED_UNIT_OUTPUT"
    ALLOWANCE_OVERAGE = "ALLOWANCE_OVERAGE"
    FIXED_PROJECT = "FIXED_PROJECT"
    COST_PLUS = "COST_PLUS"
    OUTCOME_ADJUSTMENT = "OUTCOME_ADJUSTMENT"


POST_V1_METHODS = {CalculationMethod.COST_PLUS}

METHOD_BASES: dict[CalculationMethod, set[BillingBasis]] = {
    CalculationMethod.FIXED_RECURRING: {BillingBasis.FIXED, BillingBasis.CAPACITY},
    CalculationMethod.TIME: {BillingBasis.TIME},
    CalculationMethod.DEDICATED_RESOURCE: {BillingBasis.RESOURCE},
    CalculationMethod.UNIT_OUTPUT: {BillingBasis.OUTPUT, BillingBasis.USAGE},
    CalculationMethod.WEIGHTED_UNIT_OUTPUT: {BillingBasis.OUTPUT},
    CalculationMethod.ALLOWANCE_OVERAGE: {BillingBasis.OUTPUT, BillingBasis.USAGE},
    CalculationMethod.FIXED_PROJECT: {BillingBasis.FIXED},
    CalculationMethod.COST_PLUS: {BillingBasis.COST},
    CalculationMethod.OUTCOME_ADJUSTMENT: {BillingBasis.OUTCOME},
}

FIXED_METHODS = {
    CalculationMethod.FIXED_RECURRING,
    CalculationMethod.FIXED_PROJECT,
    CalculationMethod.DEDICATED_RESOURCE,
}


class TierMethod(StrEnum):
    MARGINAL = "MARGINAL"
    ALL_UNITS = "ALL_UNITS"
    GRADUATED_BLOCK = "GRADUATED_BLOCK"


class TierScope(StrEnum):
    ALL_ELIGIBLE = "ALL_ELIGIBLE"
    EXCESS_ONLY = "EXCESS_ONLY"


class AccumulationPeriod(StrEnum):
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"
    CONTRACT_YEAR = "CONTRACT_YEAR"
    TERM = "TERM"


class Recognition(StrEnum):
    CUMULATIVE = "CUMULATIVE"
    PERIOD_END = "PERIOD_END"
    PER_SEGMENT = "PER_SEGMENT"


class RolloverPolicy(StrEnum):
    NONE = "NONE"
    NEXT_PERIOD = "NEXT_PERIOD"
    TERM = "TERM"


class CommitmentKind(StrEnum):
    MINIMUM_SPEND = "MINIMUM_SPEND"
    MINIMUM_VOLUME = "MINIMUM_VOLUME"
    RESERVED_CAPACITY = "RESERVED_CAPACITY"
    PREPAID_CREDIT = "PREPAID_CREDIT"


class AggregationScope(StrEnum):
    COMPONENT = "COMPONENT"
    SERVICE = "SERVICE"
    ENGAGEMENT = "ENGAGEMENT"


class TestedAgainst(StrEnum):
    GROSS = "GROSS"
    NET_OF_DISCOUNTS = "NET_OF_DISCOUNTS"
    NET_OF_CREDITS = "NET_OF_CREDITS"


class ShortfallRule(StrEnum):
    PERIOD_END_TRUE_UP = "PERIOD_END_TRUE_UP"
    PER_SEGMENT = "PER_SEGMENT"


class AdjustmentType(StrEnum):
    DISCOUNT = "DISCOUNT"
    REBATE = "REBATE"
    COLLAR = "COLLAR"
    SLA_CREDIT = "SLA_CREDIT"
    HOLDBACK = "HOLDBACK"
    BONUS = "BONUS"
    CAP = "CAP"
    INDEXATION = "INDEXATION"


class ProrationPolicy(StrEnum):
    CALENDAR_DAYS = "CALENDAR_DAYS"
    FULL_MONTH_FROM_NEXT = "FULL_MONTH_FROM_NEXT"
    FULL_MONTH_FROM_CURRENT = "FULL_MONTH_FROM_CURRENT"


class RoundingMode(StrEnum):
    HALF_UP = "HALF_UP"
    HALF_EVEN = "HALF_EVEN"


class RoundingLevel(StrEnum):
    LINE_ITEM = "LINE_ITEM"
    PERIOD_TOTAL = "PERIOD_TOTAL"


class UnitKind(StrEnum):
    COUNT = "COUNT"
    WEIGHTED = "WEIGHTED"
    HOURS = "HOURS"
    FTE_MONTHS = "FTE_MONTHS"
    METER = "METER"


class CostBehavior(StrEnum):
    FIXED = "FIXED"
    VARIABLE = "VARIABLE"
    STEP = "STEP"
    TIERED_VARIABLE = "TIERED_VARIABLE"
    ONE_TIME = "ONE_TIME"


class CostPeriod(StrEnum):
    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"
    TERM = "TERM"


class MarginLayer(StrEnum):
    DIRECT_DELIVERY = "DIRECT_DELIVERY"
    ENGAGEMENT_AVOIDABLE = "ENGAGEMENT_AVOIDABLE"
    PORTFOLIO_SHARED = "PORTFOLIO_SHARED"
    CORPORATE_OVERHEAD = "CORPORATE_OVERHEAD"


class CostCategory(StrEnum):
    DEDICATED_LABOR = "DEDICATED_LABOR"
    POOLED_LABOR = "POOLED_LABOR"
    DELIVERY_MANAGEMENT = "DELIVERY_MANAGEMENT"
    QA_REWORK = "QA_REWORK"
    AI_INFERENCE = "AI_INFERENCE"
    PLATFORM_OPERATIONS = "PLATFORM_OPERATIONS"
    THIRD_PARTY = "THIRD_PARTY"
    CLIENT_IMPLEMENTATION = "CLIENT_IMPLEMENTATION"
    REUSABLE_ENGINEERING = "REUSABLE_ENGINEERING"
    TRANSITION = "TRANSITION"
    ENGAGEMENT_OVERHEAD = "ENGAGEMENT_OVERHEAD"
    IDLE_POOLED_CAPACITY = "IDLE_POOLED_CAPACITY"
    CORPORATE_OVERHEAD = "CORPORATE_OVERHEAD"


class Avoidability(StrEnum):
    AVOIDABLE = "AVOIDABLE"
    UNAVOIDABLE = "UNAVOIDABLE"
    UNKNOWN = "UNKNOWN"


class TransitionView(StrEnum):
    INCURRED = "INCURRED"
    AMORTIZED = "AMORTIZED"


class BreachMode(StrEnum):
    OVERFLOW_COST = "OVERFLOW_COST"
    BACKLOG = "BACKLOG"
    INFEASIBLE = "INFEASIBLE"


class Topology(StrEnum):
    DEDICATED = "DEDICATED"
    POOLED = "POOLED"
    HYBRID = "HYBRID"


class Origin(StrEnum):
    OBSERVED = "OBSERVED"
    CONTRACTED = "CONTRACTED"
    ESTIMATED = "ESTIMATED"
    ILLUSTRATIVE = "ILLUSTRATIVE"
    INTERNAL_POLICY = "INTERNAL_POLICY"


class Distribution(StrEnum):
    FLAT = "FLAT"
    PROFILE = "PROFILE"


class RiskBearer(StrEnum):
    CLIENT = "CLIENT"
    PROVIDER = "PROVIDER"
    SHARED = "SHARED"
    THIRD_PARTY = "THIRD_PARTY"
    NONE_ADVERSE = "NONE_ADVERSE"


class PartyRole(StrEnum):
    CLIENT = "CLIENT"
    PROVIDER = "PROVIDER"
    SUBCONTRACTOR = "SUBCONTRACTOR"


class ClassificationAuthority(StrEnum):
    PROVIDER = "PROVIDER"
    CLIENT = "CLIENT"
    JOINT = "JOINT"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ERROR = "ERROR"


class EvidenceClass(StrEnum):
    A_DIRECT = "A_DIRECT"
    B_CORROBORATED = "B_CORROBORATED"
    C_INFERENCE = "C_INFERENCE"
    D_PROPOSED = "D_PROPOSED"


class Prevalence(StrEnum):
    ESTABLISHED_COMMON = "ESTABLISHED_COMMON"
    DOCUMENTED_SPECIALIZED = "DOCUMENTED_SPECIALIZED"
    EMERGING = "EMERGING"
    UNVERIFIED = "UNVERIFIED"


class TerminationRule(StrEnum):
    PRORATE = "PRORATE"  # current period's minimum pro rata by days; later periods waived
    REMAINDER_DUE = "REMAINDER_DUE"  # current period's full minimum plus every later period's
    WAIVED = "WAIVED"  # no minimum for the terminated period or later


class ThresholdScope(StrEnum):
    EXCESS_ONLY = "EXCESS_ONLY"  # the percentage applies only to the amount above the threshold
    ENTIRE_SUBTOTAL = "ENTIRE_SUBTOTAL"  # once the threshold is reached, it applies to all of it


class OutcomeForm(StrEnum):
    SHARE = "SHARE"  # share of measured improvement against a baseline
    SUCCESS = "SUCCESS"  # fixed amount when a target is met
    PERCENT_OF_OUTCOME = "PERCENT_OF_OUTCOME"  # share of a measured result such as a recovery


class OutcomeDirection(StrEnum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
