# Cometric tool specification: `propose_structures`

| | |
|---|---|
| Version | 0.2 (supersedes the 0.1 draft) |
| Date | 2026-11-05 |
| Authors | Fahad Baig, with Claude |
| Status | Draft for review. Part A is the specification; Part B is the implementation plan. Section A11 lists the decisions to confirm. |
| Target release | `cometric` 0.6.0, `base` pack 0.2.0 |

## What changed from 0.1

0.1 assumed pack data that does not exist. Checking it against the installed packs found:

- Pricing models (34) and levers (70) are defined in `base`. The "32 models, 15 levers" in 0.1 are ALSP overlays on them. ALSP itself defines 21 concepts and 16 rules (10 are constraints, one is a compatibility rule).
- No lever says how it becomes contract terms. Levers carry prose (`category`, `purpose`, `economic_effect`) and no link to a commitment, adjustment, or entitlement, so a skeleton could not be built. **A11 adds these mappings ("realizations") as pack data.**
- Volume risk is prose (`provider_client_economics`). **A11 adds structured risk labels, defined so the engine can check them.**
- Compatibility rules test an engagement document, not a list of concepts, and the conflict-type rules (COMPAT-007, 008, 014, 015, 016) are not evaluable. With today's data nothing would ever be excluded. **v0.2 adds composition rules.**
- The packs already hold part of the priority mapping: `selection_heuristics` (SEL-001 to SEL-011, with favored and cautioned model ids) and `offers` (OFFER-A to C, the contract-review risk spread). v0.2 uses them instead of a parallel mapping.
- Placeholders already exist: templates use `"<required>"`, and validation reports each as `REQUIRED_FIELD` with its pointer. v0.2 extends that convention instead of adding an object form that would fail strict decimal fields.
- Evidence status in the packs is evidence class (A to D), prevalence, and per-source verification. There is no "MODERATE".
- `PERIOD` and `OUTCOME` are not core unit kinds; `compare_arrangements` has no baseline.
- Core principle P-03 says the engine never reads selection heuristics or compatibility classes "to compute, rank, or choose". This tool chooses, so v0.2 amends P-03 explicitly (A2).

# Part A. Specification

## A1. Purpose

`propose_structures` takes a short deal profile and returns a few candidate commercial structures, each a base pricing model plus levers, with how it allocates risk, which of the client's priorities it serves and where it falls short, the pack's evidence and its strength, and on request a skeleton engagement that `compare_arrangements` and `search_structures` accept once rates and costs are filled in.

It replaces the step an LLM does today by piecing together `list_templates`, `describe_pack`, `lookup_concept`, and `list_applicable_evidence`, which gives inconsistent results and leaves the most consequential reasoning unrecorded.

Primary user: an LLM working for a non-technical practice partner. Design choices favor plain-language explanation and make it hard to present an assumption as a finding.

## A2. Principles

1. **List, don't rank.** Candidates are grouped by who absorbs a volume shortfall, in a fixed order. Nothing in the output ranks them. Choosing is for `compare_arrangements` and the partner.
2. **The partner's inputs choose; the research explains.** Selection uses only the profile (priorities, constraints, partner lever preferences), structural applicability, and composition rules. Selection heuristics, offers, and evidence annotate candidates but never change which are selected.
3. **Mappings are pack data.** Realizations, risk labels, priority definitions, signal predicates, and composition rules are YAML in packs, validated by `validate-pack`, versioned with the pack.
4. **No prices.** No monetary amount or percentage is generated. Skeleton values the partner must supply are labelled placeholders.
5. **Deterministic and stateless.** The same profile, options, pack versions, and engine version give the same output and fingerprint. Expanding a candidate is a second call with the same profile.
6. **Checkable labels.** Risk labels are pack assertions (evidence class `D_PROPOSED`). Once a skeleton is filled, `derive_risk_exposure` computes who actually absorbs the shortfall, and a mismatch is reported.
7. **Compact by default.** Summary output; skeletons only for candidates named in `options.expand`.

**P-03 amendment** (spec 3.6 rules): "The engine computes only from core vocabulary, methods, and caller policies. `propose_structures` may read composition rules to exclude a structure and may read selection heuristics, offers, and evidence to annotate one; no knowledge record is used to compute a figure or to rank."

## A3. Risk vocabulary

