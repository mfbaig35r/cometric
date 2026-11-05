# Cometric | Commercial Intelligence Engine

**Engineering Requirements v0.2**

Cometric does three things:

1. **Model.** Understand commercial arrangements through a structured ontology: a domain-neutral core plus domain packs (§3, §4).
2. **Simulate.** Calculate engagement economics and evaluate alternative scenarios, deterministically (§5, §6.1 to §6.2).
3. **Optimize.** Recommend commercial structures that balance profitability, risk, and client value, by searching candidate structures and reporting the trade-off frontier (§6.4).

It is built for any service relationship priced through a composite arrangement: consulting, outsourcing, managed services, and alternative legal services, with further industries added as packs.

| | |
|---|---|
| Project | Cometric (`cometric` on PyPI; CLI and MCP server `cometric`) |
| Status | Draft for architectural review. Open-source project. |
| License | Apache-2.0 |
| Date | November 3, 2026 |
| Supersedes | `ALSP_COMMERCIAL_ONTOLOGY_SPEC_v0.1.pdf` |
| Source foundation | `alsp-commercial-models-deep-research.md` (research cutoff November 3, 2026). Note: the report header states an execution date of November 4, 2026, which postdates this specification; the report should be corrected. |
| Target implementation | Python 3.11+, Pydantic v2 (strict), deterministic calculation library, stateless read-only MCP server and CLI |
| Scope | A domain-neutral engine for the structure and economics of service engagements: commercial design, engagement evaluation, scenario comparison, structure search, and evidence-backed advisory reasoning. Domain vocabulary ships as packs; the Alternative Legal Services Provider (ALSP) pack is first and consulting is second. Not a general ledger, invoicing system, approval workflow, or automated contracting platform. |

> **Evidence convention.** **[R]** marks a concept documented or explicitly proposed in the research report; it does not imply independently reverified external sources. **[D]** marks a design decision proposed in this specification. **[O]** marks a question still open for the maintainers (§11). Illustrative values are not market benchmarks. The research report's source register remains the evidence source; individual claims must be linked to that register before they ship in a pack.
>
> **Change markers.** `[C-nn]` marks text that is new or materially changed since v0.1. Each marker is listed in the change log.

---

## 0. Changes from v0.1

| ID | Section | Change | Reason |
|---|---|---|---|
| C-01 | 3.2 | Billing basis reduced to eight values; recurrence and milestones move to a separate `ChargeCadence` axis; RESOURCE vs CAPACITY given a discriminating rule; source vocabulary mapped. | v0.1 deferred this but made it an M0 exit criterion. The report already separates cadence (report §"Multidimensional commercial model") while keeping ten values in its controlled vocabulary. |
| C-02 | 4.1 | `calculation_method` is authoritative; `billing_basis` is a validated classification. Components declare `depends_on`; evaluation is a dependency graph. The combined "allowance + overage" method is replaced by an `ALLOWANCE_OVERAGE` component that references an entitlement. | v0.1 called components "independently computable" while the overage in its own example depends on the allowance ledger. |
| C-03 | 4.1 | New v1 methods `WEIGHTED_UNIT_OUTPUT` and `FIXED_PROJECT`. | Casebook Cases D and F (required by T-016) had no supported method. |
| C-04 | 4.2 | Tier intervals made half-open and contiguous; tiers declare scope and reset period; ALL_UNITS cliff detection added. | ALL_UNITS schedules are non-monotonic below thresholds; v0.1's property test was false for them. |
| C-05 | 4.3 | New: accumulation periods. Allowances, minimums, tiers (revenue and cost), and capacity are evaluated against a declared period independent of the monthly grain. | Casebook allowances, QA cost tiers, and capacity are annual; the engine grain is monthly. |
| C-06 | 4.5 | Evaluation order corrected (allowance consumption before tier pricing); collars, caps and not-to-exceed added; minimum test position made explicit. | v0.1 priced tiers before netting allowances and omitted caps and collars that were in v1 scope. |
| C-07 | 4.6, 4.7 | New: proration rules and money/rounding rules, including exact allocation of period totals. | Mid-month effective dates and annual-to-monthly spreading were undefined; T-012 and T-016 depend on both. |
| C-08 | 5.1, 5.4 | Single term `contractual_fee`; "contractual revenue" removed. | v0.1 banned revenue labels in §5.1 and used one in §5.4. |
| C-09 | 5.2 | Costs assigned to exactly one margin layer through a `CostPolicy`; contribution defined on that partition; `TIERED_VARIABLE` cost behavior; transition cost carries timing. | v0.1 formula could double-count avoidable direct costs and disagreed with report FM-018. Case E's QA cost could not be expressed. Payback month was uncomputable from annualized transition cost. |
| C-10 | 5.3 | New: production standards (time per unit); capacity period; declared breach mode. | Capacity in hours could not be compared with demand in units. |
| C-11 | 5.5 | New: derived risk exposure from scenario comparison. | §1 question 3 and §6.2 "risk-bearing changes" required risk allocation to be derived, not only declared. |
| C-12 | 8.1 | Engine and advisory split into two packages. | Keeps evidence and advisory concerns out of the M1 deliverable. |
| C-13 | 8.2 | Example rewritten to pass its own validation. | v0.1 example omitted fields marked MUST in §4.1. |
| C-14 | 8.4 | New: canonical serialization and fingerprint. | T-012 reproducibility was underspecified. |
| C-15 | 9 | Property test corrected; tests T-017 to T-026 added; casebook fixture rules defined. | See C-04 to C-11. |
| C-16 | 10 | M0 permits a disposable engine spike over Cases A to C. | Most semantic gaps only surface when fixtures are executed. |
| C-17 | App. A, C, D | Lever count corrected to 61; new casebook fixture specification; evidence verification priorities. | The report text says 58 levers; its catalog lists 61. |
| C-18 | 11 | New open decisions 11 to 15. | Raised by C-04, C-05, C-09, C-11. |
| C-19 | Header, 1, 2 | Project is open source and domain-neutral; ALSP becomes the first domain pack. | Decision to publish the engine as a general-purpose tool. |
| C-20 | 2.3 | P-07 refined (formatting conventions may have documented defaults; economic policies may not). New P-09 domain neutrality and P-10 stateless operation. | Usability for unknown users without weakening the no-fabrication rule. |
| C-21 | 3.4 | New: domain packs. | Separates generic arithmetic from legal-sector vocabulary, rules, and evidence. |
| C-22 | 5.2 | New: shipped `reference` cost policy, selectable by id. | Users need a sensible starting point; selection stays explicit. |
| C-23 | 6.2 | Comparison reports dominance (Pareto) by default; weighted objectives only when supplied. | Resolves v0.1 open decision 9 without embedding a business objective. |
| C-24 | 8.1, 8.3, 8.5 | One distribution with core, packs, advisory, and MCP subpackages and enforced import boundaries; MCP tool surface defined; `explain_fee` made stateless; file-based persistence. | Universal MCP use by any agent; reproducibility without a server-side store. |
| C-25 | 9, 10 | Tests T-027 to T-030; milestones rewritten for an open-source project (no internal stakeholder sign-offs; MCP moves to M2). | Follows C-19 to C-24. |
| C-26 | 11 | All v0.1 and v0.2 open decisions resolved; remaining questions are project-level. | Follows C-19. |
| C-27 | Header, 8 | Project named Cometric; Model / Simulate / Optimize framing. | Naming decision. |
| C-28 | 3.5 | New: pack concept-file format. Packs are data only. | v0.2 listed pack contents without defining their format; data-only packs let the community contribute without executing code. |
| C-29 | 6.4 | New: structure search (Optimize). | Turns "Optimize" into a deterministic search that respects the §6.3 guardrails. |
| C-30 | 3.4, 10, 11 | Consulting named as the second pack, with two core prerequisites (realization, outcome pricing). | Tests different methods from ALSP and gives the project a first real user. |
| C-31 | 3.4, 3.6, 8.3 | New: domain-neutral `base` knowledge pack with a full map of where each part of the research lands; MCP resources, prompts, `lookup_concept`; stateless HTTP transport at M4. | v0.2 captured the report's arithmetic but left most of its declarative knowledge without a home; stdio alone limits reach to local clients. |
| C-32 | 5.6 | New: price floor operation and scenario-mode health indicators. | Report formulas and indicators that the engine can compute but v0.2 omitted. |

