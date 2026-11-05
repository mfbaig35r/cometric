# Cometric | Commercial Intelligence Engine

**Engineering Requirements v0.3 (as built for 0.2.0)**

Cometric does three things:

1. **Model.** Understand commercial arrangements through a structured ontology: a domain-neutral core plus domain packs (§3, §4).
2. **Simulate.** Calculate engagement economics and evaluate alternative scenarios, deterministically (§5, §6.1 to §6.2).
3. **Optimize.** Recommend commercial structures that balance profitability, risk, and client value, by searching candidate structures and reporting the trade-off frontier (§6.4).

It is built for any service relationship priced through a composite arrangement: consulting, outsourcing, managed services, and alternative legal services, with further industries added as packs.

| | |
|---|---|
| Project | Cometric (`cometric` on PyPI; CLI and MCP server `cometric`) |
| Status | Normative for `cometric` 0.2.0 (0.1.0 released to PyPI 2026-11-04). Open-source project. Where this document and the code disagree, the code's tests are the tiebreaker and the disagreement is a defect in one of them. |
| License | Apache-2.0 |
| Date | November 4, 2026 |
| Supersedes | `COMETRIC_SPEC_v0.2.md` (kept for history, with the v0.1 to v0.2 change log) |
| Source foundation | `alsp-commercial-models-deep-research.md` (research cutoff November 3, 2026). Note: the report header states an execution date of November 4, 2026, which postdates this specification; the report should be corrected. |
| Implementation | Python 3.11 to 3.13, Pydantic v2, decimal arithmetic; CLI; stateless read-only MCP server (MCP Python SDK 2.x) over stdio and streamable HTTP. Repository: github.com/mfbaig35r/cometric |
| Scope | A domain-neutral engine for the structure and economics of service engagements: commercial design, engagement evaluation, scenario comparison, structure search, and evidence-backed advisory reasoning. Domain vocabulary ships as packs; the Alternative Legal Services Provider (ALSP) pack is first and consulting is second. Not a general ledger, invoicing system, approval workflow, or automated contracting platform. |

> **Evidence convention.** **[R]** marks a concept documented or explicitly proposed in the research report; it does not imply independently reverified external sources. **[D]** marks a design decision proposed in this specification. **[O]** marks a question still open for the maintainers (§11). Illustrative values are not market benchmarks. The research report's source register remains the evidence source; individual claims must be linked to that register before they ship in a pack.
>
> **Change markers.** `[V3-nn]` marks text that is new or materially changed since v0.2. Each marker is listed in §0. Markers from earlier versions were removed; v0.2 keeps them.

---

## 0. Changes from v0.2

v0.3 records what was built. Most changes resolve questions v0.2 left implicit; a few record where the implementation chose a simpler rule than v0.2 described.