All bearer values reuse the core `RiskBearer` vocabulary, so labels can be compared with `derive_risk_exposure`.

| Axis | Question | Values |
|---|---|---|
| `volume_shortfall` | Volume comes in below expected. Who absorbs it? | `CLIENT` (pays for capacity or a minimum it did not use; its effective unit price rises), `PROVIDER` (revenue falls while committed delivery cost stays; contribution falls), `SHARED`, `NONE_ADVERSE` (cost flexes with volume and the unit price is unchanged) |
| `volume_excess` | Volume comes in above expected. Who absorbs it? | `PROVIDER` (more work for a fixed or capped fee), `CLIENT` (pays a higher rate above a bound), `SHARED`, `NONE_ADVERSE` (paid per unit at the agreed rate) |
| `spend_variability` | How much does the client's spend move with volume? | `FIXED`, `BOUNDED` (capped or collared), `VARIABLE` |
| `mix` (only when the profile has complexity tiers) | Work shifts toward complex items. Who absorbs it? | `CLIENT` (priced per tier or by weight), `PROVIDER` (one price or a fixed fee) |
| `early_exit` (only when the client can terminate early) | The client leaves mid-term. Who absorbs stranded cost? | `CLIENT` (termination fee or remainder due), `SHARED` (minimum prorated), `PROVIDER` (no recovery) |

`volume_shortfall` labels assume the provider carries material fixed delivery cost. When `cost_profile.shape` is `MOSTLY_VARIABLE`, models declaring `variable_cost_shortfall` use that label instead (usually `NONE_ADVERSE`).

## A4. Inputs

```json
{
  "packs": ["alsp"],
  "deal_profile": {
    "service_category": "CONTRACTS",
    "unit_of_work": {
      "kind": "COUNT",
      "description": "Contract review requests",
      "tiers": ["high", "medium", "low"]
    },
    "volume": {"certainty": "RANGE", "expected": "1200", "low": "400", "high": "1500", "period": "YEAR"},
    "cost_profile": {"shape": "MIXED", "fixed_team": true, "setup_investment": false},
    "client_priorities": ["budget_certainty", "pay_for_use"],
    "provider_constraints": {"max_volume_risk": "SHARED"},
    "term": {"months": 24, "client_can_terminate_early": true, "notice_days": 90},
    "flags": {"automation_expected": false, "continuity_required": false}
  },
  "options": {"max_candidates": 4, "include_levers": [], "exclude_levers": [], "expand": []}
}
```

| Field | Required | Values and notes |
|---|---|---|
| `packs` | Yes | Installed pack ids. `base` is always included. Packs contribute vocabulary, overlays, evidence, and templates; v1 models and levers come from `base`. |
| `service_category` | Yes | From the declared packs' `service_categories`. Pack-qualify (`alsp:IMPLEMENTATION`) when the id exists in more than one declared pack. In v1 it selects overlays and evidence and is written to the skeleton; it does not filter models. |
| `unit_of_work.kind` | Yes | Core `UnitKind`: `COUNT`, `HOURS`, `FTE_MONTHS`. (`WEIGHTED` arises from tiers; `METER` is not offered in v1.) |
| `unit_of_work.tiers` | No | Complexity tiers, each a distinct unit type. Not volume bands (those are lever CL-V03). |
| `volume.certainty` | Yes | `KNOWN`, `RANGE`, `UNKNOWN`. `expected`, `low`, `high` are optional decimal strings. |
| `volume.period` | With figures | `MONTH`, `YEAR`. |
| `cost_profile.shape` | Yes | `MOSTLY_VARIABLE`, `MOSTLY_FIXED`, `MIXED`. Selects shortfall labels (A3) and the skeleton's cost components (A8). |
| `cost_profile.fixed_team`, `setup_investment` | No | Booleans; signals for SEL-003 and SEL-005 and for levers CL-R09 and CL-P14. |
| `client_priorities` | Yes | 1 to 3, ordered. Ids from the `client_priorities` scheme (A7.3): `budget_certainty`, `pay_for_use`, `cost_reduction_over_time`, `outcome_alignment`, `simplicity`. |
| `provider_constraints.max_volume_risk` | No | Largest `volume_shortfall` the provider accepts: `NONE` (CLIENT only), `SHARED` (CLIENT or SHARED), `ANY` (default). Replaces 0.1's redundant `needs_volume_protection`. |
| `term` | No | `months`, `client_can_terminate_early`, `notice_days`. Drives early-exit stubs and levers CL-P14 and CL-P12. |
| `flags` | No | `automation_expected` (SEL-010; sets descriptor `automation_benefit` so COMPAT-012 and 013 fire), `continuity_required` (SEL-011). |
| `options.max_candidates` | No | Default 4, maximum 6. |
| `options.include_levers`, `exclude_levers` | No | Lever ids. Excluded levers never appear. An included lever appears in every candidate it applies to; where it does not apply, the candidate says why. |
| `options.expand` | No | Candidate ids to return with skeletons. |