---

## 1. Purpose and intended decisions

The system SHALL represent the structure and economics of service engagements, in which a client buys professional, managed, or technology-enabled services under a composite commercial arrangement, in a way that is compositional, explainable, time-aware, and testable. Alternative Legal Services Provider (ALSP) engagements are the first supported domain, delivered as a domain pack (§3.4); the core engine contains no legal-sector vocabulary. `[C-19]` It SHALL answer questions such as:

1. What exactly is being purchased and billed, and which contractual commitments modify it?
2. What is the expected provider contribution and client effective cost under alternative demand, complexity, staffing, and automation assumptions?
3. Which party bears volume, capacity, performance, scope, and technology-cost risks, both as declared in the contract and as derived from scenario results? `[C-11]`
4. What changes if a fixed monthly service is replaced with a base-plus-overage or capacity-plus-consumption arrangement?
5. Which conclusions are contract facts, calculated results, assumptions, evidence-backed generalizations, or recommendations?

**Success criterion [D].** A user can load a validated engagement definition, run reproducible monthly financial scenarios, compare at least three feasible commercial arrangements, and receive traceable explanations of economic differences without an LLM performing financial arithmetic.

## 2. Product boundaries

### 2.1 In scope for v1

- Typed representation of engagements, parties, services, priced units, fee components, rate schedules, commitments, entitlements, capacity, delivery topology, SLAs, adjustments, risks, and evidence.
- Monthly contractual-fee and cost simulation with annual and term-level aggregation.
- Time-indexed contract amendments, effective dates, and proration. `[C-07]`
- Fixed recurring, time, dedicated resource, unit output, complexity-weighted output, allowance-plus-overage, and fixed project configurations; extensible support for other billing bases. `[C-03]`
- Tiered rates (revenue and cost side); minimum spend; included allowance; overages; credits; collars; caps and not-to-exceed limits where defined. `[C-04, C-06]`
- Dedicated and pooled delivery costs, transition costs, technology costs, QA/rework, and constrained capacity.
- Deterministic calculations and scenario comparison; warnings for incomplete or inconsistent inputs.
- Derived risk exposure from scenario comparison. `[C-11]`
- Provenance and a human-review boundary for recommendations (delivered in the advisory package, §8.1). `[C-12]`
- A domain-pack interface and the ALSP pack (§3.4). `[C-21]`
- A stateless, read-only MCP server and CLI over the engine, including schema and template discovery so any agent can construct valid inputs (§8.3). `[C-24]`
- Deterministic structure search over bounded parameter ranges, returning the trade-off frontier (§6.4). `[C-29]`

### 2.2 Explicitly out of scope for v1

- A hosted service, multi-user persistence, or approval workflow. The engine emits approval requirements; acting on them is the user's process. `[C-19]`
- Domain packs other than ALSP. The pack interface is in scope. The consulting pack follows v1 (§10, M5); further packs are community contributions.
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
- **P-04 [D] Temporal integrity.** Historical periods use the contract version and assumptions effective for that period, at day resolution within a month. `[C-07]`
- **P-05 [D] Provenance.** Source claims, observed client facts, internal policies, forecasts, and illustrative assumptions remain separate.
- **P-06 [D] Dual-sided evaluation.** Assess provider economics and client consumption/value together. Unused commitment must not be labeled automatically as success or failure.
- **P-07 [D] Explicit uncertainty.** Unknowns must not silently become zeroes, defaults, or fabricated market averages. Economic policies (cost policy, capacity ceilings, recognition rules, risk tolerances, margin floors) have no implicit defaults; omitting one that a calculation needs is a validation error. Formatting conventions (rounding) may have documented defaults, provided the effective value is echoed in every result and included in the fingerprint. `[C-20]`
- **P-08 [D] Exact arithmetic.** All money and quantities use decimal arithmetic. Binary floating point is rejected at the schema boundary. `[C-07]`
- **P-09 [D] Domain neutrality.** The core defines structure and arithmetic. Domain vocabulary (service categories, unit templates, provider types), constraint rules, catalogs, and evidence live in packs. The core never imports a pack. `[C-20]`
- **P-10 [D] Stateless operation.** Every operation is a pure function of its inputs. The engine and MCP server hold no state between calls; anything a later call needs is passed back in. `[C-20]`

## 3. Domain model

### 3.1 Core aggregate boundaries

| Aggregate / entity | Meaning | Core fields (illustrative) | Key relationships |
|---|---|---|---|
| Engagement | Evaluated client-provider relationship | id, name, currency, start_date, end_date, status, money_policy, packs | has parties, services, arrangement versions, scenarios |
| ContractParty | Buyer, provider, subcontractor | id, role, jurisdiction, regulated_status, provider_type (optional; pack vocabulary) | participates in engagement; bears risk |
| ServiceOffering | Defined operational obligation | id, service_category (optional; pack vocabulary), scope, unit_definition_id | has SLA, delivery plan, priced units |
| WorkUnitDefinition | Unambiguous measurable output | code, name, kind (COUNT, WEIGHTED, HOURS, FTE_MONTHS), counting_rule, acceptance_rule, exclusions | referenced by volume, output fees, production standards |
| ComplexityWeightTable `[C-03]` | Conversion from raw units to weighted units | id, raw_unit, weighted_unit, bands {code, weight, criteria}, classification_authority, audit_rule | used by WEIGHTED_UNIT_OUTPUT components and production standards |
| PricingArrangementVersion | Effective-dated commercial configuration | id, effective_from, effective_to, supersedes_id, proration_policy, adjustment_order | contains fee components, commitments, entitlements, adjustments |
| FeeComponent | One charge computed by one method | id, service_id, calculation_method, billing_basis, charge_cadence, depends_on | prices a service or entitlement |
| RateSchedule | Rates and tiers | currency, unit, tiers, tier_method, tier_scope, accumulation_period | applies to fee or cost component |
| CommercialCommitment | Minimum spend, minimum volume, reserved capacity | kind, amount, aggregation_scope, settlement_period, tested_against, shortfall_rule | constrains fee components or entitlements |
| Entitlement | What a base fee or commitment purchases | unit, included_quantity, granted_by, allowance_period, overage_recognition, rollover | consumed by recorded activity; referenced by ALLOWANCE_OVERAGE |
| AdjustmentMechanism | Overage, true-up, indexation, collar, cap, credit | type, trigger, formula, scope, step | modifies a named subtotal at a declared evaluation step |
| DeliveryPlan | How work is produced | topology, resource_assignments, capacity_plan, breach_mode | drives cost and capacity, not contractual fee |
| ResourceRole | Costed staffing role | role_code, loaded_cost_rate, availability, productive_ratio | used in delivery plan |
| ProductionStandard `[C-10]` | Effort per unit of output | unit, role_code, complexity_band, hours_per_unit, origin | converts demand units to demand hours |
| CostComponent | Direct or allocated cost | category, behavior, driver, rate, schedule, effective_period, avoidability_class, source_type | classified into a margin layer by the cost policy |
| CostPolicy `[C-09]` | Mapping from cost category to margin layer | id, mapping, owner, effective_period | referenced by every calculation |
| ServiceLevel | Measurable service obligation | metric, target, window, remedy_id | drives quality, credits, bonuses |
| RiskAllocation | Identified exposure and bearer | risk_type, declared_bearer, limit, mitigation | compared with derived exposure (§5.5) |
| Scenario | Immutable time-indexed assumption set | id, baseline_id, assumptions, horizon, demand_distribution, probability_label | evaluates one or more arrangements |
| EvidenceClaim | Atomic proposition | claim_id, text, classification, prevalence, applicability | supported by evidence records |
| EvidenceRecord | Source and applicability | source_id, url, publication_date, date_unknown, retrieved_date, source_type, verified | supports claims |
| CalculationResult | Reproducible output | engine_version, schema_version, input_fingerprint, periods, line_items, metrics, warnings | produced from scenario |
| PricingRecommendation | Advisory comparison, not contract fact | candidate_id, rationale, tradeoffs, assumptions, calculation_ids, approval_state | references results and evidence |