| ID | Section | Change |
|---|---|---|
| V3-01 | Header, 10 | Status is normative for 0.1.0; milestones carry their state. |
| V3-02 | 3.1, 4.1 | `OUTCOME_ADJUSTMENT` is a v1 method with three forms; outcome terms added to the domain model. |
| V3-03 | 3.1, 5.4 | Realization uses an engagement-level standard rate card and worked hours by role, under any billing method. |
| V3-04 | 3.4 | The consulting pack is built; its prerequisites are met. |
| V3-05 | 3.6 | Compatibility assessments number 17 (the report's table has 17 rows). |
| V3-06 | 4.1 | Quantity naming for time, weighted, and outcome components; how fixed amounts with longer cadences are spread. |
| V3-07 | 4.2 | Tier counters always recognize cumulatively; tiered overage with `ALL_ELIGIBLE` scope is restricted. |
| V3-08 | 4.3 | Which terms support which recognition rules. |
| V3-09 | 4.4 | Only `MINIMUM_SPEND` commitments are computed; rollover and grant rules made explicit. |
| V3-10 | 4.5 | Only the default evaluation order exists; adjustments are placed by type. Split-month, collar, rebate, indexation, and performance-trigger rules made explicit. |
| V3-11 | 4.6 | A proration policy may be declared on either version at a boundary. |
| V3-12 | 5.2 | The reference cost policy uses the amortized transition view. |
| V3-13 | 5.3 | Capacity breach is cumulative and strict; `BACKLOG` reduces billed units; production standards name scenario quantities. |
| V3-14 | 5.4 | Outputs list matches the engine, including outcome fee and realization; break-even method stated. |
| V3-15 | 7.3 | Warning codes match the implementation (`TIER_CLIFF`, `RISK_MISMATCH`). |
| V3-16 | 8.1 | Package layout as built; no separate advisory subpackage. |
| V3-17 | 8.3, 8.6 | MCP surface as built; HTTP host and token configuration; file-path inputs; new section on distribution and release. |
| V3-18 | 8.4 | Fingerprint scope as built. |
| V3-19 | 9 | Tests T-036 to T-041 for outcome pricing, realization, and the consulting pack. |
| V3-20 | 11 | Open questions updated; new questions from implementation. |
| V3-21 | App. C | Case H (consulting); fixtures live in `src/cometric/examples/`. |
| V3-22 | App. D | Evidence verification status replaces the v0.2 priority list. |
| V3-23 | 4.2, 9 | ALL_UNITS cliff bands compare every earlier tier with each threshold, with an inclusive lower bound where a band starts at a tier edge (unreleased fix after 0.1.0). |
| V3-24 | 8.3, 9, 10 | `reconcile` operation for M6, with a publishable summary (unreleased, after 0.1.0). |
| V3-25 | 4.1, 4.3, 4.5, 4.6, 5.2, 6.1, 8.4, 9 | Rules clarified by the full engine review (0.2.0): full-month proration, horizon simulation, one-time fees, indexation scope and contract years, required performance triggers, term-cost spreading, incurred view, component order. |

## 1. Purpose and intended decisions

The system SHALL represent the structure and economics of service engagements, in which a client buys professional, managed, or technology-enabled services under a composite commercial arrangement, in a way that is compositional, explainable, time-aware, and testable. Alternative Legal Services Provider (ALSP) engagements are the first supported domain, delivered as a domain pack (§3.4); the core engine contains no legal-sector vocabulary. It SHALL answer questions such as:

1. What exactly is being purchased and billed, and which contractual commitments modify it?
2. What is the expected provider contribution and client effective cost under alternative demand, complexity, staffing, and automation assumptions?
3. Which party bears volume, capacity, performance, scope, and technology-cost risks, both as declared in the contract and as derived from scenario results?
4. What changes if a fixed monthly service is replaced with a base-plus-overage or capacity-plus-consumption arrangement?
5. Which conclusions are contract facts, calculated results, assumptions, evidence-backed generalizations, or recommendations?

**Success criterion [D].** A user can load a validated engagement definition, run reproducible monthly financial scenarios, compare at least three feasible commercial arrangements, and receive traceable explanations of economic differences without an LLM performing financial arithmetic.

## 2. Product boundaries

### 2.1 In scope for v1

- Typed representation of engagements, parties, services, priced units, fee components, rate schedules, commitments, entitlements, capacity, delivery topology, SLAs, adjustments, risks, and evidence.
- Monthly contractual-fee and cost simulation with annual and term-level aggregation.
- Time-indexed contract amendments, effective dates, and proration.
- Fixed recurring, time, dedicated resource, unit output, complexity-weighted output, allowance-plus-overage, fixed project, and outcome-adjustment configurations; extensible support for other billing bases. `[V3-02]`
- Tiered rates (revenue and cost side); minimum spend; included allowance; overages; credits; collars; caps and not-to-exceed limits where defined.
- Dedicated and pooled delivery costs, transition costs, technology costs, QA/rework, and constrained capacity.
- Deterministic calculations and scenario comparison; warnings for incomplete or inconsistent inputs.
- Derived risk exposure from scenario comparison.
- Provenance and a human-review boundary for recommendations (§6.3, §7).
- A domain-pack interface and the ALSP pack (§3.4).
- A stateless, read-only MCP server and CLI over the engine, including schema and template discovery so any agent can construct valid inputs (§8.3).
- Deterministic structure search over bounded parameter ranges, returning the trade-off frontier (§6.4).

### 2.2 Explicitly out of scope for v1

- A hosted service, multi-user persistence, or approval workflow. The engine emits approval requirements; acting on them is the user's process.
- Domain packs beyond `base`, `alsp`, and `consulting`; further packs are community contributions.
- Issuing invoices, receiving payments, journal entries, tax accounting, or ASC 606 / IFRS 15 accounting automation.
- Automated interpretation of signed contracts as legally authoritative facts.
- Legal advice or automatic determination that contingent or fee-sharing arrangements are lawful.
- Optimizing across an entire enterprise workforce scheduling problem.
- Predicting client churn or asserting market-standard margin targets without internal empirical data.
- Automatically negotiating or approving commercial terms.
- Currency conversion and multicurrency engagements (see [O] 3).

### 2.3 Architecture principles

- **P-01 [D] Compositionality.** An engagement may contain multiple fee components and modifiers. ManagedService is a delivery/obligation configuration, not a billing primitive.
- **P-02 [D] Typed semantics.** Monetary values, percentages, periods, work units, resource units, and capacity units must be explicit. A quantity in one unit never prices against a rate in another unit. Weighted units are a distinct unit type from the raw units they are derived from.
- **P-03 [D] Deterministic economics.** LLMs may propose and explain arrangements; code computes prices, costs, and margins.
- **P-04 [D] Temporal integrity.** Historical periods use the contract version and assumptions effective for that period, at day resolution within a month.
- **P-05 [D] Provenance.** Source claims, observed client facts, internal policies, forecasts, and illustrative assumptions remain separate.
- **P-06 [D] Dual-sided evaluation.** Assess provider economics and client consumption/value together. Unused commitment must not be labeled automatically as success or failure.
- **P-07 [D] Explicit uncertainty.** Unknowns must not silently become zeroes, defaults, or fabricated market averages. Economic policies (cost policy, capacity ceilings, recognition rules, risk tolerances, margin floors) have no implicit defaults; omitting one that a calculation needs is a validation error. Formatting conventions (rounding) may have documented defaults, provided the effective value is echoed in every result and included in the fingerprint.
- **P-08 [D] Exact arithmetic.** All money and quantities use decimal arithmetic. Binary floating point is rejected at the schema boundary.
- **P-09 [D] Domain neutrality.** The core defines structure and arithmetic. Domain vocabulary (service categories, unit templates, provider types), constraint rules, catalogs, and evidence live in packs. The core never imports a pack.
- **P-10 [D] Stateless operation.** Every operation is a pure function of its inputs. The engine and MCP server hold no state between calls; anything a later call needs is passed back in.

## 3. Domain model

### 3.1 Core aggregate boundaries

| Aggregate / entity | Meaning | Core fields (illustrative) | Key relationships |
|---|---|---|---|
| Engagement | Evaluated client-provider relationship | id, name, currency, start_date, end_date, status, money_policy, packs | has parties, services, arrangement versions, scenarios |
| ContractParty | Buyer, provider, subcontractor | id, role, jurisdiction, regulated_status, provider_type (optional; pack vocabulary) | participates in engagement; bears risk |
| ServiceOffering | Defined operational obligation | id, service_category (optional; pack vocabulary), scope, unit_definition_id | has SLA, delivery plan, priced units |
| WorkUnitDefinition | Unambiguous measurable output | code, name, kind (COUNT, WEIGHTED, HOURS, FTE_MONTHS), counting_rule, acceptance_rule, exclusions | referenced by volume, output fees, production standards |
| ComplexityWeightTable | Conversion from raw units to weighted units | id, raw_unit, weighted_unit, bands {code, weight, criteria}, classification_authority, audit_rule | used by WEIGHTED_UNIT_OUTPUT components and production standards |
| PricingArrangementVersion | Effective-dated commercial configuration | id, effective_from, effective_to, supersedes_id, proration_policy, adjustment_order | contains fee components, commitments, entitlements, adjustments |
| FeeComponent | One charge computed by one method | id, service_id, calculation_method, billing_basis, charge_cadence, depends_on | prices a service or entitlement |
| RateSchedule | Rates and tiers | currency, unit, tiers, tier_method, tier_scope, accumulation_period | applies to fee or cost component |
| CommercialCommitment | Minimum spend, minimum volume, reserved capacity | kind, amount, aggregation_scope, settlement_period, tested_against, shortfall_rule | constrains fee components or entitlements |
| Entitlement | What a base fee or commitment purchases | unit, included_quantity, granted_by, allowance_period, overage_recognition, rollover | consumed by recorded activity; referenced by ALLOWANCE_OVERAGE |
| AdjustmentMechanism | Overage, true-up, indexation, collar, cap, credit | type, trigger, formula, scope, step | modifies a named subtotal at a declared evaluation step |
| DeliveryPlan | How work is produced | topology, resource_assignments, capacity_plan, breach_mode | drives cost and capacity, not contractual fee |
| ResourceRole | Costed staffing role | role_code, loaded_cost_rate, availability, productive_ratio | used in delivery plan |
| ProductionStandard | Effort per unit of output | unit (a scenario quantity name), role, band, hours_per_unit, origin | converts demand quantities to `demand_hours` `[V3-13]` |
| CostComponent | Direct or allocated cost | category, behavior, driver, rate, schedule, effective_period, avoidability_class, source_type | classified into a margin layer by the cost policy |
| CostPolicy | Mapping from cost category to margin layer | id, version, owner, mapping, transition_view | referenced by every calculation |
| OutcomeTerms `[V3-02]` | Terms of an outcome-based fee | form, metric, unit, direction, baseline, target, share_percent, success_amount, attribution_percent, attribution_method, cap_amount, accumulation_period, recognition, approval_reference | carried by an `OUTCOME_ADJUSTMENT` fee component |
| Standard rate card `[V3-03]` | Rate per role used to value hours worked | delivery_plan.standard_rate_card, delivery_plan.worked_hours_source | drives realization (§5.4) |
| ServiceLevel | Measurable service obligation | metric, target, window, remedy_id | drives quality, credits, bonuses |
| RiskAllocation | Identified exposure and bearer | risk_type, declared_bearer, limit, mitigation | compared with derived exposure (§5.5) |
| Scenario | Immutable time-indexed assumption set | id, baseline_id, assumptions, horizon, demand_distribution, probability_label | evaluates one or more arrangements |
| EvidenceClaim | Atomic proposition | claim_id, text, classification, prevalence, applicability | supported by evidence records |
| EvidenceRecord | Source and applicability | source_id, url, publication_date, date_unknown, retrieved_date, source_type, verified | supports claims |
| CalculationResult | Reproducible output | engine_version, schema_version, input_fingerprint, periods, line_items, metrics, warnings | produced from scenario |
| PricingRecommendation | Advisory comparison, not contract fact | candidate_id, rationale, tradeoffs, assumptions, calculation_ids, approval_state | references results and evidence |

[R] The research proposes 34 candidate entity classes and 20 relationships. This table is a deliberately smaller v1 aggregate model [D]. Concepts such as PerformanceObligation, ClientValueMetric, VolumeBand, AutomationComponent, and CommercialConstraint may initially be typed subobjects and later become independent graph entities.

### 3.2 Billing basis and charge cadence

**[D] Billing basis** describes what economic object is priced. Eight values:

| Value | Priced object | Discriminating rule |
|---|---|---|
| TIME | Professional effort as recorded hours | Quantity is approved hours worked. |
| RESOURCE | Named or qualified people | Commitment is denominated in persons or FTE-periods, whether or not they are fully used. |
| CAPACITY | Reserved throughput or availability not tied to named people | Commitment is denominated in work units or hours of availability, not persons. |
| OUTPUT | Completed, accepted work units | Quantity is accepted units under a counting rule. |
| USAGE | Metered technology or service consumption | Quantity is a meter reading (pages, GB, requests, prompts). |
| FIXED | A defined scope or entitlement regardless of effort | Amount is contractually fixed for the period or project. |
| COST | Provider-incurred eligible cost | Amount is derived from eligible cost plus markup or fee. |
| OUTCOME | A defined result, saving or recovery | Amount is derived from a measured outcome against a baseline. |

**[D] Charge cadence** describes when a charge arises and is orthogonal to basis: `ONE_TIME`, `MONTHLY`, `QUARTERLY`, `ANNUAL`, `EVENT` (milestone or acceptance trigger), `USAGE_TRIGGERED`.

**[D] Source vocabulary mapping.** The report's ten bases [R] are preserved as `source_basis` on catalog entries for traceability:

| Report value | Executable representation |
|---|---|
| BB-RECURRING | `FIXED` + periodic cadence (`MONTHLY`, `QUARTERLY`, `ANNUAL`) |
| BB-MILESTONE | `FIXED` (or `OUTPUT` for a deliverable with a counting rule) + `EVENT` cadence with a declared trigger |
| All other values | Same name, any cadence |

Freezing this mapping is part of the M0 exit criterion (§10).

### 3.3 Relationship requirements

- Engagement has one or more ServiceOffering objects.
- Engagement has one or more effective-dated PricingArrangementVersion objects; at most one version may be authoritative for the same service and day unless explicit component-level coexistence is defined.
- PricingArrangementVersion contains one or more FeeComponent objects.
- FeeComponent references exactly one calculation method and the unit, rate, and entitlement definitions that method requires.
- FeeComponent dependencies (`depends_on`) form a directed acyclic graph over components and entitlements. Cycles are a validation error.
- Commitment constrains one or more fee components or entitlements, with an explicit aggregation scope.
- AdjustmentMechanism modifies a named subtotal at a declared evaluation step (§4.5).
- DeliveryPlan drives cost and capacity, not contractual fee.
- Scenario provides assumptions for one or more comparable arrangements.
- Recommendation references calculation results and assumptions and never replaces them.
- EvidenceClaim references zero or more external sources and must indicate when it is inference or proposed design rather than externally observed fact.

### 3.4 Domain packs

A domain pack is a versioned bundle of vocabulary, rules, and data for one sector. The core runs without any pack; packs make it fluent in a domain.

| Pack contents | ALSP pack | Consulting pack `[V3-04]` |
|---|---|---|
| Service categories | CONTRACTS, EDISCOVERY, DOCUMENT_REVIEW, LEGAL_OPERATIONS, REGULATORY_CHANGE, IMPLEMENTATION, FLEXIBLE_RESOURCING | STRATEGY, OPERATIONS_IMPROVEMENT, TRANSFORMATION, IMPLEMENTATION, ADVISORY_RETAINER, INTERIM_MANAGEMENT |
| Unit templates (with counting and acceptance rule prompts) | accepted_contract_review, reviewed_document, custodian, matter, subpoena_response | consultant_day, accepted_deliverable, workstream_month |
| Provider types | REGULATED_LAW_FIRM, LICENSED_BODY, NONLAW_ALSP, FLEXIBLE_TALENT, LEGAL_TECH_VENDOR, MANAGED_SERVICES_PROVIDER [R] | LARGE_ADVISORY_FIRM, BOUTIQUE, INDEPENDENT_PRACTITIONER, TECHNOLOGY_INTEGRATOR |
| Constraint rules | Warning and approval-requirement rules, each citing evidence (for example: outcome or contingent fee with a regulated-work service; fee sharing with a non-law-firm provider type) [R] | Rules for attestation-related independence restrictions on contingent fees, and outcome fees without an agreed baseline |
| Catalogs | Legal-sector prevalence, evidence, and caveat overlays on the base catalogs (§3.6) [R] | Consulting overlays on the base catalogs, plus staffing-mix and realization concepts |
| Reasoning rules | RULE-011, RULE-012, RULE-016 (personal data, contingent legal fees, future-effective regulation) and the legally conditional compatibility combination [R] | Independence and baseline rules above |
| Engagement templates | Prefilled skeletons for common arrangements (fixed managed service, base plus overage, dedicated team, fixed project) | Role-based time and materials, capped time and materials, phased fixed fee, retainer with hours drawdown, fixed fee plus success fee |
| Evidence | Claims and sources, `verified = false` until checked (§7.2) | Same rule |

**Consulting pack prerequisites in the core.** `[V3-04]` Both are built:

- **Realization.** The delivery plan carries a `standard_rate_card` and a `worked_hours_source`; the engine values hours worked at standard rates under any billing method and reports realization, write-down, and effective billing rate (§5.4).
- **Outcome pricing.** `OUTCOME_ADJUSTMENT` is a v1 method (§4.1).

The consulting pack ships service categories, unit templates, provider types, realization and staffing concepts (CONS-001 to CONS-008), three rules (CONS-R-001 outcome-fee review, CONS-R-002 uncapped time on uncertain scope, CONS-R-003 fixed-fee scope control), overlays on eight base pricing models, and five templates: `role_based_tm`, `capped_tm`, `phased_fixed_fee`, `retainer_hours_drawdown`, `fixed_fee_plus_success`. Its evidence is thin by design: consulting prevalence is `UNVERIFIED` throughout, because the source research does not evidence it.

Rules:

- A pack MAY extend open vocabularies: service categories, provider types, unit templates, cost categories (each mapped to a core cost category), and constraint rules.
- A pack MUST NOT change billing bases, calculation methods, evaluation order, accumulation semantics, or metric definitions. Those belong to the core.
- Domain packs declare `extends: base` (§3.6). They may overlay a base concept with domain-specific prevalence, evidence, and caveats, but may not redefine its label or definition.
- An engagement declares `packs: [{id, version}]`. Pack ids and versions are part of the input fingerprint. Values from an undeclared pack fail validation.
- Constraint rules emit warnings and approval requirements only. A pack never asserts that a structure is permitted.
- The core test suite MUST pass with no packs loaded (T-027).

### 3.5 Pack concept files

The ontology a pack contributes is a set of concept files. The core validates them; nothing else defines the vocabulary.

**Packs are data only.** A pack contains YAML files and no executable code. Constraint rules use the declarative predicate language below. This lets the community contribute packs that the engine can load without running untrusted code.

**Layout:**

```
packs/<pack_id>/
  pack.yaml               id, version, title, license, core_version range
  concepts/
    service_categories.yaml
    unit_templates.yaml
    provider_types.yaml
    pricing_models.yaml
    levers.yaml
  rules/constraints.yaml
  templates/*.yaml        engagement skeletons
  evidence/sources.yaml   source records (§7.2)
  evidence/claims.yaml    atomic claims referencing sources
```

**Concept record** (one entry in a concept scheme):

```yaml
scheme: pricing_models
concepts:
  - id: PM-023                       # stable; never reused
    label: Hybrid fixed plus variable
    synonyms: [base plus overage, base plus variable]
    definition: >
      A recurring fixed charge for readiness or an included allowance,
      plus a metered charge for consumption beyond it.
    bases: [FIXED, OUTPUT, USAGE]    # core vocabulary, validated
    methods: [FIXED_RECURRING, ALLOWANCE_OVERAGE]
    broader: []
    related: [CL-R10, CL-V01, CL-V02]
    evidence_class: B_CORROBORATED
    prevalence: ESTABLISHED_COMMON
    claims: [CLM-0231]
    caveats: []
    source_ref: "report:PM-023"
```

Rules:

- `id` values are unique within the pack and never reused. Retired concepts stay with `deprecated: true` and `replaced_by`.
- Every reference to core vocabulary (`bases`, `methods`, cost categories) and to other concepts, claims, or sources must resolve; dangling references fail validation (T-032).
- `evidence_class` holds one value. Where the research gives a range (for example "A/B"), the pack records the weaker class.
- Labels, definitions, and synonyms are what `list_vocabulary` and `describe_pack` return to agents (§8.3).

**Constraint rule record:**

```yaml
rules:
  - id: ALSP-R-012
    when:
      all:
        - {path: "arrangement_versions[*].components[*].billing_basis", contains: OUTCOME}
        - {path: "services[*].service_category", in: [LEGAL_OPERATIONS, CONTRACTS]}
    emit:
      code: CONTINGENT_FEE_REGULATED_WORK
      severity: APPROVAL_REQUIRED      # or WARNING
      message: Outcome-based consideration on legal work requires legal review for the provider type and jurisdiction.
      claims: [CLM-0102]
```

The predicate language supports `all`, `any`, `not`, and the operators `equals`, `in`, `contains`, `exists`, `gt`, `lt` over JSON paths into the validated engagement. Nothing else.

**Export (post-v1).** A generated SKOS concept-scheme and JSON-LD export of the same files, for users who want to link Cometric concepts into a knowledge graph. It is generated, never hand-authored, so it cannot drift from the source.

### 3.6 Base knowledge pack

Most of the research report's knowledge is not specific to legal services; it draws on cloud, outsourcing, consulting, and accounting sources. That knowledge ships once, in a domain-neutral `base` pack that every domain pack extends. Domain packs add only what is sector-specific: vocabulary, regulation, and prevalence.

The research report itself is not shipped as prose (§11, Q-3). It is decomposed into atomic concept records, rules, and claims in the §3.5 format. Each record carries a `source_ref` naming the report section it came from; that reference is a derivation note for maintainers, not evidence. Evidence is the claims, whose sources are verified before `verified = true`. Report content without stable identifiers is assigned ids in the pack (COMPAT-, SEL-, NEG-, MECH-, DIM-).

**Where every part of the report goes:**

| Report content | Count | Home | Engine use | MCP surface |
|---|---|---|---|---|
| Billing bases (BB-*) | 10 | Core vocabulary: 8 bases + cadence (§3.2) | Arithmetic | `list_vocabulary` |
| Pricing-model catalog (PM-*) | 34 | `base/pricing_models`; prevalence overlays per domain | Template and search seeds | `lookup_concept`, resources |
| Commercial levers (CL-*) | 61, plus 9 the report names as possibly missing | `base/levers`; the 9 as `status: candidate` | Mechanics for the v1 subset (§4) | `lookup_concept` |
| Normalization finding (modifiers vs. bases) | 9 | `base/levers` with `kind: modifier` | None | `lookup_concept` |
| Commercial dimensions | 16 | `base/dimensions` with vocabularies, including automation-benefit allocation, scope type, technology treatment, transition recovery, and exit treatment | Optional engagement `descriptors`; the three risk dimensions are derived (§5.5) | `list_vocabulary` |
| Compatibility assessments `[V3-05]` | 17 | `base/compatibility` rules (COMPAT-001 to 016); the legally conditional one (COMPAT-017) in the ALSP pack | `check_commercial_constraints` emits COMPAT warnings with the assessment class | Rules resource |
| Financial metrics (FM-*) | 35 | `base/metrics` with formula, unit, limitation, and `computed_by` (engine metric id or null) | Engine metrics link to their definitions | Glossary resource |
| Commercial health indicators (CHI-*) | 12 | `base/metrics` | Scenario-mode subset computed (§5.6); the rest marked `requires: actuals` | Glossary resource |
| Cost-allocation guidance | 11 | `base/cost_categories` with preferred treatment and common distortion | `reference` cost policy (§5.2) | Resource |
| AI service-cost and AI fee decompositions | 12 and 6 components | `base/cost_categories` and `base/fee_components` | Cost categories | `lookup_concept` |
| Structures for automation-reduced effort | 5 | `base/automation_structures` concepts; engagement templates not yet built | None | `lookup_concept` |
| Model-selection framework | 12 steps | `base/selection_framework` | None | `design_arrangement` prompt |
| Decision matrix | 11 rows | `base/selection_heuristics` (SEL-*), class C_INFERENCE | None; never used to rank | `design_arrangement` prompt |
| Adjacent-industry mechanisms | 11 | `base/mechanisms` (MECH-*) with transferability class | None | `lookup_concept` |
| Negotiation exchanges | 10 | `base/negotiation_exchanges` (NEG-*) | None | `negotiation_options` prompt |
| Three defensible offers | 3 | `base/offers` concepts; engagement templates not yet built | None | `compare_structures` prompt |
| Entity classes and relationships (EC-*, REL-*) | 34 and 20 | Core schema, reconciled at M0 | Schema | `describe_schema` |
| Reasoning rules (RULE-*) | 16 | Base: 13 as rules or explanation notes; ALSP: RULE-011, -012, -016 | Warnings | Rules resource |
| Regulatory constraints, provider-type matrix | | ALSP pack | Constraint rules | Rules resource |
| Ontology layer boundaries | 7 | Core principles P-03 to P-07 | Enforced by design | Glossary resource |
| Price floor, unit price, capacity cost formulas | 3 | Core engine (§5.3, §5.6) | Computed | `price_floor` tool |
| Margin-at-Risk, Client Value-at-Risk | 2 | `base/metrics`, class C/D, `requires: distributions` | Not computed in v1 | `lookup_concept` |
| Casebook | 6 (+ G) | Fixtures (Appendix C) | Regression | Examples resource |
| Evidence register (E*) | 40 | Accounting, cloud, and outsourcing sources in base; legal-sector sources in ALSP | None | `list_applicable_evidence` |
| Evidence-coverage assessment | 12 areas | Per-pack `coverage` | None | Coverage resource |
| Internal validation checklist | | Not shipped; each item became user-supplied policy (§11) | | |

**Rules:**

- Knowledge records are advisory and explanatory. The engine computes only from core vocabulary, methods, and caller policies. It never reads selection heuristics, negotiation exchanges, mechanisms, or compatibility classes to compute, rank, or choose (P-03).
- Every record keeps its evidence class. A class C or D record is always returned labeled as inference or proposal.
- Capture is auditable: every report identifier, and every row of the unnumbered tables above, appears in a pack or in `packs/base/excluded.yaml` with a reason (T-033).

## 4. Contract and fee semantics

### 4.1 Fee component contract

Each fee component MUST declare: `id`, `service_id`, `calculation_method`, `billing_basis`, `charge_cadence`, `currency`, `quantity_source` (or null for fixed methods), `unit` (or null for fixed methods), `effective_period`, `depends_on`, and the inputs its method requires (below). Missing required inputs yield validation errors.

`calculation_method` is authoritative for arithmetic. `billing_basis` is a classification validated against the method.

| Method | Formula (per period segment *t*) | Required inputs | Allowed bases | v1 |
|---|---|---|---|---|
| `FIXED_RECURRING` | fee_t = fixed_amount_t, prorated per §4.6 | fixed_amount, cadence | FIXED, CAPACITY | Yes |
| `TIME` | fee_t = Σ_role hours_role,t × rate_role,t | `role_rates`; hours from scenario quantities `<quantity_source>.<role>` | TIME | Yes |
| `DEDICATED_RESOURCE` | fee_t = Σ_role committed_FTE_role,t × rate_role,t | FTE commitment, rate per FTE-period, partial-period rule | RESOURCE | Yes |
| `UNIT_OUTPUT` | fee_t = rate_schedule(accepted_units_t) | rate_schedule, unit with counting and acceptance rules | OUTPUT, USAGE | Yes |
| `WEIGHTED_UNIT_OUTPUT` | fee_t = rate_schedule(Σ_band raw_units_band,t × weight_band) | rate_schedule in weighted units, ComplexityWeightTable; band quantities `<quantity_source>.<band>` | OUTPUT | Yes |
| `ALLOWANCE_OVERAGE` | fee_t = rate_schedule(excess_quantity_t), where excess comes from the referenced entitlement ledger (§4.4) | entitlement_id, rate_schedule | OUTPUT, USAGE | Yes |
| `FIXED_PROJECT` | fee_t = payment_schedule_t, Σ_t payment_schedule_t = project_fee | project_fee, payment schedule (dates or events) | FIXED | Yes |
| `COST_PLUS` | fee_t = eligible_cost_t × (1 + markup) | cost eligibility policy, markup | COST | Post-v1 |
| `OUTCOME_ADJUSTMENT` `[V3-02]` | See below | `outcome` terms | OUTCOME | Yes |

`ALLOWANCE_OVERAGE` components MUST list their entitlement in `depends_on`. The entitlement's `granted_by` names the component that grants it (typically a `FIXED_RECURRING` base).

**Fixed amounts with longer cadences.** `[V3-06]` A `FIXED_RECURRING` amount with `QUARTERLY` or `ANNUAL` cadence is spread across the months of its quarter or contract year by exact allocation (§4.7), anchored at the component's effective month, so its declared total is kept even when the component starts mid-month; it is reduced only by its version's share of a split month. `ONE_TIME` is charged in full in its first month and never prorated. `MONTHLY` amounts prorate by the component's days in the month. `[V3-25]` A billing or cash schedule, if needed, is separate (§5.1).

**Outcome adjustment.** `[V3-02]` The outcome fee is its own component; any base fee is a separate component. The scenario supplies the measured outcome per month as the quantity named by `outcome.metric`. The engine accumulates it over `outcome.accumulation_period` and charges the fee in the period's final month:

| Form | Fee for the period |
|---|---|
| `SHARE` | share_percent × attribution_percent × max(0, improvement), where improvement = outcome − baseline (`HIGHER_IS_BETTER`) or baseline − outcome (`LOWER_IS_BETTER`) |
| `SUCCESS` | success_amount if the outcome meets `target` in the declared direction, else 0 |
| `PERCENT_OF_OUTCOME` | share_percent × attribution_percent × max(0, outcome) |

The fee is then limited to `cap_amount`. Validation requires a baseline for `SHARE`, a target and amount for `SUCCESS`, attribution for `SHARE` and `PERCENT_OF_OUTCOME`, and `recognition = PERIOD_END` (cumulative recognition is post-v1). A missing cap or a missing `approval_reference` raises an approval requirement, never a silent default; a missing `attribution_method` raises a warning. If the horizon ends before the period does, the fee is not charged and `TRUE_UP_OUTSIDE_HORIZON` is raised.

### 4.2 Rate tiers

`RateSchedule.tier_method` MUST be one of:

- `MARGINAL`: each tier prices only units within that tier.
- `ALL_UNITS`: the tier reached sets the rate for all eligible units.
- `GRADUATED_BLOCK`: fixed price per defined block (post-v1).

A single-tier schedule is valid under either v1 method and they are equivalent.

Tier rules:

- Tiers are half-open intervals `[from, to)`. The first tier starts at 0. The last tier has `to = null`. Tiers are contiguous and non-overlapping.
- `tier_scope` declares which quantity is tiered: `ALL_ELIGIBLE` or `EXCESS_ONLY` (units beyond an entitlement).
- `accumulation_period` declares when the tier counter resets (§4.3). A tier counter may span multiple monthly segments. Tier counters always recognize cumulatively: each month is priced as the difference between the schedule's price at the counter after and before that month. `[V3-07]`
- Tiered overage (`ALLOWANCE_OVERAGE`) with `tier_scope = ALL_ELIGIBLE` must use `MARGINAL` tiers and non-`PERIOD_END` recognition in v1; other combinations fail with `UNSUPPORTED_COMBINATION`. `[V3-07]`
- Tier calculations MUST be tested at `threshold - 1`, `threshold`, and `threshold + 1`.

**ALL_UNITS cliff detection [D].** For each threshold *t* (rate *r_t*) and each earlier tier *i* with a higher rate *r_i*, every quantity *q* in tier *i* with *q × r_i > t × r_t* costs more than *t* units. The band is `(t × r_t / r_i, min(to_i, t))` within tier *i*, with an inclusive lower bound when the tier's own start already exceeds `t × r_t / r_i`. Comparing every earlier tier, not only the adjacent one, catches jumps across several tiers. `[V3-23]` Example: $10 below 1,000 and $9 from 1,000 gives 999 units = $9,990 and 1,000 units = $9,000; quantities 901 to 999 all cost more than 1,000. Validation MUST emit one `TIER_CLIFF` per threshold, listing every band with its lower bound, whether that bound is inclusive, and its exclusive upper bound. The cliff is a property of the contract, not an error; the warning lets reviewers see the incentive it creates.

The same tier machinery applies to tiered **cost** schedules (§5.2).

### 4.3 Accumulation periods

The calculation grain is the calendar month (§5.1). Many contract terms operate over a longer period. Every allowance, minimum commitment, tier counter, tiered cost, and capacity limit MUST declare an `accumulation_period`: `MONTH`, `QUARTER`, `YEAR`, `CONTRACT_YEAR` (anniversary-based), or `TERM`.

Within an accumulation period the engine keeps a running accumulator. Each such term MUST also declare its recognition rule:

| Rule | Meaning |
|---|---|
| `CUMULATIVE` | The effect is recognized in the month the accumulator crosses the threshold. Example: an annual allowance of 12,000 units is consumed month by month; overage fees begin in the month cumulative consumption passes 12,000. |
| `PERIOD_END` | The effect is computed and recognized in the final month of the accumulation period (true-up). |
| `PER_SEGMENT` | Only valid when `accumulation_period = MONTH`; each month stands alone. |

**Horizon starting after the engagement.** `[V3-25]` The engine always simulates from the engagement's first month, so allowances, tier counters, minimums, caps, rebates, and outcome periods carry into the horizon; only horizon months are reported. Assumptions stated for a year or `TERM` are spread over the engagement's months, not just the horizon. If the scenario has no quantities before the horizon, `PRE_HORIZON_QUANTITIES_MISSING` warns that accumulators start the horizon empty.

Applicability `[V3-08]`: allowances support all three rules (`PER_SEGMENT` only with `MONTH`); minimum commitments use their `shortfall_rule` (`PERIOD_END_TRUE_UP`, or `PER_SEGMENT` with `MONTH`); outcome fees use `PERIOD_END` only; tier counters and capacity limits are always cumulative. A true-up whose period ends after the horizon is not charged and raises `TRUE_UP_OUTSIDE_HORIZON`.

There is no default recognition rule (§11, R-11); engagement templates prefill `CUMULATIVE` visibly. For the annual totals the casebook reports, `CUMULATIVE` and `PERIOD_END` produce identical annual results; they differ only in which months carry the amounts (T-023).

### 4.4 Commitments and entitlement ledger

A minimum-spend commitment is not equivalent to an included-unit allowance. The engine SHALL model separately:

- **Minimum commitment:** `minimum_amount`, `aggregation_scope` (`COMPONENT`, `SERVICE`, `ENGAGEMENT`), `accumulation_period`, `tested_against` (`GROSS`, `NET_OF_DISCOUNTS`, `NET_OF_CREDITS`), and `shortfall_rule` (`PERIOD_END_TRUE_UP`, `PER_SEGMENT`). A minimum is applied exactly once at its declared scope (T-007).
- **Entitlement:** `included_quantity`, qualifying unit, `granted_by`, `accumulation_period`, `overage_recognition`.
- **Ledger state:** consumed, remaining, rolled-over, and expired quantities.
- **Rollover:** policy (`NONE`, `NEXT_PERIOD`, `TERM`), carryover ceiling, expiry, and whether rolled quantity is consumed before or after new grants (`FIFO` required in v1).
- **Credit application order** and an explicit prohibition on double counting.

Each ledger entry MUST include: period, unit, entry type (`GRANT`, `CONSUME`, `ROLLOVER_OUT`, `ROLLOVER_IN`, `EXPIRE`, `ADJUST`), quantity, source grant, accumulation period id, expiry, and contract version. Invariant: every granted unit is consumed, rolled, or expired exactly once (T-006).

As built `[V3-09]`:

- Only `MINIMUM_SPEND` commitments are computed. `MINIMUM_VOLUME`, `RESERVED_CAPACITY`, and `PREPAID_CREDIT` are validated and recorded with a `COMMITMENT_NOT_COMPUTED` warning.
- A grant is posted when an entitlement's accumulation period opens, for the full `included_quantity`; grants are not prorated when a contract version starts mid-period.
- Consumption is FIFO with rolled-in lots first. `NEXT_PERIOD` rolls unused granted quantity (up to `ceiling`) into the next period, where it expires if unused; it does not roll twice. `TERM` rolls everything until the engagement ends. Remaining quantity expires at the engagement's end; a horizon that ends earlier leaves lots open.

[O] Treatment of unused prepaid entitlements for financial-statement accounting is excluded from v1.

### 4.5 Evaluation order

v1 supports only the default order (`adjustment_order = DEFAULT`); each adjustment is placed at its step by its type, so no mechanism can be unplaced or duplicated. Custom orders are post-v1. `[V3-10]`

**Default order [D], per period segment:**

1. **Resolve.** For each day segment of the month, select the authoritative arrangement version (§4.6).
2. **Measure.** Determine eligible quantities per unit definition. Apply complexity weights to produce weighted quantities. Reject any quantity whose unit does not match the consuming component (T-004).
3. **Consume.** Post consumption to entitlement ledgers. Split each metered quantity into in-allowance and excess portions.
4. **Price.** Compute each component in dependency order. Fixed amounts are prorated. Metered amounts apply the component's rate schedule to its declared quantity (excess quantity for `ALLOWANCE_OVERAGE`). Tier pricing happens here, using the tier accumulator.
5. **Collar.** Apply volume-corridor repricing where measured quantity falls outside the declared band. v1 supports one repricing form: an alternate rate schedule outside the band.
6. **Discount.** Apply contractual discounts and rebates.
7. **Minimum.** Test minimum commitments against their declared subtotal (`GROSS` uses the subtotal after step 5; `NET_OF_DISCOUNTS` after step 6) and post shortfall per the shortfall rule. A minimum declared `NET_OF_CREDITS` is evaluated after step 8 instead.
8. **Performance.** Apply SLA credits, holdbacks, and bonuses, each subject to its cap. A cap expressed as a percentage of a subtotal is computed on the subtotal entering this step, which avoids circular definitions.
9. **Cap.** Apply fee caps and not-to-exceed limits at their declared scope.
10. **Deferred.** Currency conversion and taxes are out of scope for v1.

This order is not a universal commercial rule. The engine MUST return `requires_contract_interpretation` instead of guessing when:

- the contract is ambiguous about order or terms conflict;
- a floor (minimum) exceeds a cap at the same scope and period (T-024);
- a mechanism references a subtotal that does not exist at its step.

Every step emits line items with: step, stage, mechanism id, attributed component, kind, quantity, unit, rate, formula text, unrounded amount, rounded amount, day segment, and contract version. `explain_fee` (§8.3) reads these line items.

Step semantics as built `[V3-10]`:

- **Split months.** Steps 3 and 4 run per day segment. Steps 5 to 9 run once per month with the adjustments and commitments of the version in force at the month's last priced segment.
- **Collar.** Evaluated per month on that month's measured quantity. Above `upper`, units above the band are repriced on the alternate schedule; below `lower`, all units are repriced on it.
- **Discount** applies a percentage to each component's step-5 subtotal (all components unless `applies_to` is set). **Rebate** credits a percentage of the accumulated period subtotal at period end when it meets `threshold`.
- **Indexation** adds, from the second contract year, `(1 + percent)^n - 1` times each step-4 fixed, resource, time, unit, and overage line (including period-end overage), where n is the contract year. Project payments and outcome fees are not indexed. A month belongs to the contract year containing its first day, counting anniversaries of the engagement start date. `[V3-25]`
- **Performance.** A trigger quantity the scenario does not provide is an error with a pointer to the adjustment's `trigger`, never a silent zero. `[V3-25]` `SLA_CREDIT` and `BONUS` multiply `percent` × the step-7 subtotal × a scenario trigger quantity (for example, misses in the month), limited by `cap_percent` of that subtotal. `HOLDBACK` withholds `percent` of the subtotal unless the trigger quantity releases it (1).
- **Cap** accumulates the pre-cap total over its period and reduces the month in which the cap is crossed and any month after.

### 4.6 Amendments and proration

An amendment MUST specify affected terms, effective date, precedence, and whether retroactive recalculation is authorized. Re-running a historical scenario SHALL preserve the original contract version unless an explicit amended-run flag is provided (T-005). Results MUST store an input fingerprint (§8.4).

Effective dates may fall on any day. When any version, component, or commitment boundary falls inside a month, the month is split into day segments and each segment is evaluated against its authoritative version. The arrangement MUST then declare `proration_policy`:

| Policy | Fixed amounts | Metered quantities |
|---|---|---|
| `CALENDAR_DAYS` | amount × segment_days / days_in_month | Supplied per segment; if only a monthly quantity is supplied, it is split by days and the split quantity is tagged `ESTIMATED` |
| `FULL_MONTH_FROM_NEXT` | New terms apply from the first day of the following month; the outgoing version bills the whole month | Same |
| `FULL_MONTH_FROM_CURRENT` | New terms apply to the whole month containing the effective date | Same |

Under the two full-month policies, component effective dates inside that month snap to the version's whole-month assignment: a component is either in for the month or out, never prorated by days. Fixed project payments and one-time fees post once in the month, whichever segment their component falls in. `[V3-25]`

If all boundaries fall on month starts, `proration_policy` may be omitted. Otherwise at least one of the two versions meeting at a mid-month boundary must declare it; the incoming version's policy wins if both do. Omission on both is a validation error (P-07, T-018). `[V3-11]`

### 4.7 Money, quantities, and rounding

- Monetary amounts, rates, quantities, weights, and percentages are `Decimal`. Schema fields accept JSON strings or integers; JSON floating-point numbers are rejected (P-08).
- Count units (`kind = COUNT`) must be integer-valued and non-negative. Weighted, hour, and FTE units may be fractional.
- Internal computation is unrounded at a fixed decimal context (28 significant digits).
- `money_policy` on the engagement declares `rounding_mode` (`HALF_UP` or `HALF_EVEN`), `rounding_scale`, and `rounding_level` (`LINE_ITEM` or `PERIOD_TOTAL`). It is optional. The documented default is `HALF_UP`, the currency's ISO 4217 minor-unit scale, and `LINE_ITEM`. The effective policy is echoed in every result and included in the fingerprint (P-07; §11, R-13).
- Period totals are the sum of their rounded line items. Annual and term totals are the sum of period totals, never independently recomputed (T-015).
- **Exact allocation.** When a total declared over a longer period (an annual fee, an annual cost, an annual demand forecast) is spread across months, the allocation MUST preserve the declared total exactly. Each month receives the truncated share at rounding scale (or unit scale for counts); the residual is distributed one minor unit at a time to the earliest months. Example: $880,000/year over 12 months gives 4 months of $73,333.34 and 8 months of $73,333.33. Dividing a rate and rounding each month independently is prohibited.
- Ratios (margins, utilization, markups) are returned unrounded. Rounding for display is a presentation concern.

## 5. Economics engine

### 5.1 Time model

The calculation grain SHALL be calendar month [D], split into day segments where §4.6 requires, with aggregation to quarter, year, contract year, and term. Each month SHALL carry:

- `contractual_fee` (contractual consideration computed under §4; not GAAP revenue);
- estimated billed amount and cash collections, only if an optional cash schedule is provided;
- actual or forecast demand by unit and complexity band;
- theoretical, available, productive, and safe capacity; demand hours; overflow and backlog (§5.3);
- costs by category and by margin layer (§5.2);
- gross profit, contribution profit, margins, and cumulative contribution;
- client paid amount, consumed units, and effective client price per accepted normalized unit (or per used hour for resource arrangements).

`contractual_fee` is the only label for the computed charge. The system MUST NOT label it `revenue` or `recognized_revenue` absent an explicit accounting adapter. Where this specification or the research report says "revenue" in a formula, read `contractual_fee`.

### 5.2 Cost classification and margin layers

Cost components MUST declare: `cost_category`, `behavior`, `dedicated_or_shared`, `cost_driver`, `cost_rate` or schedule, `allocation_method`, `effective_period`, `avoidability_class`, `source_type`, and, for one-time costs, an `incurred_schedule`.

**Required cost categories:** dedicated labor, pooled labor, delivery management, QA/rework, AI inference, platform operations, third-party services, client-specific implementation, reusable engineering allocation, transition, engagement-specific overhead, corporate overhead.

**Cost behaviors:** `FIXED`, `VARIABLE` (rate × driver), `STEP` (step size, step cost), `TIERED_VARIABLE` (a tiered rate schedule on the driver with its own accumulation period, §4.2 and §4.3).

**Margin layers.** A `CostPolicy` maps every cost category to exactly one layer. Every calculation references one cost policy, and that policy is part of the input fingerprint.

| Layer | Meaning |
|---|---|
| `DIRECT_DELIVERY` | Costs of producing the service for this engagement |
| `ENGAGEMENT_AVOIDABLE` | Costs outside direct delivery that would not be incurred without this engagement |
| `PORTFOLIO_SHARED` | Shared investment or capacity not caused by this engagement (reusable platform build, idle pooled capacity) |
| `CORPORATE_OVERHEAD` | Fully loaded view only |

Metric definitions [D]:

```
gross_profit         = contractual_fee - Σ DIRECT_DELIVERY
contribution_profit  = gross_profit    - Σ ENGAGEMENT_AVOIDABLE
gross_margin         = gross_profit        / contractual_fee
contribution_margin  = contribution_profit / contractual_fee
full_cost_profit     = contribution_profit - Σ PORTFOLIO_SHARED - Σ CORPORATE_OVERHEAD   (separate view)
```

Because layers partition costs, no cost is subtracted twice (T-021). `avoidability_class` remains a descriptive attribute; it does not drive arithmetic.

**Reference cost policy.** The core ships a cost policy with id `reference`. A calculation uses it only when the caller names it; there is no implicit policy (P-07). It follows the report's cost-allocation guidance [R]:

| Cost category | Layer in `reference` |
|---|---|
| Dedicated labor, pooled labor (activity-allocated), delivery management, QA/rework, AI inference, platform operations, third-party services | `DIRECT_DELIVERY` |
| Client-specific implementation, transition, engagement-specific overhead (account management, client governance) | `ENGAGEMENT_AVOIDABLE` |
| Reusable engineering allocation, unallocated idle pooled capacity | `PORTFOLIO_SHARED` |
| Corporate overhead | `CORPORATE_OVERHEAD` |

The reference policy uses the amortized view of one-time costs (`transition_view = AMORTIZED`); both views are reported on one-time cost lines, and the transition payback month always uses the incurred view. `[V3-12]` The Appendix C "harmonized" fixture variants use this policy.

**Reconciliation with the report.** Report FM-018 defines contribution as revenue minus variable costs minus engagement-avoidable fixed costs [R]. That matches `contribution_profit` only when every `DIRECT_DELIVERY` cost is avoidable. The engine SHALL report `unavoidable_direct_cost` separately so FM-018 can be reconstructed.

Zero-fee periods MUST return a null margin with an explanation, not divide by zero (T-008). Portfolio and overhead allocations MUST NOT be merged into contribution.

**Term costs.** A `FIXED` cost with `period = TERM` is spread over the months it is in effect (its own effective period within the engagement), so its declared total is kept. `[V3-25]`

**Transition cost timing.** One-time costs carry an `incurred_schedule`. The engine reports two views: **incurred** (cost in the month it occurs; used for cumulative contribution and transition payback month) and **amortized** (spread over a declared period using exact allocation; used where a fixture or policy states annualized transition cost). The cost policy states which view feeds `contribution_profit`. The incurred-view adjustment applies only to one-time costs in the two layers inside contribution (`DIRECT_DELIVERY`, `ENGAGEMENT_AVOIDABLE`). `[V3-25]`

### 5.3 Capacity and operational production

Capacity MUST distinguish:

```
theoretical_hours = FTE × contracted_hours_per_period
available_hours   = theoretical_hours - planned_leave - training - holidays
productive_hours  = available_hours × productive_ratio
safe_capacity     = productive_hours × safe_utilization_ceiling     (INTERNAL_POLICY origin, no default)
```

**Production standards.** Demand quantities convert to demand hours through `ProductionStandard` records (hours per unit, optionally by band). Each record names a scenario quantity (`unit`, or `unit.band`); the engine derives a `demand_hours` quantity from them. `[V3-13]` Capacity declared directly in units (as in casebook Case A) is permitted; the engine then compares unit demand with unit capacity and does not require standards.

**Capacity period.** Capacity limits carry an `accumulation_period`. Breach is tested against cumulative demand and cumulative capacity within that period, so whole-unit demand allocation does not create false breaches against fractional monthly capacity. A breach is demand strictly greater than the limit. Under `BACKLOG`, served units (and therefore billed units) are reduced and the excess carries into the next month; under `OVERFLOW_COST`, units above the limit are costed at `overflow_cost_rate` in place of the cost components listed in `overflow_replaces`. `[V3-13]`

**Breach mode** is declared on the delivery plan or scenario:

| Mode | Behavior |
|---|---|
| `OVERFLOW_COST` | Units or hours above capacity incur a declared overflow cost rate instead of the normal variable rate: `cost = F + v × min(Q, K) + v_o × max(Q - K, 0)` [R] |
| `BACKLOG` | Excess demand carries to the next period; SLA risk warning emitted; backlog at horizon end reported |
| `INFEASIBLE` | Scenario fails feasibility validation |

If no breach mode is declared and a breach occurs, the scenario is infeasible (T-010).

For pooled resources, allocation policy MUST be declared and shared portfolio capacity MUST NOT be double-booked. v1 may model pooled capacity with a simplified aggregate pool, but it must expose that simplification in result warnings.

For AI-assisted services, cost drivers SHOULD include document complexity, inference volume, human validation time, exception rate, rework, and engineering amortization. [O] Correlated stochastic production drivers are a later enhancement; v1 uses explicit scenario inputs and sensitivity bands.

### 5.4 Financial outputs

Required metrics `[V3-14]`: contractual fee, outcome fee, direct delivery cost, unavoidable direct cost, gross profit and margin, engagement-avoidable cost, contribution profit and margin, cost per accepted unit, effective client price per accepted unit (and per used hour for resource arrangements), reserved-capacity utilization, productive-hours utilization, included-allowance consumption, commitment shortfall, overage fee, cumulative contribution, transition payback month (incurred view), break-even volume where mathematically defined, and, when the delivery plan has a standard rate card, worked hours, standard value, realization (contractual fee / standard value), write-down (standard value − contractual fee), and effective billing rate (contractual fee / worked hours).

Break-even volume is found by bracketing whole driver units and interpolating linearly between the bracketing pair; it is reported as that decimal value and as the whole unit at the boundary (the smallest whole unit with non-negative contribution when contribution rises with the driver, the largest when it falls). The result states the interpolation assumption. For piecewise fees or costs, the engine solves piecewise and returns null with a reason when no break-even exists in the horizon.

The engine SHALL separately label provider-side financial outcomes and client-side consumption/value indicators. It SHALL NOT infer retention probability from unused commitment.

### 5.5 Derived risk exposure

Declared `RiskAllocation` records what the contract says. The engine also derives exposure from scenario results, so reviewers can see who actually absorbs a deviation.

For a scenario set with a base case and one or more deviation cases on a named driver (demand volume, delivery hours, complexity mix, utilization):

```
provider_downside(case) = contribution_profit(base) - contribution_profit(case)
client_downside(case)   = effective_client_unit_price(case) - effective_client_unit_price(base)
```

Positive values are adverse. Absolute fee change is reported alongside for context.

Given tolerances supplied by the caller (§11, R-14), expressed relative to base contribution and base unit price, each deviation case is labeled:

| Provider adverse | Client adverse | Derived bearer |
|---|---|---|
| Yes | No | `PROVIDER` |
| No | Yes | `CLIENT` |
| Yes | Yes | `SHARED` |
| No | No | `NONE_ADVERSE` |

With no tolerance declared, the engine reports the raw exposures and no label (P-07). Where a declared bearer and a derived bearer disagree, the engine emits `RISK_MISMATCH`. Expected labels for the casebook are in Appendix C.

### 5.6 Price floor and health indicators

**Price floor.** The report's decision formula [R] becomes an engine operation:

```
P_min(q)     = (C(q) + RiskPremium) / (1 - m_t)
unit_floor(q) = P_min(q) / q
```

where `C(q)` is the sum of `DIRECT_DELIVERY` and `ENGAGEMENT_AVOIDABLE` costs at volume `q` under the caller's cost policy, `m_t` is the target contribution margin, and `RiskPremium` is an amount. Both `m_t` and `RiskPremium` are required caller inputs with `origin = INTERNAL_POLICY`; `m_t` must be less than 1. The result is the fee at which contribution margin equals `m_t`. `price_floor` returns the floor at each scenario volume, so the caller sees how the floor rises as volume falls. It is a decision formula, never a benchmark. Example (T-034): casebook Case B at 12,000 contracts, 20% target, no premium: costs $900,000, floor $1,125,000, $93.75 per contract.

**Health indicators.** The report's commercial-health indicators [R] split by what they need:

| Indicator | v1 (scenario mode) | Needs actuals (post-v1) |
|---|---|---|
| CHI-001 commitment utilization | Yes | |
| CHI-002 effective client cost per unit | Yes | |
| CHI-003 capacity utilization | Yes | |
| CHI-007 margin sensitivity to consumption | Yes, from scenario pairs | |
| CHI-011 capacity-service mismatch | Yes | |
| CHI-004, -005, -006, -008, -009, -010, -012 | | Yes: forecast variance, credit frequency, quality-adjusted throughput, renewal price pressure, value realization, unused-commitment trend, effective cost trend |

The post-v1 indicators need recorded actuals over time, which v1 does not store (§8.5). Each indicator returns with its limitation from `base/metrics`; CHI-010 always carries the report's caveat that it is not a validated retention predictor.

## 6. Scenarios, comparison, and advisory behavior

### 6.1 Scenario definition

A scenario is an immutable snapshot of arrangement version, cost policy, demand profile, complexity mix, staffing/capacity plan, technology assumptions, breach mode, and simulation horizon. Every assumption SHALL have `value`, `unit`, `time_period`, and `origin` (`OBSERVED`, `CONTRACTED`, `ESTIMATED`, `ILLUSTRATIVE`, `INTERNAL_POLICY`).

Assumptions stated over a longer period than a month MUST declare a `demand_distribution`: `FLAT` (exact allocation per §4.7) or an explicit monthly profile.

v1 SHALL support low/base/high scenarios and deterministic one-way sensitivity analysis. Probability distributions and Monte Carlo are deferred until calibrated data is available.

### 6.2 Candidate comparison

Given one service and demand profile, the engine SHOULD compare at least:

- fixed recurring managed service;
- dedicated resource or capacity model;
- base fee plus output-based overage.

Each comparison MUST show fee, cost, contribution, client effective unit cost, capacity utilization, declared and derived risk exposure (§5.5), and the assumptions that differ. A model can be rejected for infeasibility without being labeled commercially inferior.

**Dominance, not ranking.** By default the engine ranks nothing. For each feasible candidate it reports whether another candidate dominates it: at least as good on every comparison metric and strictly better on one. The default metrics are provider contribution (higher is better) and client effective unit price (lower is better), evaluated in every scenario of the set. The non-dominated candidates are returned as a set. A weighted or constrained objective is applied only when the caller supplies one, and the result records it verbatim.

### 6.3 Advisory guardrails

An AI layer MAY propose alternatives, explain tradeoffs, or identify missing facts. It MUST NOT:

- invent market rate cards, target margins, renewal probabilities, or legal permissions;
- treat provider case studies as independent market benchmarks;
- change financial inputs without showing the change;
- state that one structure is optimal absent a declared objective function and constraints;
- bypass legal or commercial approval requirements.

Recommendations SHALL cite calculation IDs, assumptions, constraints, and evidence claims. Human sign-off is required before adopting a commercial recommendation.

### 6.4 Structure search (Optimize)

In Cometric, "optimize" means a deterministic search over a space of candidate structures that the caller declares. It never means asking a model for an answer.

**Input (`search_spec`):**

- a base engagement or template containing named parameters;
- `parameters`: each with a name, a JSON Pointer into the engagement, and either an explicit value list or a decimal range `{from, to, step}`;
- `constraints`: predicates over result metrics, using the §3.5 predicate operators (for example: contribution margin ≥ 0.15 in every scenario; client effective unit price ≤ 110.00 in the base scenario; feasible in every scenario);
- `scenario_set` and `cost_policy`;
- `objective` (optional): one metric to maximize or minimize, a scenario aggregation (`BASE`, `WORST`, or `MEAN`), and optional lexicographic tie-breakers. Weighted sums of metrics in different units are not supported.

**Procedure:**

1. Enumerate the Cartesian product of parameter values in declared order. If the grid exceeds `max_candidates` (default 10,000; caller may lower it), the search is rejected with the grid size. v1 has no random sampling.
2. Validate each candidate. Invalid candidates are counted by reason, never silently dropped.
3. Evaluate each valid candidate across the scenario set (§5) and derive risk exposure (§5.5).
4. Apply constraints.
5. Compute the **trade-off frontier**: the candidates not dominated (§6.2) on the frontier metrics. By default these balance the three things Cometric optimizes for:
   - profitability: provider contribution in the base scenario (higher is better);
   - client value: client effective unit price in the base scenario (lower is better);
   - risk: the largest provider downside and the largest client downside across deviation scenarios (lower is better for each).
   Callers may declare a different metric set.
6. If an objective is supplied, also return the best constraint-satisfying candidate(s) under it. Ties are all returned.

**Output:** counts (enumerated, invalid, infeasible, failing constraints, on frontier); every frontier candidate with its parameter values, per-scenario metrics, exposure, and fingerprint; binding constraints for each returned candidate; and the objective, if any, echoed verbatim. If the frontier exceeds the response limit, the result says so and returns candidates in enumeration order up to the limit. It never applies an undeclared ranking to choose which to show.

**Guardrails.** Results are `PricingRecommendation` records with `approval_state = PENDING_HUMAN_REVIEW` (§6.3). The engine never invents parameter ranges or objectives. An advisory agent may propose a `search_spec`, and the spec must be shown to the user before it runs.

## 7. Evidence and governance

### 7.1 Evidence classes

Preserve research classifications [R]:

- `A_DIRECT`: directly documented claim;
- `B_CORROBORATED`: independently supported generalized claim;
- `C_INFERENCE`: analytical interpretation;
- `D_PROPOSED`: proposed mechanism not established as industry practice.

Evidence strength is independent of prevalence (`ESTABLISHED_COMMON`, `DOCUMENTED_SPECIALIZED`, `EMERGING`, `UNVERIFIED`). A claim may be direct but specialized.

### 7.2 Provenance schema

Each claim SHALL store: claim ID, atomic statement, classification, prevalence, source references, applicability (provider, provider type, jurisdiction, service, date range), date verified, reviewer, and caveats. Each source SHALL store publication date if known and `date_unknown = true` otherwise, plus `verified` (default false). Source URLs from the report MUST be independently checked before being marked verified; the `cite…` tokens in the report are not durable identifiers. Appendix D lists verification priorities.

Evidence ships as pack data. Entries stay `verified = false` until a maintainer checks the source and records a retrieval date. Contributed evidence MUST include source URL, retrieval date, and the exact supported statement.

### 7.3 Approval policy

The system SHALL emit warnings and approval requirements (it does not run an approval workflow) for:

- contribution below a user-supplied policy floor;
- undefined pricing unit or missing counting rule;
- missing commitment terms or missing accumulation/recognition rules;
- ambiguous tier logic or an ALL_UNITS cliff (`TIER_CLIFF`); `[V3-15]`
- unbounded fixed-fee volume;
- pack-defined constraint rules (for example, the ALSP pack's contingent-fee and regulated-work rules);
- material uncapped SLA exposure;
- floor/cap conflicts (`requires_contract_interpretation`);
- capacity breach under any breach mode;
- declared/derived risk mismatch (`RISK_MISMATCH`);
- outcome fees without a cap or recorded approval (`UNCAPPED_OUTCOME_FEE`, `OUTCOME_FEE_APPROVAL`), and SLA credits or bonuses without `cap_percent` (`UNCAPPED_PERFORMANCE_ADJUSTMENT`);
- missing evidence for asserted market benchmarks.

Thresholds are user-supplied policy, not embedded industry facts. A check whose threshold is not supplied reports the measured value without a pass/fail verdict.

## 8. Data contracts and implementation shape

### 8.1 Packages `[V3-16]`

One distribution, `cometric`:

```
src/cometric/
  core/               domain-neutral engine
    models.py, enums.py          input models and controlled vocabularies
    money.py, quantities.py      decimals, rounding, exact allocation, scenario quantities
    periods.py, tiers.py         calendar segments, accumulation keys, tier pricing and cliffs
    ledger.py, engine.py         entitlement ledger; evaluation order, costs, capacity, metrics
    validation.py, issues.py     schema and semantic validation with JSON Pointer issues
    api.py                       public operations (§8.3), comparison, search, floor, break-even, risk
    fingerprint.py               canonical serialization and hashing
    predicates.py, packs.py      rule language; pack loading, validation, lookup, rule evaluation
    templates.py, schema.py      core templates; JSON Schema export
  packs/              data only, no Python
    base/  alsp/  consulting/
  examples/           casebook fixtures A to H and the §8.2 example
  mcp/                MCP server (stdio and HTTP)
  cli.py              command-line interface
scripts/              fixture and template generators
tests/                unit, property, regression, conformance, MCP
```

v0.2's separate `advisory` subpackage was not needed: comparison and search live in `core.api`, evidence lookup in `core.packs`, and the guided workflows are MCP prompts.

**Import boundaries** (enforced by test, T-028): `core` imports neither `mcp` nor `cli`; `packs/` contains no Python. The MCP server is an optional extra (`pip install "cometric[mcp]"`).

### 8.2 Example engagement input [D, illustrative]

This example passes validation as specified. It declares no packs, so it validates against the core alone (T-027).

```json
{
  "schema_version": "0.2",
  "engagement_id": "EX-MANAGED-001",
  "currency": "USD",
  "start_date": "2027-01-01",
  "end_date": "2027-12-31",
  "money_policy": {
    "rounding_mode": "HALF_UP",
    "rounding_scale": 2,
    "rounding_level": "LINE_ITEM"
  },
  "unit_definitions": [
    {
      "code": "accepted_contract_review",
      "kind": "COUNT",
      "counting_rule": "One completed review of one eligible contract",
      "acceptance_rule": "Accepted on client sign-off or 5 business days after delivery without rejection",
      "exclusions": ["Contracts over 100 pages", "Non-English contracts"]
    }
  ],
  "services": [
    {
      "id": "contract_review",
      "unit_definition_id": "accepted_contract_review"
    }
  ],
  "arrangement_versions": [
    {
      "id": "v1",
      "effective_from": "2027-01-01",
      "effective_to": null,
      "supersedes_id": null,
      "adjustment_order": "DEFAULT",
      "components": [
        {
          "id": "base",
          "service_id": "contract_review",
          "calculation_method": "FIXED_RECURRING",
          "billing_basis": "FIXED",
          "charge_cadence": "MONTHLY",
          "currency": "USD",
          "fixed_amount": "100000.00",
          "quantity_source": null,
          "unit": null,
          "effective_period": {"from": "2027-01-01", "to": null},
          "depends_on": []
        },
        {
          "id": "overage",
          "service_id": "contract_review",
          "calculation_method": "ALLOWANCE_OVERAGE",
          "billing_basis": "OUTPUT",
          "charge_cadence": "MONTHLY",
          "currency": "USD",
          "entitlement_id": "base_allowance",
          "rate_schedule_id": "overage_rate",
          "quantity_source": "scenario.accepted_units",
          "unit": "accepted_contract_review",
          "effective_period": {"from": "2027-01-01", "to": null},
          "depends_on": ["base_allowance"]
        }
      ],
      "entitlements": [
        {
          "id": "base_allowance",
          "granted_by": "base",
          "unit": "accepted_contract_review",
          "included_quantity": "1000",
          "accumulation_period": "MONTH",
          "overage_recognition": "PER_SEGMENT",
          "rollover": {"policy": "NONE"}
        }
      ],
      "rate_schedules": [
        {
          "id": "overage_rate",
          "currency": "USD",
          "unit": "accepted_contract_review",
          "tier_method": "MARGINAL",
          "tier_scope": "EXCESS_ONLY",
          "accumulation_period": "MONTH",
          "tiers": [{"from": "0", "to": null, "rate": "120.00"}]
        }
      ],
      "commitments": []
    }
  ],
  "scenario": {
    "id": "base_case",
    "horizon": {"from": "2027-01-01", "to": "2027-01-31"},
    "assumptions": [
      {
        "name": "accepted_units",
        "unit": "accepted_contract_review",
        "value": "1200",
        "time_period": "2027-01",
        "origin": "ILLUSTRATIVE"
      }
    ]
  }
}
```

Expected January 2027 fee: $100,000.00 + (1,200 − 1,000) × $120.00 = $124,000.00 (T-001). The example omits costs and a cost policy, so `calculate_periods` MUST return the fee and reject requests for margin or contribution metrics with an explicit "cost section absent" reason.

### 8.3 Interface contracts

The CLI, Python API, and MCP server expose the same operations. Every operation is stateless (P-10).

**Discovery** (lets an agent with no prior knowledge build valid input):

- `describe_schema(model) -> json_schema` for any input or output model
- `list_packs() -> [{id, version, summary}]` and `describe_pack(id) -> vocabularies, rules, templates`
- `get_template(template_id, pack?) -> engagement skeleton` with required fields present and unknown values marked `"<required>"`
- `list_vocabulary(name, pack?) -> values with definitions`
- `lookup_concept(id_or_query, pack?) -> concept records` with definitions, links, evidence class, prevalence overlays, and claims

**Engine:**

- `validate_engagement(input) -> validation_report`
- `calculate_periods(engagement, scenario, cost_policy, detail?) -> calculation_result`
- `compare_arrangements(candidates, scenario_set, cost_policy, objective?, tolerance_policy?) -> comparison_result`
- `derive_risk_exposure(calculation_results, tolerance_policy?) -> exposure_report`
- `search_structures(search_spec) -> frontier_result`
- `price_floor(engagement, scenarios, cost_policy, target_margin, risk_premium?) -> floor_result` (§5.6)
- `break_even(engagement, scenario, cost_policy, driver) -> break_even_result` (§5.4)
- `explain_fee(engagement, scenario, cost_policy, period, component?) -> line_item_trace`. The engine recomputes deterministically from inputs and returns the trace with the input fingerprint, so no stored calculation is needed.
- `check_commercial_constraints(engagement, policy?) -> warnings_and_approvals` (core checks plus rules from declared packs)

**Evidence:**

- `list_applicable_evidence(claim_or_concept, pack?) -> provenance_records` (claims and their source records, with verification status)

**Reconciliation** `[V3-24]`:

- `reconcile(engagement, scenario, cost_policy, actuals, tolerance_absolute?, tolerance_relative?) -> reconciliation_result`. `actuals` holds recorded figures by month and for the term, as decimal strings or integers. Each compared figure passes within either tolerance (both non-negative). Unknown metrics, malformed months, floats, nulls, and negative tolerances are errors with JSON Pointer paths, never silently skipped. A metric the engine did not compute (costs without a cost policy, realization without a rate card) is reported as not computed, never as zero. Status is `reconciled`, `discrepancies`, `infeasible` (the scenario breaches capacity, so matching figures do not reconcile it), `nothing_compared`, or `invalid`. Failing monthly rows carry that month's fee line items. The result carries its own fingerprint over the inputs, actuals, and tolerances, plus the underlying calculation's fingerprint. `publishable_summary` carries only metric, month of the engagement term (1 = first month of the engagement), relative difference, direction, and the mechanisms priced that month; no amounts, dates, or names.

The MCP server exposes 18 tools: the operations above plus `describe_schema`, `list_packs`, `describe_pack`, `list_templates`, `get_template`, `list_vocabulary`, and `lookup_concept`; `reconcile` is the 18th. `[V3-17]`

**MCP server requirements:**

- Read-only. No tool writes files, calls a network service, or calls an LLM.
- **Transports**: stdio from M2. Streamable HTTP from M4, so web-based clients and hosted connectors can reach Cometric. The HTTP transport MUST be stateless: no session ids, no server-side state, `POST /mcp` only, and `GET /mcp` answered with `405 Method Not Allowed` so clients do not hold idle event streams open. Authentication is the deployer's concern; the server accepts an optional bearer-token check and nothing more.
- Inputs are passed inline, or as file paths when the server runs over stdio with `COMETRIC_ALLOWED_ROOT` set. Paths outside that root are rejected. A file holding a casebook fixture (an object with an `engagement` key) is unwrapped to its engagement. The HTTP transport accepts inline inputs only. `[V3-17]`
- The HTTP transport keeps DNS-rebinding protection on. Allowed `Host` headers default to localhost; deployments set `COMETRIC_ALLOWED_HOSTS` (comma-separated). A bearer token is checked when `COMETRIC_MCP_TOKEN` is set. `[V3-17]`
- Errors are structured: `{code, message, path}` where `path` is a JSON Pointer into the input, so an agent can repair its input.
- `detail` controls result size: `summary` (term and annual totals, metrics, warnings), `periods` (adds monthly rows), `line_items` (adds the full trace).
- Every result carries `engine_version`, `schema_version`, pack versions, the effective money policy, and the input fingerprint.

**MCP resources** (read without spending tool calls):

| URI pattern | Content |
|---|---|
| `cometric://schema/{model}` | JSON Schema for any input or output model |
| `cometric://glossary` | Core terms (§5.1, §5.2, §4.3) with definitions |
| `cometric://packs/{pack}/concepts/{scheme}` | A concept scheme (§3.5, §3.6) |
| `cometric://packs/{pack}/rules` | Constraint and compatibility rules |
| `cometric://templates/{template_id}` | Core engagement templates |
| `cometric://packs/{pack}/templates/{template_id}` | Pack engagement templates |
| `cometric://examples/{case}` | Casebook fixtures (`case_a` to `case_h`) and `spec_example`, with expected results (Appendix C) |
| `cometric://packs/{pack}/coverage` | Evidence strength and readiness by knowledge area, so an agent knows how much to trust each area |

**MCP prompts** (guided workflows that any client can offer its user):

| Prompt | Workflow |
|---|---|
| `model_from_terms` | Turn a term sheet, SOW, or contract summary into a validated engagement: pick a template, fill fields, validate, repair using error pointers, then confirm assumptions and their origins with the user |
| `design_arrangement` | The twelve-step selection sequence [R] (§3.6): characterize the service, identify drivers and uncertainty, capture client preferences, shortlist bases and levers using the selection heuristics, screen constraints, then hand off to `compare_structures` |
| `compare_structures` | Build three candidates (fixed managed service, dedicated capacity, base plus overage, or caller-chosen), run them across low/base/high, present dominance and derived risk |
| `search_structures` | Draft a `search_spec` with the user, show it before running (§6.4), present the frontier and binding constraints |
| `negotiation_options` | Given a proposed concession, list matching exchanges from the negotiation-exchange scheme (§3.6) and quantify each with `compare_arrangements` |
| `explain_result` | Walk a user through a calculation with `explain_fee`, separating contract facts, assumptions, and calculated results |

Prompts instruct the agent; they never contain numbers, benchmarks, or recommendations of their own.

### 8.4 Canonical serialization and fingerprint

`input_fingerprint` = `sha256:` + SHA-256 of the canonical JSON of: operation name, `schema_version`, `engine_version`, engagement (including its arrangement versions and pack references), scenario, cost policy, and the effective money policy. Risk-exposure, comparison, and search results reference the fingerprints of the calculations they are built from. `[V3-18]`

Canonical JSON:

- object keys sorted; no insignificant whitespace; UTF-8;
- decimals serialized as strings in plain notation with trailing zeros removed (`"100000"` and `"100000.00"` serialize identically; in Python, `format(d.normalize(), "f")`);
- dates as ISO 8601 `YYYY-MM-DD`;
- arrays keep declared order, except arrays whose order is semantically irrelevant (components, entitlements, rate schedules, commitments, adjustments, cost components, units, services, versions, assumptions, and similar sets), which are sorted by `id`, `code`, `role`, or `name` plus period;
- run ids, timestamps, and host information excluded.

The engine is deterministic: no floating point, no wall-clock reads, no randomness, no reliance on hash-map iteration order. Components are evaluated in `id` order, so sorting them in the fingerprint is sound: two inputs that differ only in component order produce the same fingerprint and the same results. `[V3-25]`

### 8.5 Persistence

v1 has no database. Engagements, scenarios, cost policies, and tolerance policies are versioned JSON or YAML files in the user's own repository. Because results are reproducible from inputs plus fingerprint, storing results is optional; a user who wants an audit record stores the result JSON next to its inputs.

### 8.6 Distribution and release `[V3-17]`

- Published to PyPI as `cometric` under Apache-2.0. The version lives in `pyproject.toml`; `cometric.__version__` reads it from package metadata. `ENGINE_VERSION` and `SCHEMA_VERSION` are separate and change only when calculations or the input schema change.
- CI runs on every push and pull request: lint and format checks, tests on Python 3.11 to 3.13, validation of every shipped pack, and a wheel build smoke-tested in a clean environment.
- A `v*` tag push runs the publish workflow: tests, a check that the tag matches the version, build, strict metadata check, and upload through a PyPI trusted publisher (OIDC, no stored token). The GitHub `pypi` environment only accepts `v*` tags.
- A release is: bump the version, add a `CHANGELOG.md` entry, commit, push, then tag and push the tag.

## 9. Verification and acceptance tests

The test suite MUST include:

| Test ID | Requirement | Expected behavior |
|---|---|---|
| T-001 | Base plus overage | 1,200 units, 1,000 included, $100k base, $120 overage → $124,000.00 |
| T-002 | Minimum with zero consumption | Contractual minimum charged; effective unit cost null with reason |
| T-003 | Marginal versus all-units tiers | Different, correct totals at the same threshold-crossing quantity |
| T-004 | No unit mismatch | Document volume cannot price against a contract rate; weighted units cannot price against a raw-unit rate |
| T-005 | Contract amendment | Prior months retain prior terms unless retroactivity is authorized |
| T-006 | Rollover ledger | Granted units are consumed, rolled, or expired exactly once |
| T-007 | No duplicate minimum | Minimum applied at declared aggregation scope only |
| T-008 | Zero fee | Margin null with reason; never infinity or a division error |
| T-009 | Dedicated FTE low demand | Fee and dedicated labor cost unchanged absent contractual or cost change |
| T-010 | Capacity breach | Each breach mode produces its specified behavior; undeclared mode makes the scenario infeasible |
| T-011 | Evidence provenance | Inference is never serialized as externally verified fact |
| T-012 | Reproducibility | Same inputs and engine version produce identical outputs and fingerprint |
| T-013 | Scope ambiguity | Missing unit counting rule blocks output pricing approval |
| T-014 | Margin versus markup | $75 cost, $100 price → 25% margin and 33.33% markup |
| T-015 | Annual versus monthly | Annual totals equal the sum of monthly fees and costs |
| T-016 | Casebook | Fixtures A to G reproduce the report's published results, and Case H its stated results, under Appendix C rules |
| T-017 | ALL_UNITS cliff | $10 below 1,000 / $9 from 1,000 emits one `TIER_CLIFF` per threshold with bands [(900 exclusive, 1000)]; a three-tier schedule reports a band in each earlier tier, with an inclusive edge where needed |
| T-018 | Proration | A version effective 2027-03-16 under `CALENDAR_DAYS` charges 15/31 and 16/31 of the two fixed amounts; omitting `proration_policy` fails validation |
| T-019 | Fingerprint normalization | `"100000"` and `"100000.00"` inputs yield the same fingerprint; reordering components yields the same fingerprint |
| T-020 | Dependency graph | A cycle in `depends_on` fails validation; an `ALLOWANCE_OVERAGE` component without its entitlement in `depends_on` fails validation |
| T-021 | Margin layer partition | A cost policy mapping one category to two layers, or leaving a category unmapped, fails validation |
| T-022 | Derived risk exposure | Casebook labels match Appendix C table C.3 |
| T-023 | Recognition timing | `CUMULATIVE` and `PERIOD_END` produce identical annual totals and different monthly distributions for Case A high demand |
| T-024 | Floor/cap conflict | Minimum greater than cap at the same scope returns `requires_contract_interpretation` |
| T-025 | Exact allocation | $880,000/year spread monthly sums to exactly $880,000.00 |
| T-026 | Example validity | The §8.2 example validates and produces T-001's result |
| T-027 | Core conformance | T-001 to T-026 (except T-011) pass with no packs installed |
| T-028 | Import boundaries | `core` imports no other subpackage; `packs/` contains no Python files |
| T-029 | Template round trip | Every shipped template, once `"<required>"` fields are filled, validates; unfilled, it fails with a JSON Pointer per missing field |
| T-030 | Dominance | With three candidates where one is worse on both default metrics in every scenario, it is reported dominated; no candidate is ranked without a supplied objective |
| T-031 | Structure search | Case A with base fee {900k, 1.2M, 1.5M} × overage rate {100, 120, 140} across low/base/high: same frontier on repeated runs; a grid above `max_candidates` is rejected with its size; every invalid candidate is counted by reason |
| T-032 | Pack validation | A concept file with a dangling reference, a reused id, an unknown core vocabulary value, or a Python file in the pack directory fails validation |
| T-033 | Research capture | Every report identifier (BB, PM, CL, FM, CHI, EC, REL, RULE, E) and every row of the compatibility, decision-matrix, mechanism, negotiation, and dimension tables appears in the base or ALSP pack, or in `packs/base/excluded.yaml` with a reason |
| T-034 | Price floor | Case B, 12,000 contracts, 20% target, no premium → $1,125,000 and $93.75 per contract; `m_t ≥ 1` fails validation |
| T-035 | MCP surface | Every listed resource URI resolves for the installed packs; every prompt renders; HTTP transport returns 405 on `GET /mcp` and keeps no state between requests |
| T-036 | Outcome SHARE `[V3-19]` | 25% share, 80% attribution, baseline 1,000,000, outcome 1,300,000 → 60,000 in the period's last month only; capped at `cap_amount`; never negative; `LOWER_IS_BETTER` inverts the improvement |
| T-037 | Outcome SUCCESS and PERCENT `[V3-19]` | Success fee charged at the target and not one unit below it; percent of outcome applies share and attribution |
| T-038 | Outcome prerequisites `[V3-19]` | Missing baseline or attribution fails validation; missing cap or approval raises approval requirements; non-`PERIOD_END` recognition fails; a period ending after the horizon raises `TRUE_UP_OUTSIDE_HORIZON` |
| T-039 | Realization `[V3-19]` | Case D with a $200 rate card and 6,000 worked hours → standard value 1,200,000, realization 0.75, write-down 300,000, effective billing rate 150; a rate card without worked hours fails with a pointer to `worked_hours_source` |
| T-040 | Consulting pack `[V3-19]` | The pack validates; each of its five templates round-trips (T-029); Case H fires CONS-R-001 (approval) and CONS-R-003 |
| T-041 | Pack templates over MCP `[V3-19]` | `cometric://packs/{pack}/templates/{id}` resolves for every pack template |
| T-043 | Engine review regressions `[V3-25]` | Full-month policies bill whole months; a project payment in a split month posts; a mid-year horizon carries the annual allowance; one-time and annual fees keep their totals; collars reprice at the cumulative tier position; cumulative and period-end overage index identically and project payments are not indexed; a later-starting term cost keeps its total; the incurred view ignores portfolio costs; a missing trigger is an error; the price floor needs costs; quarterly shares anchor at the component start; contract years honor the start day; component order never changes results |
| T-042 | Reconciliation `[V3-24]` | Actuals equal to computed figures reconcile; a changed July invoice is reported at month 7 with the mechanism that priced it; the publishable summary contains no amounts, dates, or names; relative tolerance and unknown metrics are honored |

**Property tests** SHOULD verify: non-negative accepted units; non-overlapping effective dates; contiguous tiers; under `MARGINAL` tier schedules with non-negative rates, the pre-credit fee never decreases when eligible consumption increases, holding other terms fixed. Under `ALL_UNITS` schedules the property holds outside every band reported by `TIER_CLIFF` and is not asserted inside them. T-033 runs only when the private research report is present; CI skips it.

## 10. Delivery milestones `[V3-01]`

| Milestone | Deliverable | State |
|---|---|---|
| M0: Schema freeze | Schema, glossary, JSON Schema export | Superseded: the engine was built directly and this document records the decisions it surfaced. |
| M1: Core engine | Engine, validation, fingerprinting, CLI, casebook | Done. |
| M2: Compare, optimize, MCP | Dominance, structure search, risk exposure, MCP with discovery, core templates | Done. |
| M3: Knowledge packs | Pack loader and rule language; `base` and `alsp` packs; evidence; resources and prompts; price floor and scenario-mode indicators | Done; 33 of 39 sources verified (Appendix D). |
| M4: Public release | PyPI release, documentation, HTTP transport, real-engagement reconciliation | Released as 0.1.0; reconciliation outstanding. |
| M5: Consulting pack | Realization, outcome pricing, consulting pack | Done; reconciliation outstanding. |
| M6: Reconciliation | One real consulting engagement reconciled privately; discrepancies (not client data) published | Tooling built (`reconcile`, `docs/RECONCILIATION.md`); waiting on engagement data. |
| M7: Actuals mode | Recorded monthly actuals; the health indicators that need them (CHI-004, 005, 006, 008, 009, 010, 012) | Planned. |

Do not claim real-world accuracy from the illustrative casebook alone.

## 11. Resolved decisions and remaining questions

### 11.1 Resolutions

v0.1 framed most open decisions as questions for one organization's stakeholders. As an open-source engine, the general answer is: **the engine takes the policy as input, requires it where economics depend on it, and ships a documented reference where a sensible one exists.** [D]

| ID | v0.1/v0.2 question | Resolution |
|---|---|---|
| R-1 | Who owns margin policy, exceptions, and approval thresholds? | The user. Policies are input files with `id`, `version`, and `owner` fields, included in the fingerprint. The engine emits approval requirements; workflow is out of scope (§2.2). |
| R-2 | Which cost categories map to which margin layer? | Caller-supplied `CostPolicy`, required. The core ships `reference` (§5.2), selectable only by name. |
| R-3 | Monthly granularity; multicurrency? | Monthly grain with day segments (§4.6) is sufficient for v1. One currency per engagement in v1; every money value still carries its currency, so multicurrency can be added without a schema break. Mixed currencies fail validation. |
| R-4 | Which engagement is the pilot? | Replaced by public synthetic fixtures (Appendix C) and a private practitioner reconciliation at M4 that publishes discrepancies, not client data. |
| R-5 | What counts as an accepted unit; who adjudicates complexity? | Not the engine's decision. `counting_rule`, `acceptance_rule`, and `classification_authority` are required fields; packs supply templates with prompts, never values. |
| R-6 | Productive-ratio and safe-utilization assumptions? | Caller-supplied, required whenever capacity is modeled, `origin = INTERNAL_POLICY`. Fixtures carry illustrative values only. |
| R-7 | How are amendments and retroactivity represented? | An amendment creates a new `PricingArrangementVersion` with `supersedes_id`, plus an amendment record (affected terms, effective date, retroactivity flag). A retroactive run produces a new result linked to the original fingerprint; nothing is overwritten (§4.6). |
| R-8 | Who verifies evidence? | Maintainers, through pull requests. Evidence ships `verified = false` until a source check is recorded (§7.2). |
| R-9 | What does a recommendation optimize? | Nothing by default. Comparison reports dominance (§6.2); a weighted or constrained objective is applied only when supplied and is recorded in the result. |
| R-10 | Persistence: files or database? | Files (§8.5). No database in v1. |
| R-11 | Default recognition rule for annual allowances and minimums? | No default in the schema (P-07). Templates prefill `CUMULATIVE` visibly, since it reflects consumption as it happens and is the more common reading of "included volume". |
| R-12 | Casebook regression baseline? | Both. As-published proves the engine reproduces the report; `reference` is the policy the project recommends. |
| R-13 | Rounding mode and level? | Optional `money_policy` with a documented default: `HALF_UP`, ISO 4217 minor units, `LINE_ITEM`. Echoed in results and fingerprinted (§4.7). |
| R-14 | Risk tolerances? | Optional, caller-supplied. Without them the engine reports raw exposures and no labels (§5.5). |
| R-15 | Collar forms? | v1 supports one: an alternate rate schedule outside the band. Shared-loss collars are post-v1. |

### 11.2 Remaining open questions `[V3-20]`

- **Q-1 Resolved: name.** Cometric; distribution, import package, CLI, and MCP server are all `cometric`. A trademark search is still advisable; the plural "Cometrics" is used by unrelated companies.
- **Q-2 Resolved: license.** Apache-2.0.
- **Q-3 Resolved in practice: research report.** Kept out of the repository; its knowledge ships as pack data.
- **Q-4 Resolved: second domain pack.** Consulting, built.
- **Q-5 [O] Evidence that names firms.** Pack text never names firms; source URLs do, because they are citations. Decide whether that stays.
- **Q-6 [O] Remaining evidence.** Four sources block automated access and need a manual check; two are behind registration forms (Appendix D).
- **Q-7 [O] Cumulative outcome recognition.** Should outcome fees support month-by-month recognition for metrics that accrue (for example, recoveries), or stay period-end only?
- **Q-8 [O] Other commitment kinds.** Which of `MINIMUM_VOLUME`, `RESERVED_CAPACITY`, and `PREPAID_CREDIT` should be computed next, and with what semantics?
- **Q-9 [O] Mid-period amendments.** Should allowance grants be prorated when a version starts mid-period, and should adjustments split by segment within a month?
- **Q-10 [O] Custom evaluation orders.** Is there a real contract that needs one?

## 12. Decisions recorded in v0.3

- Outcome-based fees are a v1 method with three forms, charged at period end, with baseline, attribution, cap, and approval prerequisites (§4.1). [D]
- Realization uses an engagement-level standard rate card and applies under any billing method (§5.4). [D]
- Tier counters and capacity limits are always cumulative; allowances, minimums, and outcomes declare recognition (§4.2, §4.3). [D]
- Only the default evaluation order exists in v1, with the step semantics in §4.5. [D]
- Only `MINIMUM_SPEND` commitments are computed in v1 (§4.4). [D]
- No separate advisory subpackage (§8.1). [D]
- Release by tag push through a trusted publisher (§8.6). [D]

The decisions recorded in v0.2 §12 stand.

---

## Appendix A. Research-to-implementation traceability

This table summarizes by implementation location. §3.6 is the authoritative item-by-item map, and T-033 verifies it.

| Research domain | Initial implementation location | Status |
|---|---|---|
| Ten billing bases and normalized pricing taxonomy | `core.enums`, `core.engine` | Mapped to eight bases + cadence (§3.2); frozen at M0 |
| 61 commercial levers (the report text states 58; its catalog lists 61: 12 CL-R, 12 CL-V, 13 CL-D, 15 CL-P, 9 CL-VL) | Mechanics in `core.engine`; catalog in `packs/base`, legal-sector overlays in `packs/alsp` | Mechanics for the v1 subset at M1; catalog at M3; near-duplicates (CL-R01/CL-R02/CL-V06; CL-R05/CL-VL03/CL-VL04) consolidated in the catalog |
| 35 financial metrics | `core.engine`; definitions in `packs/base/concepts/metrics.yaml` | Priority subset M1; accounting metrics deferred |
| 34 candidate entity classes | `core.models` | Collapsed to core aggregates for v1 |
| 20 proposed semantic relationships | `core.models`; mapping in `packs/base/concepts/schema_map.yaml` | Reconciled against typed schema at M0 |
| Six illustrative cases | `src/cometric/examples`, `tests` | Regression baseline per Appendix C, plus Cases G and H |
| Evidence register E001 to E040 | `packs/base` and `packs/alsp` evidence | 33 of 39 verified; E017 excluded (Appendix D) |
| Regulatory constraints | `packs/alsp` constraint rules | Warning/approval requirement only; no automated legal determination |
| Provider-type limitations matrix | `packs/alsp` vocabulary and rules | Built |
| AI cost and automation benefit | `core.engine` cost categories | Cost categories M1; sophisticated inference post-v1 |
| Adjacent-sector mechanisms | `packs/base` mechanisms; cited by the consulting pack | Design candidates, not universal practice |

## Appendix B. Explicit non-claims

This specification does not assert that any particular pricing structure is universally optimal, that a fixed margin target is industry standard, that unused commitments predict churn, that an ALSP can legally use every modeled fee type, or that the illustrative scenario prices reflect actual market rates. Such claims require evidence, internal policy, or legal review beyond the supplied report.

## Appendix C. Casebook fixture specification

### C.1 Common rules

- All fixtures: USD, horizon 2027-01-01 to 2027-12-31, `money_policy` HALF_UP / 2 / LINE_ITEM, all assumptions `origin = ILLUSTRATIVE`.
- Annual fees, annual costs, and annual demand are spread monthly using exact allocation (§4.7) with `demand_distribution = FLAT`. Raw units per complexity band are allocated per band.
- Annual allowances, tiers, and capacities use `accumulation_period = YEAR` and `CUMULATIVE` recognition.
- T-016 compares annual totals. Currency amounts must match the report exactly. Margins must match the report's one-decimal presentation to within 0.05 percentage points.
- Each fixture runs under two cost policies: **as-published**, reproducing the report's classification, and **harmonized**, which is the core `reference` policy (§5.2). Both are regression baselines (§11, R-12). Where the two give the same result, only one set of expected values is listed.
- Fixtures A to G declare no packs, so they also serve the core conformance test (T-027). Case H declares the consulting pack.
- Fixtures live in `src/cometric/examples/` (served as MCP resources) and are generated by `scripts/build_fixtures.py` and `scripts/build_consulting.py`. `[V3-21]`
- Values marked *(v0.2)* or *(v0.3)* below are assumptions this specification adds because the report does not state them. They do not change annual results.

### C.2 Fixtures

**Case A: annual managed-services commitment.**
Components: `FIXED_RECURRING` $100,000/month; `ALLOWANCE_OVERAGE` $120/unit against a 12,000-unit annual entitlement. Costs: fixed delivery labor $540,000, platform operations $120,000, variable $18/unit → `DIRECT_DELIVERY`; client governance $60,000, transition $80,000 (amortized view) → `ENGAGEMENT_AVOIDABLE`. Capacity 14,000 units/year, breach mode `OVERFLOW_COST` (rate not needed; the high case equals capacity and is not a breach).
Expected: low 6,000 → fee $1,200,000, GP $432,000, CP $292,000; base 10,000 → $1,200,000 / $360,000 / $220,000; high 14,000 → $1,440,000 / $528,000 / $388,000.

**Case B: variable-volume contract review.**
`UNIT_OUTPUT` $95/contract. Costs: $52/contract and fixed QA/platform $216,000 → `DIRECT_DELIVERY`; account management $60,000 → `ENGAGEMENT_AVOIDABLE`.
Expected: low 6,000 → fee $570,000, CP −$18,000; base 12,000 → $1,140,000 / $240,000; high 18,000 → $1,710,000 / $498,000. Break-even 6,418.604651… exact, 6,419 whole units.

**Case C: dedicated team priced per FTE.**
`DEDICATED_RESOURCE` 8 FTE × $16,000/month. Costs: loaded labor $110,000/FTE/year and delivery management $120,000 → `DIRECT_DELIVERY`; platform/support $60,000 and transition $40,000 → `ENGAGEMENT_AVOIDABLE` (as published). Productive capacity 1,600 hours/FTE/year.
Expected: fee $1,536,000, direct $1,000,000, GP $536,000 (34.9%), CP $436,000 (28.4%) at every utilization level. Client price per used hour: 55% → $218.18, 80% → $150.00, 95% → $126.32.
Harmonized variant: platform/support → `DIRECT_DELIVERY` (consistent with Cases A and E). GP $476,000 (31.0%); CP unchanged.

**Case D: fixed-fee CLM migration.**
`FIXED_PROJECT` $900,000, payment schedule $75,000/month *(v0.2)*. Costs: delivery hours × $80 and third-party $100,000 → `DIRECT_DELIVERY`; engagement cost $50,000 → `ENGAGEMENT_AVOIDABLE`. Hours spread flat *(v0.2)*. Driver for §5.5 is delivery hours, not volume.
Expected: efficient 4,000 h → CP $430,000; expected 6,000 h → $270,000; overrun 8,500 h → $70,000. Break-even 9,375 hours.

**Case E: AI-enabled review.**
`FIXED_RECURRING` $15,000/month; `UNIT_OUTPUT` $25/document. Costs: platform operations $120,000, inference $1.50/document, QA `TIERED_VARIABLE` marginal ($8 to 10,000; $6 to 30,000; $4 above; annual reset) → `DIRECT_DELIVERY`; engineering amortization $100,000 → `ENGAGEMENT_AVOIDABLE` (as published).
Expected: low 10,000 → fee $430,000, direct $215,000, CP $115,000; base 25,000 → $805,000 / $327,500 / $377,500; high 50,000 → $1,430,000 / $475,000 / $855,000. Break-even 2,580.645… exact, 2,581 whole units.
Harmonized variant: engineering amortization → `PORTFOLIO_SHARED`, per the report's guidance that reusable platform build belongs in a separate investment pool. CP rises by $100,000 in every scenario (low CP $215,000, 50.0%).

**Case F: base plus complexity-weighted volume.**
`FIXED_RECURRING` $25,000/month; `WEIGHTED_UNIT_OUTPUT` $70/weighted unit; weights standard 1.0, medium 1.8, complex 3.0. Costs: fixed $270,000 and $35/weighted unit → `DIRECT_DELIVERY`; transition $40,000 → `ENGAGEMENT_AVOIDABLE`. `classification_authority = JOINT` *(v0.2)*.
Expected: low 5,000 at 70/20/10 → 6,800 WU, fee $776,000, direct $508,000; base 10,000 at 60/25/15 → 15,000 WU, $1,350,000 / $795,000; high 16,000 at 50/30/20 → 26,240 WU, $2,136,800 / $1,188,400.

**Case G (new): capacity breach.** *(v0.2, not in the report)*
Case A with demand 16,000 units and `OVERFLOW_COST` at $40/unit replacing the $18 variable rate for units above capacity.
Expected: fee $1,200,000 + 4,000 × $120 = $1,680,000; direct $660,000 + 14,000 × $18 + 2,000 × $40 = $992,000; GP $688,000; CP $548,000; overflow recognized in November and December under cumulative capacity. Variants: `BACKLOG` carries 2,000 units past the horizon with an SLA warning; `INFEASIBLE` and undeclared mode fail feasibility (T-010).

**Case H (new): consulting phased fixed fee plus gain-share.** *(v0.3, illustrative, not from the report)* `[V3-21]`
`FIXED_PROJECT` $600,000 paid $150,000 / $250,000 / $200,000 in March, July, December; `OUTCOME_ADJUSTMENT` SHARE of 10% with 70% attribution on reduction of annual addressable spend below a $10,000,000 baseline (`LOWER_IS_BETTER`), capped at $100,000. Costs: 4,000 delivery hours at $90 → `DIRECT_DELIVERY`; engagement overhead $30,000 → `ENGAGEMENT_AVOIDABLE`. Standard rate card: partner $400 (500 hours), consultant $175 (3,500 hours). Declares the consulting pack; service category `TRANSFORMATION`; provider type `BOUTIQUE`.
Expected under `reference`: spend 9,900,000 → outcome fee $7,000, fee $607,000, CP $217,000; 9,500,000 → $35,000 / $635,000 / $245,000; 9,000,000 → $70,000 / $670,000 / $280,000. Standard value $812,500 in every scenario; base realization 0.7815.

### C.3 Expected derived risk labels (T-022)

Illustrative tolerance: zero (any adverse movement counts). Base case is the report's expected scenario.

| Case | Deviation | Provider downside | Client downside (unit price) | Derived bearer |
|---|---|---|---|---|
| A | Low demand | −$72,000 (gain) | +$80.00 ($200.00 vs $120.00) | CLIENT |
| A | High demand | −$168,000 (gain) | −$17.14 ($102.86 vs $120.00) | NONE_ADVERSE |
| B | Low demand | +$258,000 | $0.00 | PROVIDER |
| C | Low utilization | $0 | +$68.18 per used hour | CLIENT |
| D | Hours overrun | +$200,000 | $0.00 | PROVIDER (effort risk) |
| E | Low demand | +$262,500 | +$10.80 ($43.00 vs $32.20) | SHARED |
| F | Low demand | +$287,000 | +$24.12 per weighted unit ($114.12 vs $90.00) | SHARED |

## Appendix D. Evidence verification status `[V3-22]`

Sources were fetched on 2026-11-03 and rechecked on 2026-11-04 against the claims the research uses them for. Each source record carries a `verification` block with the verdict, date, and note.

| State | Count | Sources |
|---|---|---|
| Verified as cited | 27 | including E034, checked against the full supervisory statement |
| Verified at a new URL | 3 | E013, E019, E027 |
| Verified after narrowing the claim to what the source states | 3 | E008, E016, E032 |
| Partial: detail behind a registration form | 2 | E001, E040; affected claims carry a caveat |
| Not checked: publisher blocks automated access | 4 | E028, E029, E035, E039 |
| Excluded | 1 | E017; no claim depends on it |

The v0.2 anomalies are resolved: E037's hosting reflects a corporate relationship between the two providers and the page supports the claim; E014's page does state per-document and per-custodian pricing; E015 supports only the fixed monthly subscription point; E018's document date is 2015 and the URL path is an upload folder; E006's rate range is confirmed; E008 states a monthly fee without a per-user basis, and the claim was narrowed.