Validation follows 0.4.0 behavior: unknown fields and values are errors naming the field and the nearest valid value. `describe_schema("deal_profile")` returns the schema. `existing_engagement` (renewals) is deferred to v1.1 (A11, D5).

## A5. Selection

1. **Eligible base models.** Models with a realization whose `unit_kinds` include `unit_of_work.kind` (and `requires_tiers` satisfied). Draft v1 set in A7.1.
2. **Lever pool.** The union of levers suggested by the profile's signals (A7.3 priorities, A7.4 signals) and `include_levers`, minus `exclude_levers`.
3. **Compositions.** For each eligible model, every subset of applicable pool levers of size 0 to 3 (applicability is the lever's `applies_to`). Compositions are canonical: levers sorted by id; a composition equivalent to a named model (for example PM-011 with CL-R02 equals PM-034) is reported once, under the named model.
4. **Risk labels.** Start from the model's labels; apply each lever's `effects` (an explicit from-to map per axis) in lever-id order. No arithmetic.
5. **Exclusion.** Drop compositions that break `provider_constraints.max_volume_risk`, a composition rule (A7.5), or an evaluable pack rule whose assessment is in the exclusion set (`ECONOMICALLY_CONFLICTING`, `NOT_ECONOMICALLY_DEFENSIBLE`, `NOT_VALID_FOR_RIGOROUS_MODELING`, `STRUCTURALLY_WEAK`) when run on the composition's skeleton. Rules at WARNING severity annotate instead. `excluded` reports each rule once with the count of compositions it removed and one example.
6. **Fit.** For each profile priority, the priority's `fits` and `tension` predicates (A7.3) evaluate against the composition's labels and levers. Every candidate lists both `fits_priorities` and `tension_with_priorities`.
7. **Selection.** Group by `volume_shortfall` in the order `CLIENT`, `SHARED`, `PROVIDER`, `NONE_ADVERSE`. Within a group, prefer the composition that fits the most priorities, compared in the profile's priority order; then fewer tensions; then fewer levers; then lexical composition id. Pick round-robin across groups until `max_candidates`; a second pick in a group must use a different base model. This preference decides only what is listed. Within a group the output is ordered by composition id, not by preference.
8. **Annotation.** Attach evidence (A6.3), heuristic notes (SEL ids favoring or cautioning the base model, with their caution text), matching offers (OFFER-A to C by risk shape), WARNING-level rule results, and a similar template where one declares the same composition.
9. **Skeleton** (expanded candidates only). Assemble from realizations and the profile (A8), then run `validate_engagement`. Any error other than `REQUIRED_FIELD` on a labelled placeholder is a defect.

## A6. Output

### A6.1 Summary (default)

```json
{
  "status": "ok",
  "record_type": "StructureProposal",
  "approval_state": "PENDING_HUMAN_REVIEW",
  "fingerprint": "sha256:...",
  "order_note": "Candidates are grouped by who absorbs a volume shortfall, not ordered by preference.",
  "candidates": [
    {
      "id": "PM-011+CL-R01",
      "label": "Per-unit pricing with a minimum spend commitment",
      "composition": {"base_model": "base:PM-011", "levers": ["base:CL-R01"]},
      "risk_allocation": {"volume_shortfall": "SHARED", "volume_excess": "NONE_ADVERSE", "spend_variability": "VARIABLE", "mix": "CLIENT", "early_exit": "PROVIDER"},
      "fits_priorities": ["pay_for_use"],
      "tension_with_priorities": [{"priority": "budget_certainty", "note": "Spend moves with volume above the minimum."}],
      "tradeoffs": ["The provider is protected below the minimum; the client pays for unused volume up to it."],
      "notes": [{"source": "base:SEL-003", "kind": "caution", "text": "Pure per-unit pricing without a minimum if staffing cannot flex"}],
      "requires_inputs": ["unit rate, tier high", "unit rate, tier medium", "unit rate, tier low", "minimum spend per year", "monthly team cost", "cost per unit"],
      "evidence": [
        {"concept": "base:PM-011", "evidence_class": "A_DIRECT", "prevalence": "ESTABLISHED_COMMON", "prevalence_source": "alsp", "claims": 3, "verified_sources": 2},
        {"concept": "base:CL-R01", "evidence_class": "B_CORROBORATED", "prevalence": "UNVERIFIED", "claims": 2, "verified_sources": 1, "flag": "WEAK"}
      ],
      "rules": [],
      "similar_template": "alsp:tiered_units_annual_minimum",
      "skeleton": null
    }
  ],
  "excluded": [{"rule": "base:COMP-002", "reason": "A collar and a minimum commitment both protect against shortfall; keep one.", "compositions": 6, "example": "PM-011+CL-R01+CL-V08"}],
  "levers_not_applicable": [{"lever": "base:CL-V07", "reason": "A consumption cap needs a variable charge; PM-007 has none."}],
  "warnings": [{"code": "LABELS_ARE_PROPOSED", "message": "Risk labels are pack assertions (D_PROPOSED). Fill a skeleton and run derive_risk_exposure to check them."}],
  "next_step": {"tool": "propose_structures", "note": "Expand the candidates to compare with options.expand, fill the required inputs, then run compare_arrangements on the shared scenarios."},
  "definitions": {"risk_allocation.volume_shortfall": "Who absorbs the effect when volume is below expected."}
}
```

Ids and values in this example are illustrative until the pack data in A7 is authored.

### A6.2 Field rules

- Candidate ids are canonical composition ids (`PM-011+CL-R01`), stable across calls; with several declared packs they are pack-qualified.
- `fits_priorities` and `tension_with_priorities` use only the profile's priorities and are both always present.
- `requires_inputs` lists every placeholder label in the candidate's skeleton, so it is complete even when the skeleton is not expanded.
- **No figures:** no monetary amount or percentage appears that the profile did not supply. Evidence is reported as ids and status only (pack text such as offers contains illustrative amounts); `list_applicable_evidence` returns the statements.
- The fingerprint covers the profile, options other than `expand`, declared pack ids and versions, engine version, and schema version.

### A6.3 Evidence

For the base model and each lever: evidence class and prevalence (the declared pack's overlay when present, else `base`, with `prevalence_source`), the number of claims, and the number of verified sources. `flag: "WEAK"` when the class is C or D, prevalence is `UNVERIFIED`, or no source is verified. Values are reported as stored; never combined into a score.

### A6.4 Expanded skeletons

With `options.expand: ["PM-011+CL-R01"]`, that candidate's `skeleton` is `{"engagement": ..., "scenarios": [...]}`. Placeholders are labelled strings:

```json
{"rate": "<required: unit rate, tier high>"}
```

`<required>` (unlabelled) remains valid. Validation reports each placeholder as `REQUIRED_FIELD` with its pointer and label. `compare_arrangements` marks a candidate with placeholders invalid and lists each one; `search_structures` rejects a base engagement with placeholders, listing each.

## A7. Pack data (base 0.2.0)

All new records carry `evidence_class: D_PROPOSED` and `source_ref: cometric:design` unless they cite a claim. `validate-pack` enforces every reference and vocabulary value below.

### A7.1 Model realizations (draft, for review)

New directory `packs/base/realizations/`. Each realization names a concept, the unit kinds it fits, its risk labels, and an engagement fragment with placeholders and symbolic ids.

| Model | Realization | Unit kinds | Shortfall (fixed cost / variable cost) | Excess | Spend | Mix |
|---|---|---|---|---|---|---|
| PM-001 Hourly time and materials | `TIME` with role rates | HOURS | PROVIDER / NONE_ADVERSE | NONE_ADVERSE | VARIABLE | n/a |
| PM-020 Capped time and materials | `TIME` + `CAP` adjustment | HOURS | PROVIDER / NONE_ADVERSE | PROVIDER | BOUNDED | n/a |
| PM-004 Dedicated FTE | `DEDICATED_RESOURCE` | FTE_MONTHS, HOURS, COUNT | CLIENT | PROVIDER | FIXED | PROVIDER |
| PM-009 Capacity reservation | `FIXED_RECURRING` + `RESERVED_CAPACITY` commitment | COUNT, HOURS | CLIENT | PROVIDER | FIXED | PROVIDER |
| PM-007 Fixed-fee managed service | `FIXED_RECURRING` | COUNT, HOURS | CLIENT | PROVIDER | FIXED | PROVIDER |
| PM-011 Per unit | `UNIT_OUTPUT`, one rate per unit type | COUNT | PROVIDER / NONE_ADVERSE | NONE_ADVERSE | VARIABLE | CLIENT with tiers |
| PM-014 Tiered volume pricing | `UNIT_OUTPUT`, marginal volume tiers | COUNT | PROVIDER / NONE_ADVERSE | NONE_ADVERSE | VARIABLE | CLIENT with tiers |
| PM-015 Complexity-weighted units | `WEIGHTED_UNIT_OUTPUT` + weight table (requires tiers) | COUNT | PROVIDER / NONE_ADVERSE | NONE_ADVERSE | VARIABLE | CLIENT |
| PM-023 Hybrid fixed plus variable | `FIXED_RECURRING` + entitlement + `ALLOWANCE_OVERAGE` | COUNT, HOURS | CLIENT | NONE_ADVERSE | VARIABLE | PROVIDER below the allowance |
| PM-031 Prepaid credits | `FIXED_RECURRING` + `PREPAID_CREDIT` commitment | COUNT, HOURS | CLIENT | NONE_ADVERSE | FIXED per block | CLIENT |

Out of v1: outcome models (PM-024, 026, 027, 032; the non-evaluable rules COMPAT-007, 008, 014, 015 concern exactly these), project fees (PM-006, 016, 017, 018), cost-plus (PM-019; the engine does not implement it), and the rest.

### A7.2 Lever realizations (draft, for review)

| Lever | Realization | Applies to | Effects |
|---|---|---|---|
| CL-R01 Minimum spend | `MINIMUM_SPEND` commitment, period-end true-up | variable models | shortfall PROVIDER→SHARED, NONE_ADVERSE→SHARED |
| CL-R02 Take-or-pay | `MINIMUM_VOLUME` commitment | unit models | as CL-R01 |
| CL-R06 Rollover | entitlement rollover `NEXT_PERIOD` | models with an entitlement | shortfall CLIENT→SHARED |
| CL-R09 Setup fee | `ONE_TIME` fixed component | all | early_exit PROVIDER→SHARED |
| CL-V02 Overage (with CL-V01 allowance) | entitlement + `ALLOWANCE_OVERAGE` on a fixed base | PM-007, PM-009 | excess PROVIDER→NONE_ADVERSE; spend FIXED→VARIABLE |
| CL-V03 Tiered rate | marginal volume tiers on unit rates | PM-011 | none (price falls with volume) |
| CL-V04 Volume discount | `DISCOUNT`, threshold, excess only | variable models | none |
| CL-V05 Volume rebate | `REBATE`, threshold | variable models | none |
| CL-V07 Consumption cap | `CAP` adjustment | variable models | spend VARIABLE→BOUNDED; excess NONE_ADVERSE→PROVIDER |
| CL-V08 Collar | `COLLAR` with outside rate schedule | unit models | shortfall PROVIDER→SHARED; excess NONE_ADVERSE→SHARED |
| CL-P01 SLA service credit | `SLA_CREDIT` with trigger | all | none |
| CL-P02 Performance bonus | `BONUS` with trigger | all | none |
| CL-P12 Indexation | `INDEXATION` | all | none (suggested when term exceeds 12 months) |
| CL-P14 Termination fee | version `termination_fee` | all | early_exit PROVIDER→CLIENT |
| CL-P14 Prorated minimum (variant) | commitment `termination_rule: PRORATE` | compositions with a minimum | early_exit PROVIDER→SHARED |

Levers without a realization never appear in a candidate.

### A7.3 Client priorities (new scheme `client_priorities`)

| Priority | Fits when | Tension when | Suggests levers | Related heuristic |
|---|---|---|---|---|
| `budget_certainty` | spend is FIXED or BOUNDED | spend is VARIABLE | CL-V07 | SEL-007 |
| `pay_for_use` | shortfall is not CLIENT and spend is not FIXED | shortfall is CLIENT | CL-R06 | SEL-008 |
| `cost_reduction_over_time` | has CL-V03, CL-V04, or CL-V05 | none of them | CL-V03, CL-V04, CL-V05 | |
| `outcome_alignment` | has CL-P01 or CL-P02 | neither | CL-P01, CL-P02 | |
| `simplicity` | at most one lever | three or more levers | | |

`fits` and `tension` are predicates over `{labels, levers}` in the existing predicate language.

### A7.4 Signals

Each selection heuristic gains a `profile_signal` predicate over the deal profile, for example SEL-003 when `cost_profile.fixed_team` is true, SEL-006 when `unit_of_work.tiers` is non-empty, SEL-004 when certainty is `RANGE` or `UNKNOWN` and there is no fixed team. Other signals suggest levers: `max_volume_risk` of `SHARED` or `NONE` suggests CL-R01, CL-R02, CL-V08; certainty `RANGE` or `UNKNOWN` suggests CL-V08; `client_can_terminate_early` suggests both CL-P14 variants; `setup_investment` suggests CL-R09; `term.months` over 12 suggests CL-P12.

### A7.5 Composition rules (new rule kind `composition`)

Predicates over `{base_model, levers}`, each with an id, a one-line reason, and `D_PROPOSED`. Draft set:

| Rule | Excludes | Reason |
|---|---|---|
| COMP-001 | CL-V03 with CL-V04 | Two volume price reductions on the same charge. |
| COMP-002 | CL-V08 with CL-R01 or CL-R02 | Two shortfall protections; keep one. |
| COMP-003 | CL-V04 with CL-V05 | Discount and rebate reward the same volume twice. |
| COMP-004 | both CL-P14 variants | Alternative termination terms. |
| COMP-005 | CL-V07 with CL-R02 on PM-014 | A cap and a volume floor on tiered pricing fix the price band twice. |

### A7.6 Templates

Pack templates may declare `composition`. `list_templates` lists core and pack templates with their source, filterable by pack.

## A8. Skeletons and scenario stubs

- **Engagement:** currency, dates, and name are placeholders; `service_category` from the profile; one unit per tier (or one unit, or a raw unit plus weight table for PM-015).
- **Costs:** from `cost_profile.shape`: `MOSTLY_FIXED` adds a monthly team cost placeholder; `MOSTLY_VARIABLE` a cost-per-unit placeholder; `MIXED` both.
- **Scenarios:** shared by every candidate, so comparisons run on identical volumes. Low, expected, and high where the profile gave figures (converted to term totals from `volume.period` and `term.months`, the arithmetic stated in `definitions`), else one scenario with volume placeholders. With tiers, the split across tiers is a placeholder per tier. An early-exit scenario when early termination is possible, with `termination_date` as a placeholder labelled "early-exit date (term midpoint suggested)".

## A9. Non-goals

Proposing any figure; ranking or recommending; market or competitor claims beyond pack evidence; client-facing material; storing profiles or proposals; renewals (v1.1); outcome-based and project-fee structures (later).

## A10. Acceptance tests (T-049 to T-066 in the main spec)

| Test | Pass condition |
|---|---|
| P01 | The A4 profile returns candidates in at least two shortfall groups, including a tiered or weighted unit structure with a minimum and a bounded alternative. |
| P02 | Every expanded skeleton validates except labelled placeholders. |
| P03 | `compare_arrangements` on an unfilled skeleton marks it invalid and lists every placeholder label; `search_structures` rejects one. |
| P04 | Filled fixture skeletons compare on the shared scenarios without other edits. |
| P05 | Identical input gives identical output and fingerprint; a pack version change changes the fingerprint. |
| P06 | No monetary amount or percentage appears that the profile did not supply. |
| P07 | A composition breaking a composition rule appears in `excluded` with its rule id. |
| P08 | An excluded lever appears in no candidate; an included lever appears in every candidate it applies to, and `levers_not_applicable` explains the rest. |
| P09 | Certainty `UNKNOWN` warns, stubs carry placeholders, and a candidate includes CL-V08 or CL-V03. |
| P10 | With early termination possible, every skeleton has an early-exit scenario and a CL-P14 candidate is considered. |
| P11 | Every candidate shows evidence per concept; weak support is flagged. |
| P12 | Unknown fields or values are errors naming the nearest valid value. |
| P13 | Summary output for four candidates stays under 6,000 characters. |
| P14 | The order note is present; no output text calls the order a ranking. |
| P15 | `max_volume_risk: NONE` returns only CLIENT-shortfall candidates. |
| P16 | For the fixture fills, `derive_risk_exposure` on the low scenario agrees with each candidate's declared `volume_shortfall`. |
| P17 | `validate-pack base` rejects a realization that does not validate, an unknown lever id, or a label outside the vocabulary. |
| P18 | `list_templates` lists pack templates with their source. |

## A11. Decisions to confirm

| # | Question | Proposal |
|---|---|---|
| D1 | Priorities ranked? | Yes, 1 to 3. |
| D2 | Candidate count | Default 4, maximum 6. |
| D3 | Skeletons | On request via `expand`. |
| D4 | Several packs | Yes; pack-qualified ids everywhere, mandatory where ids collide (alsp and consulting both define `IMPLEMENTATION`). |
| D5 | Renewals in v1 | **Deferred to v1.1.** The current engagement's quantity names would have to be mapped onto the shared stubs, and `compare_arrangements` has no baseline. |
| D6 | Where mappings live | Pack data, versioned with the pack. |
| D7 | Name | `propose_structures`. |
| D8 | Risk axes and the draft labels in A7.1 and A7.2 | Needs domain review. These labels are the core content of the tool. |
| D9 | v1 scope excludes outcome and project-fee structures | Yes. |
| D10 | Heuristics annotate only, never select | Yes (principle A2.2). |

# Part B. Implementation plan

Built in this repository by Claude, one commit per step, CI green at each.

| Step | Work | Size |
|---|---|---|
| **B0. Prerequisites** | (a) `list_templates` lists core and pack templates with source and optional `pack` filter (core, MCP, CLI). (b) Labelled placeholders: `<required: label>` recognized by prefix, label carried in `REQUIRED_FIELD`; `search_structures` rejects placeholder bases with the list; tests P03, P18. Shippable alone. | Small |
| **B1. Pack schema** | Loader and `validate-pack` support for `realizations/`, the `client_priorities` scheme, `profile_signal` on heuristics, `composition` rules, and template `composition`. A realization is checked by assembling a minimal skeleton and validating it. Ontology export picks up the new records (realizations as `cm:Realization`). Test P17. | Medium |
| **B2. Pack content** | Author A7.1 to A7.5 in `base` 0.2.0 (10 models, 15 lever realizations, 5 priorities, 11 signals, 5 composition rules); add `composition` to the ALSP and consulting templates. Regenerate `docs/ontology/`. **Review gate: the label tables go to Fahad before B3 builds on them.** | Medium; judgment-heavy |
| **B3. Engine** | `core/propose.py`: `DealProfile` model, eligibility, lever pool, canonical compositions, label propagation, exclusion, fit, grouped selection, annotation, evidence, fingerprint. Skeleton and scenario-stub assembly in `core/skeleton.py`. Tests P05 to P09, P12, P15. | Large |
| **B4. Surfaces** | MCP tool `propose_structures`, CLI `cometric propose profile.json [--expand ID]`, `describe_schema("deal_profile")`, a runnable `quickstart` entry, glossary terms for the five risk axes, display precision and detail conventions. Tests P13, P14. | Small |
| **B5. Verification** | Golden output for the A4 profile, hand-reviewed and committed; fixture fills for every expanded candidate; P01, P02, P04, P10, P11, P16. Run the full flow through the MCP server in Claude Desktop as a partner would. | Medium |
| **B6. Documentation and release** | Main spec: section 6.5, the P-03 amendment, change-log entries, tests T-049 onward; README and `docs/PATTERNS.md` section; CHANGELOG; release 0.6.0 through the usual tag flow. | Small |

Order and gates: B0 can ship first (0.5.1) since it helps today. B1 and B2 precede B3 because the engine is a thin layer over the data; the B2 review gate is the main schedule risk, since the labels are judgment, not code. Main technical risk: composition enumeration size (about 10 models × up to 3 of about 12 levers, roughly 3,000 compositions per call). Mitigation: evaluate composition rules and labels on plain dicts and assemble and validate skeletons only for selected or expanded candidates.