[R] The research proposes 34 candidate entity classes and 20 relationships. This table is a deliberately smaller v1 aggregate model [D]. Concepts such as PerformanceObligation, ClientValueMetric, VolumeBand, AutomationComponent, and CommercialConstraint may initially be typed subobjects and later become independent graph entities.

### 3.2 Billing basis and charge cadence `[C-01]`

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
- FeeComponent dependencies (`depends_on`) form a directed acyclic graph over components and entitlements. Cycles are a validation error. `[C-02]`
- Commitment constrains one or more fee components or entitlements, with an explicit aggregation scope.
- AdjustmentMechanism modifies a named subtotal at a declared evaluation step (§4.5).
- DeliveryPlan drives cost and capacity, not contractual fee.
- Scenario provides assumptions for one or more comparable arrangements.
- Recommendation references calculation results and assumptions and never replaces them.
- EvidenceClaim references zero or more external sources and must indicate when it is inference or proposed design rather than externally observed fact.

### 3.4 Domain packs `[C-21]`

A domain pack is a versioned bundle of vocabulary, rules, and data for one sector. The core runs without any pack; packs make it fluent in a domain.

| Pack contents | ALSP pack (v1) | Consulting pack (M5) `[C-30]` |
|---|---|---|
| Service categories | CONTRACTS, EDISCOVERY, DOCUMENT_REVIEW, LEGAL_OPERATIONS, REGULATORY_CHANGE, IMPLEMENTATION, FLEXIBLE_RESOURCING | STRATEGY, OPERATIONS_IMPROVEMENT, TRANSFORMATION, IMPLEMENTATION, ADVISORY_RETAINER, INTERIM_MANAGEMENT |
| Unit templates (with counting and acceptance rule prompts) | accepted_contract_review, reviewed_document, custodian, matter, subpoena_response | consultant_day, accepted_deliverable, workstream_month |
| Provider types | REGULATED_LAW_FIRM, LICENSED_BODY, NONLAW_ALSP, FLEXIBLE_TALENT, LEGAL_TECH_VENDOR, MANAGED_SERVICES_PROVIDER [R] | LARGE_ADVISORY_FIRM, BOUTIQUE, INDEPENDENT_PRACTITIONER, TECHNOLOGY_INTEGRATOR |
| Constraint rules | Warning and approval-requirement rules, each citing evidence (for example: outcome or contingent fee with a regulated-work service; fee sharing with a non-law-firm provider type) [R] | Rules for attestation-related independence restrictions on contingent fees, and outcome fees without an agreed baseline |
| Catalogs | Legal-sector prevalence, evidence, and caveat overlays on the base catalogs (§3.6) [R] | Consulting overlays on the base catalogs, plus staffing-mix and realization concepts |
| Reasoning rules | RULE-011, RULE-012, RULE-016 (personal data, contingent legal fees, future-effective regulation) and the legally conditional compatibility combination [R] | Independence and baseline rules above |
| Engagement templates | Prefilled skeletons for common arrangements (fixed managed service, base plus overage, dedicated team, fixed project) | Role-based time and materials, capped time and materials, phased fixed fee, retainer with hours drawdown, fixed fee plus success fee |
| Evidence | Claims and sources, `verified = false` until checked (§7.2) | Same rule |

**Consulting pack prerequisites in the core.** The consulting pack depends on two core capabilities that v1 does not include:

- **Realization.** The delivery plan gains a `standard_rate_card` and a `worked_hours_source`, so the engine can value hours worked at standard rates under any billing method and report realization (contractual fee / standard value [R, FM-028]), write-down, and effective billing rate. Built.
- **Outcome pricing.** `OUTCOME_ADJUSTMENT` (§4.1) is promoted from post-v1, with its baseline, attribution, cap, and approval requirements, so the success-fee template can be computed. Built.

Both prerequisites are built; the consulting pack ships all five templates.

Rules:

- A pack MAY extend open vocabularies: service categories, provider types, unit templates, cost categories (each mapped to a core cost category), and constraint rules.
- A pack MUST NOT change billing bases, calculation methods, evaluation order, accumulation semantics, or metric definitions. Those belong to the core.
- Domain packs declare `extends: base` (§3.6). They may overlay a base concept with domain-specific prevalence, evidence, and caveats, but may not redefine its label or definition. `[C-31]`
- An engagement declares `packs: [{id, version}]`. Pack ids and versions are part of the input fingerprint. Values from an undeclared pack fail validation.
- Constraint rules emit warnings and approval requirements only. A pack never asserts that a structure is permitted.
- The core test suite MUST pass with no packs loaded (T-027).

### 3.5 Pack concept files `[C-28]`

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

### 3.6 Base knowledge pack `[C-31]`

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
| Compatibility assessments | 17 | `base/compatibility` rules (COMPAT-001 to 016); the legally conditional one (COMPAT-017) in the ALSP pack | `check_commercial_constraints` emits COMPAT warnings with the assessment class | Rules resource |
| Financial metrics (FM-*) | 35 | `base/metrics` with formula, unit, limitation, and `computed_by` (engine metric id or null) | Engine metrics link to their definitions | Glossary resource |
| Commercial health indicators (CHI-*) | 12 | `base/metrics` | Scenario-mode subset computed (§5.6); the rest marked `requires: actuals` | Glossary resource |
| Cost-allocation guidance | 11 | `base/cost_categories` with preferred treatment and common distortion | `reference` cost policy (§5.2) | Resource |
| AI service-cost and AI fee decompositions | 12 and 6 components | `base/cost_categories` and `base/fee_components` | Cost categories | `lookup_concept` |
| Structures for automation-reduced effort | 5 | Base templates; the shared-savings one needs outcome pricing (M5) | Templates | `get_template` |
| Model-selection framework | 12 steps | `base/selection_framework` | None | `design_arrangement` prompt |
| Decision matrix | 11 rows | `base/selection_heuristics` (SEL-*), class C_INFERENCE | None; never used to rank | `design_arrangement` prompt |
| Adjacent-industry mechanisms | 11 | `base/mechanisms` (MECH-*) with transferability class | None | `lookup_concept` |
| Negotiation exchanges | 10 | `base/negotiation_exchanges` (NEG-*) | None | `negotiation_options` prompt |
| Three defensible offers | 3 | Base templates | Templates | `compare_structures` prompt |
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

### 4.1 Fee component contract `[C-02, C-03]`

Each fee component MUST declare: `id`, `service_id`, `calculation_method`, `billing_basis`, `charge_cadence`, `currency`, `quantity_source` (or null for fixed methods), `unit` (or null for fixed methods), `effective_period`, `depends_on`, and the inputs its method requires (below). Missing required inputs yield validation errors.

`calculation_method` is authoritative for arithmetic. `billing_basis` is a classification validated against the method.

| Method | Formula (per period segment *t*) | Required inputs | Allowed bases | v1 |
|---|---|---|---|---|
| `FIXED_RECURRING` | fee_t = fixed_amount_t, prorated per §4.6 | fixed_amount, cadence | FIXED, CAPACITY | Yes |
| `TIME` | fee_t = Σ_role hours_role,t × rate_role,t | rate_schedule per role; eligibility rule | TIME | Yes |
| `DEDICATED_RESOURCE` | fee_t = Σ_role committed_FTE_role,t × rate_role,t | FTE commitment, rate per FTE-period, partial-period rule | RESOURCE | Yes |
| `UNIT_OUTPUT` | fee_t = rate_schedule(accepted_units_t) | rate_schedule, unit with counting and acceptance rules | OUTPUT, USAGE | Yes |
| `WEIGHTED_UNIT_OUTPUT` | fee_t = rate_schedule(Σ_band raw_units_band,t × weight_band) | rate_schedule in weighted units, ComplexityWeightTable | OUTPUT | Yes |
| `ALLOWANCE_OVERAGE` | fee_t = rate_schedule(excess_quantity_t), where excess comes from the referenced entitlement ledger (§4.4) | entitlement_id, rate_schedule | OUTPUT, USAGE | Yes |
| `FIXED_PROJECT` | fee_t = payment_schedule_t, Σ_t payment_schedule_t = project_fee | project_fee, payment schedule (dates or events) | FIXED | Yes |
| `COST_PLUS` | fee_t = eligible_cost_t × (1 + markup) | cost eligibility policy, markup | COST | Post-v1 |
| `OUTCOME_ADJUSTMENT` | fee_t = incentive(outcome over the accumulation period), charged at period end; the base is a separate component | outcome terms: form (SHARE, SUCCESS, PERCENT_OF_OUTCOME), metric, baseline or target, attribution, cap, approval | OUTCOME | Yes (consulting prerequisite) |

`ALLOWANCE_OVERAGE` components MUST list their entitlement in `depends_on`. The entitlement's `granted_by` names the component that grants it (typically a `FIXED_RECURRING` base).

### 4.2 Rate tiers `[C-04]`

`RateSchedule.tier_method` MUST be one of:

- `MARGINAL`: each tier prices only units within that tier.
- `ALL_UNITS`: the tier reached sets the rate for all eligible units.
- `GRADUATED_BLOCK`: fixed price per defined block (post-v1).

A single-tier schedule is valid under either v1 method and they are equivalent.

Tier rules:

- Tiers are half-open intervals `[from, to)`. The first tier starts at 0. The last tier has `to = null`. Tiers are contiguous and non-overlapping.
- `tier_scope` declares which quantity is tiered: `ALL_ELIGIBLE` or `EXCESS_ONLY` (units beyond an entitlement).
- `accumulation_period` declares when the tier counter resets (§4.3). A tier counter may span multiple monthly segments.
- Tier calculations MUST be tested at `threshold - 1`, `threshold`, and `threshold + 1`.

**ALL_UNITS cliff detection [D].** For each threshold *t* where the rate falls from *r_prev* to *r_t*, total fee is higher for every quantity *q* in the open interval `(t × r_t / r_prev, t)` than at *t*. Example: $10 below 1,000 and $9 from 1,000 gives 999 units = $9,990 and 1,000 units = $9,000; quantities 901 to 999 all cost more than 1,000. Validation MUST emit `W-TIER-CLIFF` with the band for each such threshold. The cliff is a property of the contract, not an error; the warning lets reviewers see the incentive it creates.

The same tier machinery applies to tiered **cost** schedules (§5.2).

### 4.3 Accumulation periods `[C-05]`

The calculation grain is the calendar month (§5.1). Many contract terms operate over a longer period. Every allowance, minimum commitment, tier counter, tiered cost, and capacity limit MUST declare an `accumulation_period`: `MONTH`, `QUARTER`, `YEAR`, `CONTRACT_YEAR` (anniversary-based), or `TERM`.

Within an accumulation period the engine keeps a running accumulator. Each such term MUST also declare its recognition rule:

| Rule | Meaning |
|---|---|
| `CUMULATIVE` | The effect is recognized in the month the accumulator crosses the threshold. Example: an annual allowance of 12,000 units is consumed month by month; overage fees begin in the month cumulative consumption passes 12,000. |
| `PERIOD_END` | The effect is computed and recognized in the final month of the accumulation period (true-up). |
| `PER_SEGMENT` | Only valid when `accumulation_period = MONTH`; each month stands alone. |

There is no default recognition rule (§11, R-11); engagement templates prefill `CUMULATIVE` visibly. For the annual totals the casebook reports, `CUMULATIVE` and `PERIOD_END` produce identical annual results; they differ only in which months carry the amounts (T-023).

### 4.4 Commitments and entitlement ledger

A minimum-spend commitment is not equivalent to an included-unit allowance. The engine SHALL model separately:

- **Minimum commitment:** `minimum_amount`, `aggregation_scope` (`COMPONENT`, `SERVICE`, `ENGAGEMENT`), `accumulation_period`, `tested_against` (`GROSS`, `NET_OF_DISCOUNTS`, `NET_OF_CREDITS`), and `shortfall_rule` (`PERIOD_END_TRUE_UP`, `PER_SEGMENT`). A minimum is applied exactly once at its declared scope (T-007).
- **Entitlement:** `included_quantity`, qualifying unit, `granted_by`, `accumulation_period`, `overage_recognition`.
- **Ledger state:** consumed, remaining, rolled-over, and expired quantities.
- **Rollover:** policy (`NONE`, `NEXT_PERIOD`, `TERM`), carryover ceiling, expiry, and whether rolled quantity is consumed before or after new grants (`FIFO` required in v1).
- **Credit application order** and an explicit prohibition on double counting.

Each ledger entry MUST include: period, unit, entry type (`GRANT`, `CONSUME`, `ROLLOVER_OUT`, `ROLLOVER_IN`, `EXPIRE`, `ADJUST`), quantity, source grant, accumulation period id, expiry, and contract version. Invariant: every granted unit is consumed, rolled, or expired exactly once (T-006).

[O] Treatment of unused prepaid entitlements for financial-statement accounting is excluded from v1.

### 4.5 Evaluation order `[C-06]`

An arrangement MUST declare an adjustment order or adopt the default below. Every adjustment mechanism on the arrangement must appear at exactly one step; validation rejects unplaced or duplicated mechanisms.

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

Every step emits line items with: step, component or mechanism id, inputs, formula id, unrounded amount, rounded amount. `explain_fee` (§8.3) reads these line items.

### 4.6 Amendments and proration `[C-07]`

An amendment MUST specify affected terms, effective date, precedence, and whether retroactive recalculation is authorized. Re-running a historical scenario SHALL preserve the original contract version unless an explicit amended-run flag is provided (T-005). Results MUST store an input fingerprint (§8.4).

Effective dates may fall on any day. When any version, component, or commitment boundary falls inside a month, the month is split into day segments and each segment is evaluated against its authoritative version. The arrangement MUST then declare `proration_policy`:

| Policy | Fixed amounts | Metered quantities |
|---|---|---|
| `CALENDAR_DAYS` | amount × segment_days / days_in_month | Supplied per segment; if only a monthly quantity is supplied, it is split by days and the split quantity is tagged `ESTIMATED` |
| `FULL_MONTH_FROM_NEXT` | New terms apply from the first day of the following month | Same |
| `FULL_MONTH_FROM_CURRENT` | New terms apply to the whole month containing the effective date | Same |

If all boundaries fall on month starts, `proration_policy` may be omitted. Otherwise omission is a validation error (P-07, T-018).

### 4.7 Money, quantities, and rounding `[C-07]`

- Monetary amounts, rates, quantities, weights, and percentages are `Decimal`. Schema fields accept JSON strings or integers; JSON floating-point numbers are rejected (P-08).
- Count units (`kind = COUNT`) must be integer-valued and non-negative. Weighted, hour, and FTE units may be fractional.
- Internal computation is unrounded at a fixed decimal context (28 significant digits).
- `money_policy` on the engagement declares `rounding_mode` (`HALF_UP` or `HALF_EVEN`), `rounding_scale`, and `rounding_level` (`LINE_ITEM` or `PERIOD_TOTAL`). It is optional. The documented default is `HALF_UP`, the currency's ISO 4217 minor-unit scale, and `LINE_ITEM`. The effective policy is echoed in every result and included in the fingerprint (P-07; §11, R-13).
- Period totals are the sum of their rounded line items. Annual and term totals are the sum of period totals, never independently recomputed (T-015).
- **Exact allocation.** When a total declared over a longer period (an annual fee, an annual cost, an annual demand forecast) is spread across months, the allocation MUST preserve the declared total exactly. Each month receives the truncated share at rounding scale (or unit scale for counts); the residual is distributed one minor unit at a time to the earliest months. Example: $880,000/year over 12 months gives 4 months of $73,333.34 and 8 months of $73,333.33. Dividing a rate and rounding each month independently is prohibited.
- Ratios (margins, utilization, markups) are returned unrounded. Rounding for display is a presentation concern.

## 5. Economics engine

### 5.1 Time model `[C-08]`

The calculation grain SHALL be calendar month [D], split into day segments where §4.6 requires, with aggregation to quarter, year, contract year, and term. Each month SHALL carry:

- `contractual_fee` (contractual consideration computed under §4; not GAAP revenue);
- estimated billed amount and cash collections, only if an optional cash schedule is provided;
- actual or forecast demand by unit and complexity band;
- theoretical, available, productive, and safe capacity; demand hours; overflow and backlog (§5.3);
- costs by category and by margin layer (§5.2);
- gross profit, contribution profit, margins, and cumulative contribution;
- client paid amount, consumed units, and effective client price per accepted normalized unit (or per used hour for resource arrangements).

`contractual_fee` is the only label for the computed charge. The system MUST NOT label it `revenue` or `recognized_revenue` absent an explicit accounting adapter. Where this specification or the research report says "revenue" in a formula, read `contractual_fee`.

### 5.2 Cost classification and margin layers `[C-09]`

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

**Reference cost policy.** `[C-22]` The core ships a cost policy with id `reference`. A calculation uses it only when the caller names it; there is no implicit policy (P-07). It follows the report's cost-allocation guidance [R]:

| Cost category | Layer in `reference` |
|---|---|
| Dedicated labor, pooled labor (activity-allocated), delivery management, QA/rework, AI inference, platform operations, third-party services | `DIRECT_DELIVERY` |
| Client-specific implementation, transition, engagement-specific overhead (account management, client governance) | `ENGAGEMENT_AVOIDABLE` |
| Reusable engineering allocation, unallocated idle pooled capacity | `PORTFOLIO_SHARED` |
| Corporate overhead | `CORPORATE_OVERHEAD` |

The Appendix C "harmonized" fixture variants use this policy.

**Reconciliation with the report.** Report FM-018 defines contribution as revenue minus variable costs minus engagement-avoidable fixed costs [R]. That matches `contribution_profit` only when every `DIRECT_DELIVERY` cost is avoidable. The engine SHALL report `unavoidable_direct_cost` separately so FM-018 can be reconstructed.

Zero-fee periods MUST return a null margin with an explanation, not divide by zero (T-008). Portfolio and overhead allocations MUST NOT be merged into contribution.

**Transition cost timing.** One-time costs carry an `incurred_schedule`. The engine reports two views: **incurred** (cost in the month it occurs; used for cumulative contribution and transition payback month) and **amortized** (spread over a declared period using exact allocation; used where a fixture or policy states annualized transition cost). The cost policy states which view feeds `contribution_profit`.

### 5.3 Capacity and operational production `[C-10]`

Capacity MUST distinguish:

```
theoretical_hours = FTE × contracted_hours_per_period
available_hours   = theoretical_hours - planned_leave - training - holidays
productive_hours  = available_hours × productive_ratio
safe_capacity     = productive_hours × safe_utilization_ceiling     (INTERNAL_POLICY origin, no default)
```

**Production standards.** Demand in units converts to demand hours through `ProductionStandard` records (hours per unit by role and complexity band). Capacity declared directly in units (as in casebook Case A) is permitted; the engine then compares unit demand with unit capacity and does not require standards.

**Capacity period.** Capacity limits carry an `accumulation_period`. Breach is tested against cumulative demand and cumulative capacity within that period, so whole-unit demand allocation does not create false breaches against fractional monthly capacity. A breach is demand strictly greater than safe capacity.

**Breach mode** is declared on the delivery plan or scenario:

| Mode | Behavior |
|---|---|
| `OVERFLOW_COST` | Units or hours above capacity incur a declared overflow cost rate instead of the normal variable rate: `cost = F + v × min(Q, K) + v_o × max(Q - K, 0)` [R] |
| `BACKLOG` | Excess demand carries to the next period; SLA risk warning emitted; backlog at horizon end reported |
| `INFEASIBLE` | Scenario fails feasibility validation |

If no breach mode is declared and a breach occurs, the scenario is infeasible (T-010).

For pooled resources, allocation policy MUST be declared and shared portfolio capacity MUST NOT be double-booked. v1 may model pooled capacity with a simplified aggregate pool, but it must expose that simplification in result warnings.

For AI-assisted services, cost drivers SHOULD include document complexity, inference volume, human validation time, exception rate, rework, and engineering amortization. [O] Correlated stochastic production drivers are a later enhancement; v1 uses explicit scenario inputs and sensitivity bands.

### 5.4 Financial outputs `[C-08]`

Required metrics: contractual fee, direct delivery cost, unavoidable direct cost, gross profit and margin, engagement-avoidable cost, contribution profit and margin, cost per accepted unit, effective client price per accepted unit (and per used hour for resource arrangements), reserved-capacity utilization, productive-hours utilization, included-allowance consumption, commitment shortfall, overage fee, cumulative contribution, transition payback month (incurred view), and break-even volume where mathematically defined.

Break-even volume is reported as the exact decimal solution and as the smallest whole unit at which contribution is non-negative. For piecewise fees or costs, the engine solves piecewise and returns null with a reason when no break-even exists in the horizon.

The engine SHALL separately label provider-side financial outcomes and client-side consumption/value indicators. It SHALL NOT infer retention probability from unused commitment.

### 5.5 Derived risk exposure `[C-11]`

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

With no tolerance declared, the engine reports the raw exposures and no label (P-07). Where a declared bearer and a derived bearer disagree, the engine emits `W-RISK-MISMATCH`. Expected labels for the casebook are in Appendix C.

### 5.6 Price floor and health indicators `[C-32]`

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

Assumptions stated over a longer period than a month MUST declare a `demand_distribution`: `FLAT` (exact allocation per §4.7) or an explicit monthly profile. `[C-05]`

v1 SHALL support low/base/high scenarios and deterministic one-way sensitivity analysis. Probability distributions and Monte Carlo are deferred until calibrated data is available.

### 6.2 Candidate comparison

Given one service and demand profile, the engine SHOULD compare at least:

- fixed recurring managed service;
- dedicated resource or capacity model;
- base fee plus output-based overage.

Each comparison MUST show fee, cost, contribution, client effective unit cost, capacity utilization, declared and derived risk exposure (§5.5), and the assumptions that differ. A model can be rejected for infeasibility without being labeled commercially inferior.

**Dominance, not ranking.** `[C-23]` By default the engine ranks nothing. For each feasible candidate it reports whether another candidate dominates it: at least as good on every comparison metric and strictly better on one. The default metrics are provider contribution (higher is better) and client effective unit price (lower is better), evaluated in every scenario of the set. The non-dominated candidates are returned as a set. A weighted or constrained objective is applied only when the caller supplies one, and the result records it verbatim.

### 6.3 Advisory guardrails

An AI layer MAY propose alternatives, explain tradeoffs, or identify missing facts. It MUST NOT:

- invent market rate cards, target margins, renewal probabilities, or legal permissions;
- treat provider case studies as independent market benchmarks;
- change financial inputs without showing the change;
- state that one structure is optimal absent a declared objective function and constraints;
- bypass legal or commercial approval requirements.

Recommendations SHALL cite calculation IDs, assumptions, constraints, and evidence claims. Human sign-off is required before adopting a commercial recommendation.

### 6.4 Structure search (Optimize) `[C-29]`

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

Evidence ships as pack data. Entries stay `verified = false` until a maintainer checks the source and records a retrieval date. Contributed evidence MUST include source URL, retrieval date, and the exact supported statement. `[C-21]`

### 7.3 Approval policy

The system SHALL emit warnings and approval requirements (it does not run an approval workflow) for:

- contribution below a user-supplied policy floor;
- undefined pricing unit or missing counting rule;
- missing commitment terms or missing accumulation/recognition rules;
- ambiguous tier logic or an ALL_UNITS cliff (`W-TIER-CLIFF`); `[C-04]`
- unbounded fixed-fee volume;
- pack-defined constraint rules (for example, the ALSP pack's contingent-fee and regulated-work rules);
- material uncapped SLA exposure;
- floor/cap conflicts (`requires_contract_interpretation`); `[C-06]`
- capacity breach under any breach mode; `[C-10]`
- declared/derived risk mismatch (`W-RISK-MISMATCH`); `[C-11]`
- missing evidence for asserted market benchmarks.

Thresholds are user-supplied policy, not embedded industry facts. A check whose threshold is not supplied reports the measured value without a pass/fail verdict.

## 8. Data contracts and implementation shape

### 8.1 Packages `[C-12, C-24]`

One distribution, `cometric`, with four subpackages. `[C-27]`

```
cometric/
  core/          # domain-neutral engine (M1-M2)
    domain/        Pydantic schemas, enums, units, contract versions, money policy
    pricing/       fee components, tiers, accumulators, ledger, evaluation order
    economics/     costs, cost policies (incl. `reference`), capacity, margins, risk exposure
    scenarios/     immutable scenario inputs, distributions, sensitivity, dominance
    search/        structure search and frontier (§6.4)
    packs_loader/  pack file validation and predicate evaluation (§3.5)
    validation/    schema, semantic, policy, compatibility checks
    fingerprint/   canonical serialization and hashing
    templates/     domain-neutral engagement templates
    schema/        JSON Schema export of every input and output model
  packs/         # data only, no Python (§3.5)
    base/        # domain-neutral knowledge from the research (M3, §3.6)
    alsp/        # ALSP pack (M3)
    consulting/  # consulting pack (M5)
  advisory/      # candidate generation and explanation contracts (M3)
  mcp/           # stateless read-only MCP server (M2)
  cli/           # validate, calculate, compare, explain
fixtures/        # casebook engagements A-G with as-published and reference cost policies
tests/           # unit, property, boundary, regression, conformance, import boundaries
```

**Import boundaries** (enforced by test, T-028): `core` imports no other subpackage; `packs` contain no Python; `advisory` imports `core` and reads packs through `core.packs_loader`; `mcp` and `cli` may import everything. The MCP server is an optional extra (`pip install cometric[mcp]`).

### 8.2 Example engagement input [D, illustrative] `[C-13]`

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

### 8.3 Interface contracts `[C-24]`

The CLI, Python API, and MCP server expose the same operations. Every operation is stateless (P-10).

**Discovery** (lets an agent with no prior knowledge build valid input):

- `describe_schema(model) -> json_schema` for any input or output model
- `list_packs() -> [{id, version, summary}]` and `describe_pack(id) -> vocabularies, rules, templates`
- `get_template(template_id, pack?) -> engagement skeleton` with required fields present and unknown values marked `"<required>"`
- `list_vocabulary(name, pack?) -> values with definitions`
- `lookup_concept(id_or_query, pack?) -> concept records` with definitions, links, evidence class, prevalence overlays, and claims `[C-31]`

**Engine:**

- `validate_engagement(input) -> validation_report`
- `calculate_periods(engagement, scenario, cost_policy, detail?) -> calculation_result`
- `compare_arrangements(engagement, candidates, scenario_set, cost_policy, objective?) -> comparison_result`
- `derive_risk_exposure(calculation_results, tolerance_policy?) -> exposure_report` `[C-11]`
- `search_structures(search_spec) -> frontier_result` `[C-29]`
- `price_floor(cost_inputs, volume, target_margin, risk_premium?) -> floor_result` (§5.6) `[C-32]`
- `explain_fee(engagement, scenario, cost_policy, period, component?) -> line_item_trace`. The engine recomputes deterministically from inputs and returns the trace with the input fingerprint, so no stored calculation is needed.
- `check_commercial_constraints(engagement, policy?) -> warnings_and_approvals` (core checks plus rules from declared packs)

**Advisory:**

- `list_applicable_evidence(claim_or_concept, pack) -> provenance_records`

**MCP server requirements:**

- Read-only. No tool writes files, calls a network service, or calls an LLM.
- **Transports** `[C-31]`: stdio from M2. Streamable HTTP from M4, so web-based clients and hosted connectors can reach Cometric. The HTTP transport MUST be stateless: no session ids, no server-side state, `POST /mcp` only, and `GET /mcp` answered with `405 Method Not Allowed` so clients do not hold idle event streams open. Authentication is the deployer's concern; the server accepts an optional bearer-token check and nothing more.
- Inputs are passed inline, or as file paths when the server runs over stdio with an allowed root directory. Paths outside that root are rejected. The HTTP transport accepts inline inputs only.
- Errors are structured: `{code, message, path}` where `path` is a JSON Pointer into the input, so an agent can repair its input.
- `detail` controls result size: `summary` (term and annual totals, metrics, warnings), `periods` (adds monthly rows), `line_items` (adds the full trace).
- Every result carries `engine_version`, `schema_version`, pack versions, the effective money policy, and the input fingerprint.

**MCP resources** `[C-31]` (read without spending tool calls):

| URI pattern | Content |
|---|---|
| `cometric://schema/{model}` | JSON Schema for any input or output model |
| `cometric://glossary` | Core terms (§5.1, §5.2, §4.3) with definitions |
| `cometric://packs/{pack}/concepts/{scheme}` | A concept scheme (§3.5, §3.6) |
| `cometric://packs/{pack}/rules` | Constraint and compatibility rules |
| `cometric://packs/{pack}/templates/{id}` | Engagement templates |
| `cometric://examples/{case}` | Casebook fixtures A to G with expected results (Appendix C) |
| `cometric://packs/{pack}/coverage` | Evidence strength and readiness by knowledge area, so an agent knows how much to trust each area |

**MCP prompts** `[C-31]` (guided workflows that any client can offer its user):

| Prompt | Workflow |
|---|---|
| `model_from_terms` | Turn a term sheet, SOW, or contract summary into a validated engagement: pick a template, fill fields, validate, repair using error pointers, then confirm assumptions and their origins with the user |
| `design_arrangement` | The twelve-step selection sequence [R] (§3.6): characterize the service, identify drivers and uncertainty, capture client preferences, shortlist bases and levers using the selection heuristics, screen constraints, then hand off to `compare_structures` |
| `compare_structures` | Build three candidates (fixed managed service, dedicated capacity, base plus overage, or caller-chosen), run them across low/base/high, present dominance and derived risk |
| `search_structures` | Draft a `search_spec` with the user, show it before running (§6.4), present the frontier and binding constraints |
| `negotiation_options` | Given a proposed concession, list matching exchanges from the negotiation-exchange scheme (§3.6) and quantify each with `compare_arrangements` |
| `explain_result` | Walk a user through a calculation with `explain_fee`, separating contract facts, assumptions, and calculated results |

Prompts instruct the agent; they never contain numbers, benchmarks, or recommendations of their own.

### 8.4 Canonical serialization and fingerprint `[C-14]`

`input_fingerprint` = SHA-256 of the canonical JSON of: `schema_version`, `engine_version`, engagement, arrangement versions, scenario, cost policy, money policy, and tolerance policy if supplied.

Canonical JSON:

- object keys sorted; no insignificant whitespace; UTF-8;
- decimals serialized as strings in plain notation with trailing zeros removed (`"100000"` and `"100000.00"` serialize identically; in Python, `format(d.normalize(), "f")`);
- dates as ISO 8601 `YYYY-MM-DD`;
- arrays keep declared order, except arrays whose order is semantically irrelevant (components, entitlements, rate schedules), which are sorted by `id`;
- run ids, timestamps, and host information excluded.

The engine is deterministic: no floating point, no wall-clock reads, no randomness, no reliance on hash-map iteration order.

### 8.5 Persistence `[C-24]`

v1 has no database. Engagements, scenarios, cost policies, and tolerance policies are versioned JSON or YAML files in the user's own repository. Because results are reproducible from inputs plus fingerprint, storing results is optional; a user who wants an audit record stores the result JSON next to its inputs.

## 9. Verification and acceptance tests `[C-15]`

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
| T-016 | Casebook | Fixtures A to F reproduce the report's published results under Appendix C rules |
| T-017 | ALL_UNITS cliff | $10 below 1,000 / $9 from 1,000 emits `W-TIER-CLIFF` with band (900, 1000) |
| T-018 | Proration | A version effective 2027-03-16 under `CALENDAR_DAYS` charges 15/31 and 16/31 of the two fixed amounts; omitting `proration_policy` fails validation |
| T-019 | Fingerprint normalization | `"100000"` and `"100000.00"` inputs yield the same fingerprint; reordering components yields the same fingerprint |
| T-020 | Dependency graph | A cycle in `depends_on` fails validation; an `ALLOWANCE_OVERAGE` component without its entitlement in `depends_on` fails validation |
| T-021 | Margin layer partition | A cost policy mapping one category to two layers, or leaving a category unmapped, fails validation |
| T-022 | Derived risk exposure | Casebook labels match Appendix C table C.3 |
| T-023 | Recognition timing | `CUMULATIVE` and `PERIOD_END` produce identical annual totals and different monthly distributions for Case A high demand |
| T-024 | Floor/cap conflict | Minimum greater than cap at the same scope returns `requires_contract_interpretation` |
| T-025 | Exact allocation | $880,000/year spread monthly sums to exactly $880,000.00 |
| T-026 | Example validity | The §8.2 example validates and produces T-001's result |
| T-027 | Core conformance | T-001 to T-026 (except T-011) pass with no packs installed `[C-21]` |
| T-028 | Import boundaries | `core` imports no other subpackage; `packs/` contains no Python files `[C-24, C-28]` |
| T-029 | Template round trip | Every shipped template, once `"<required>"` fields are filled, validates; unfilled, it fails with a JSON Pointer per missing field `[C-24]` |
| T-030 | Dominance | With three candidates where one is worse on both default metrics in every scenario, it is reported dominated; no candidate is ranked without a supplied objective `[C-23]` |
| T-031 | Structure search | Case A with base fee {900k, 1.2M, 1.5M} × overage rate {100, 120, 140} across low/base/high: same frontier on repeated runs; a grid above `max_candidates` is rejected with its size; every invalid candidate is counted by reason `[C-29]` |
| T-032 | Pack validation | A concept file with a dangling reference, a reused id, an unknown core vocabulary value, or a Python file in the pack directory fails validation `[C-28]` |
| T-033 | Research capture | Every report identifier (BB, PM, CL, FM, CHI, EC, REL, RULE, E) and every row of the compatibility, decision-matrix, mechanism, negotiation, and dimension tables appears in the base or ALSP pack, or in `packs/base/excluded.yaml` with a reason `[C-31]` |
| T-034 | Price floor | Case B, 12,000 contracts, 20% target, no premium → $1,125,000 and $93.75 per contract; `m_t ≥ 1` fails validation `[C-32]` |
| T-035 | MCP surface | Every listed resource URI resolves for the installed packs; every prompt renders; HTTP transport returns 405 on `GET /mcp` and keeps no state between requests `[C-31]` |

**Property tests** SHOULD verify: non-negative accepted units; non-overlapping effective dates; contiguous tiers; under `MARGINAL` tier schedules with non-negative rates, the pre-credit fee never decreases when eligible consumption increases, holding other terms fixed. Under `ALL_UNITS` schedules the property holds outside every band reported by `W-TIER-CLIFF` and is not asserted inside them. `[C-04]`

## 10. Delivery milestones `[C-16, C-25]`

| Milestone | Deliverable | Exit criterion |
|---|---|---|
| M0: Schema freeze | Schema v0.3, glossary, JSON Schema export; disposable engine spike over fixtures A to C | Spike reproduces A to C; every semantic issue it surfaces is resolved or logged as a schema change |
| M1: Core engine | `core` subpackage, validators, monthly calculations, fingerprinting, CLI, tests | T-001 to T-010, T-012 to T-028 pass; fixtures A to G reproduce Appendix C under both cost policies |
| M2: Compare, optimize, MCP | Dominance comparison, structure search, sensitivities, capacity warnings, derived risk exposure; stateless MCP server with discovery tools; domain-neutral templates | T-029 to T-031 pass; an agent given only the MCP server builds a valid engagement from a template, compares three arrangements, and runs a structure search |
| M3: Knowledge packs and advisory | Pack loader and predicate language; base pack (§3.6) and ALSP pack; evidence data; MCP resources and prompts; price floor and scenario-mode health indicators; advisory explanations | T-011, T-032 to T-034 pass; Appendix D entries verified or removed; explanations trace to formulas and evidence; no LLM arithmetic |
| M4: Public release | PyPI release of `cometric`, documentation, worked examples; stateless HTTP transport; one real engagement reconciled privately by a practitioner, with discrepancies (not client data) published | T-035 passes; reconciliation discrepancies fixed or documented as known limitations |
| M5: Consulting pack `[C-30]` | Core realization and outcome pricing (§3.4 prerequisites); consulting concept files, rules, templates | A real consulting engagement reconciles privately, as in M4; the success-fee template computes with baseline, attribution, and cap |

The M0 spike exists to surface semantic questions against executable fixtures. It is explicitly disposable: M1 may discard its code.

Do not advance from M0 to M1 before billing-basis, entitlement, and recognition semantics are frozen. Do not claim real-world accuracy from the illustrative casebook alone.

## 11. Resolved decisions and remaining questions `[C-26]`

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

### 11.2 Remaining open questions

- **Q-1 Resolved: name.** Cometric. Distribution, import package, CLI, and MCP server are all `cometric` `[C-27]`. A trademark search is pending before public launch; the plural "Cometrics" is in use by unrelated companies.
- **Q-2 Resolved: license.** Apache-2.0, for patent-grant coverage and consistency with comparable infrastructure projects.
- **Q-3 [O] Research report in the public repository.** Recommendation: do not publish the report as is. Its citations are dead tokens, its date is wrong, and it names specific providers throughout. Publish this specification; ship evidence only as verified pack data (§7.2).
- **Q-4 Resolved: second domain pack.** Consulting (§3.4, M5) `[C-30]`. It exercises methods the ALSP pack barely uses (role-based time, fixed projects, retainers, success fees) and has a first user available for reconciliation.
- **Q-5 [O] Evidence that names firms.** Pack evidence necessarily cites the organizations whose public material supports a claim. Decide whether published packs may name them in source records, or whether sources are cited by document title and URL only.

## 12. Decisions proposed for v0.2 review

- Name the project Cometric, framed as Model / Simulate / Optimize. [D]
- Build a domain-neutral engine with ALSP as the first domain pack and consulting as the second (§3.4). [D]
- Define packs as data-only concept files with a declarative rule language (§3.5). [D]
- Decompose the research into a domain-neutral base pack plus domain overlays, with capture verified by test (§3.6, T-033). [D]
- Ship MCP resources and guided prompts, and add a stateless HTTP transport at M4 (§8.3). [D]
- Implement "Optimize" as deterministic structure search returning a trade-off frontier (§6.4). [D]
- Adopt a compositional PricingArrangement instead of a flat enumeration of 34 pricing models. [R/D]
- Adopt eight billing bases plus an orthogonal charge cadence (§3.2). [D]
- Evaluate allowances, minimums, tiers, and capacity against declared accumulation periods (§4.3). [D]
- Adopt the corrected evaluation order (§4.5). [D]
- Define contribution on a margin-layer partition governed by an explicit cost policy, with a shipped `reference` policy (§5.2). [D]
- Use Pydantic domain models and pure Python decimal financial functions before adding a graph database. [D]
- Implement monthly time-indexed simulation before Monte Carlo optimization. [D]
- Keep client value indicators distinct from provider financial measures, and derive risk exposure from both (§5.5). [R/D]
- Report dominance rather than a ranking unless an objective is supplied (§6.2). [D]
- Require contract facts, assumptions, evidence, and recommendations to be explicitly labeled. [R/D]
- Use the research casebook as regression fixtures, not market benchmarks. [R/D]
- Ship a stateless, read-only MCP server with schema and template discovery at M2, after deterministic validation (§8.3). [D]
- Compute price floors and scenario-mode health indicators; defer indicators that need actuals (§5.6). [D]

---

## Appendix A. Research-to-implementation traceability `[C-17]`

This table summarizes by implementation location. §3.6 is the authoritative item-by-item map, and T-033 verifies it.

| Research domain | Initial implementation location | Status |
|---|---|---|
| Ten billing bases and normalized pricing taxonomy | `core.domain`, `core.pricing` | Mapped to eight bases + cadence (§3.2); frozen at M0 |
| 61 commercial levers (the report text states 58; its catalog lists 61: 12 CL-R, 12 CL-V, 13 CL-D, 15 CL-P, 9 CL-VL) | Mechanics in `core.pricing`; catalog in `packs.base`, legal-sector overlays in `packs.alsp` | Mechanics for the v1 subset at M1; catalog at M3; near-duplicates (CL-R01/CL-R02/CL-V06; CL-R05/CL-VL03/CL-VL04) consolidated in the catalog |
| 35 financial metrics | `core.economics` | Priority subset M1; accounting metrics deferred |
| 34 candidate entity classes | `core.domain` | Collapsed to core aggregates for v1 |
| 20 proposed semantic relationships | `core.domain` | Reconciled against typed schema at M0 |
| Six illustrative cases | `fixtures`, `tests` | M1 regression baseline per Appendix C, plus new Case G |
| Evidence register E001 to E040 | `packs.base` and `packs.alsp` evidence | Ships `verified = false`; verification at M3 (Appendix D) |
| Regulatory constraints | `packs.alsp` constraint rules | Warning/approval requirement only; no automated legal determination |
| Provider-type limitations matrix | `packs.alsp` vocabulary and rules | M3 |
| AI cost and automation benefit | `core.economics`, `core.scenarios` | Cost categories M1; sophisticated inference post-v1 |
| Adjacent-sector mechanisms | `packs.base` mechanisms; inputs to the consulting pack (M5) | Design candidates, not universal practice |

## Appendix B. Explicit non-claims

This specification does not assert that any particular pricing structure is universally optimal, that a fixed margin target is industry standard, that unused commitments predict churn, that an ALSP can legally use every modeled fee type, or that the illustrative scenario prices reflect actual market rates. Such claims require evidence, internal policy, or legal review beyond the supplied report.

## Appendix C. Casebook fixture specification `[C-17]`

### C.1 Common rules

- All fixtures: USD, horizon 2027-01-01 to 2027-12-31, `money_policy` HALF_UP / 2 / LINE_ITEM, all assumptions `origin = ILLUSTRATIVE`.
- Annual fees, annual costs, and annual demand are spread monthly using exact allocation (§4.7) with `demand_distribution = FLAT`. Raw units per complexity band are allocated per band.
- Annual allowances, tiers, and capacities use `accumulation_period = YEAR` and `CUMULATIVE` recognition.
- T-016 compares annual totals. Currency amounts must match the report exactly. Margins must match the report's one-decimal presentation to within 0.05 percentage points.
- Each fixture runs under two cost policies: **as-published**, reproducing the report's classification, and **harmonized**, which is the core `reference` policy (§5.2). Both are regression baselines (§11, R-12). Where the two give the same result, only one set of expected values is listed.
- Fixtures declare no packs, so they also serve the core conformance test (T-027).
- Values marked *(v0.2)* below are assumptions this specification adds because the report does not state them. They do not change annual results.

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

## Appendix D. Evidence verification priorities `[C-17]`

All 40 register entries require verification before `verified = true`. Check these first, because a specific claim depends on each and the record shows a visible anomaly:

| Entry | Anomaly | Claim affected |
|---|---|---|
| E037 | One provider's announcement hosted on a different provider's domain | Emerging AI pricing contrast (PM-030) |
| E014 | A practice-area page cited as evidence of the provider's own per-document fee structure; the page may concern the practice area's subject matter instead | Per-document and per-custodian pricing (PM-012) |
| E015 | 2016 source supporting a current fixed monthly subscription claim | PM-007, PM-010 |
| E018 | "2015-era" handbook at a 2019 URL path | Collars, holdbacks, success fees (PM-033, CL-V08) |
| E006, E008 | Specific dollar figures quoted ($150 to $350/hour; $250/user/month) | Must carry retrieval date and remain provider-specific |
