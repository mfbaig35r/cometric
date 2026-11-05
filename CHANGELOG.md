# Changelog

## 0.6.0 (2026-11-05)

Additive. `ENGINE_VERSION` stays 0.3.0: no calculation changed. Validation now reports labelled placeholders and scenario placeholders, and `search_structures` rejects unfilled placeholders. The `base` pack is 0.2.0, so engagements that pin `base` 0.1.0 get a `PACK_VERSION` warning.

- `list_templates` lists core and pack templates, each labelled with its source; `pack` narrows it to one pack. The CLI's `cometric templates` lists all of them.
- Labelled placeholders: `"<required: unit rate, tier high>"` works like `"<required>"` and the label is reported in `REQUIRED_FIELD` (`detail.required_input`). Placeholders in scenarios are now reported as `REQUIRED_FIELD` too.
- `search_structures` rejects a spec whose engagement or scenarios still hold placeholders, except values a search parameter writes.
- `propose_structures` engine (`cometric.core.propose`): validates a deal profile (nearest valid value on errors), builds a lever pool from profile signals, priorities, and partner preferences, enumerates compositions, removes those that break the provider's volume-risk limit or a composition rule, evaluates fit and tension per priority, and lists candidates grouped by who absorbs a volume shortfall, with trade-offs, label assumptions, heuristic notes, evidence strength, the candidate's own inputs and the inputs all share, and on request a skeleton engagement with shared scenarios. Risk labels are checked against `derive_risk_exposure` on filled skeletons (T: P16).
- Surfaces: MCP tool `propose_structures` (20 tools) and a `propose_structures` prompt that walks an LLM through the partner conversation; CLI `cometric propose request.json [--expand ID] [--max N]`; `describe_schema("deal_profile")` and `("propose_options")`; a runnable `quickstart("propose_structures")` and a `propose_then_compare` note; glossary terms for the risk axes; `cometric.propose_structures` exported.
- `base` pack 0.2.0: realizations (how 8 pricing models and 12 levers become engagement terms, with risk labels and label effects), a `client_priorities` scheme, `profile_signal` predicates on the selection heuristics, and composition rules (COMP-001 to COMP-004). `validate-pack` assembles every model, alone and with each lever that applies, fills the placeholders with sample values, and fails if any scenario does not calculate. The ontology export includes realizations.

## 0.5.0 (2026-11-05)

Additive; no breaking changes. `ENGINE_VERSION` stays 0.3.0: no calculation or fingerprint changed.

- Ontology export: `cometric ontology` prints the ontology as Turtle (OWL classes and properties for the input model, SKOS concept schemes for the core vocabularies and every pack, with overlays, rules, claims, and sources as typed resources). `cometric ontology --out DIR` also writes a Markdown reference. The generated reference is committed in `docs/ontology/`, and a test fails when it is stale.
- The glossary moved from the MCP server to `cometric.core.glossary`, so the ontology can use it without the `mcp` extra.

## 0.4.0 (2026-11-05)

Additive; no breaking changes. `ENGINE_VERSION` stays 0.3.0 because no existing calculation changed. Fingerprints of existing scenarios still change, because the scenario schema gained fields with default values (`derived`, and `basis` on assumptions) that are part of the fingerprint.

- Counting rules: assumptions with `basis: RATE` apply every month unchanged; scenarios can declare `derived` quantities (sum, difference, product, quotient over other quantities and constants), evaluated each month in dependency order, with explicit rounding for COUNT units. Results list derived formulas under `definitions`.
- Search parameters can set a named scenario assumption in every scenario (`"assumption": "reissue_rate"`).
- ALSP pack: counting-rule concepts (CNT-001 to CNT-003) and `pattern_counting_rules`.

## 0.3.0 (2026-11-05)

### Breaking changes

- A `DISCOUNT` or `REBATE` with a `threshold` now requires `threshold_scope` (`EXCESS_ONLY` or `ENTIRE_SUBTOTAL`). `DISCOUNT` previously ignored its threshold.
- `CAP`, `REBATE`, and threshold `DISCOUNT` require `accumulation_period`; it previously defaulted to `MONTH` silently.
- Effective client unit price, cost per unit, and unit contribution are null, with `AMBIGUOUS_UNIT_PRICE`, when several quantities are priced and `client_value_unit` is not set. Previously they used the first quantity.
- `search_structures` output is restructured: best results first with full figures; the frontier is parameter sets only at the default `summary` detail.
- `compare_arrangements` and `search_structures` default to `detail: summary` and `precision: display`; the MCP `calculate_periods` tool defaults to `precision: display`. Use `exact` for unrounded figures.
- `ENGINE_VERSION` is 0.3.0, so fingerprints of existing inputs change.

### Added and fixed

- Termination scenarios: `termination_date` on a scenario; `termination_rule` (PRORATE, REMAINDER_DUE, WAIVED) on minimum-spend commitments; `termination_fee` on an arrangement version; allowances expire, unamortized one-time costs are written off, and a `termination` block reports the cost of exiting early.
- ALSP template `tiered_units_annual_minimum` and five worked patterns with hand-computed figures (`docs/PATTERNS.md`).
- "Pending human review" defined in the spec: a label for the user's own approval process, not a workflow.

From an LLM-driven pricing analysis:

- Search: best results first, with full figures per scenario, objective values, constraint results, grid-edge flags (`BEST_AT_GRID_EDGE`), difference from the baseline (the engagement as given), downside per deviation, and fingerprints; `objective.tie_breakers`; `dry_run`; parameters that write several pointers with `set`, `scale`, or `add`.
- `detail` (summary, standard, full) and `precision` (display, exact) on search and compare, defaulting to summary and display; `precision` on calculate_periods (the MCP tool defaults to display). A typical search answer is about 14% of its full size.
- The server stays stateless: engagements are passed by reference as file paths; results reproduce from their fingerprints.

- Threshold discounts and rebates take a required `threshold_scope`: `EXCESS_ONLY` ("10% off charges above the minimum") or `ENTIRE_SUBTOTAL`. `DISCOUNT` previously ignored `threshold` entirely. `CAP`, `REBATE`, and threshold `DISCOUNT` now require `accumulation_period` (it silently defaulted to `MONTH`).
- Effective client unit price (and cost per unit, unit contribution) is null with an `AMBIGUOUS_UNIT_PRICE` warning when more than one quantity is priced and `client_value_unit` is not set; `client_value_unit` accepts `a+b` to sum commensurable units.
- Every calculation result has a `definitions` block: unit-price basis, quantity spreading, thresholds, allowance recognition, minimums.
- `quickstart` tool and resource with a runnable argument object for every tool; `describe_schema` covers candidates, constraints, reference paths, and actuals.
- No unstructured MCP errors: every tool returns a code, message, and hint. Candidates may be bare engagements; constraint leaves accept `{path, op, value}`; search specs are validated up front with field paths; clearer message for fractional counts.

## 0.2.0 (2026-11-05)

- `reconcile`: compare computed figures with recorded actuals by month and term, with a publishable summary that carries no amounts, dates, or names (API, CLI, MCP tool). Guide in `docs/RECONCILIATION.md`.
- Fix: ALL_UNITS cliff detection now reports bands across non-adjacent tiers, with an inclusive lower bound where a band starts at a tier edge. Found by property testing.
- MCP resource `cometric://packs/{pack}/templates/{id}`; CLI `templates --pack` and `template --pack`.
- `TIER_CLIFF` warnings: one per threshold with a `bands` list (lower, lower_inclusive, upper_exclusive), replacing the single `band` pair.
- Fixed from code review of `reconcile`: uncalculated costs are reported as not computed instead of zero (decided once in the shared calculation step); invalid actuals and tolerances return issues instead of raising; infeasible scenarios never report `reconciled`; unknown metrics are errors; the result has its own fingerprint over actuals and tolerances; month numbers count from the engagement start; repeated scans removed.
- Fixed from the full engine review (calculation changes, so `ENGINE_VERSION` moves to 0.2.0):
  - `FULL_MONTH_FROM_CURRENT` and `FULL_MONTH_FROM_NEXT` now bill the whole month instead of prorating by component dates.
  - A fixed project payment due in a month split between contract versions is no longer dropped.
  - A horizon that starts after the engagement simulates from the engagement start, so allowances, tiers, minimums, caps, and outcome periods carry into it; year and term assumptions spread over the engagement's months.
  - One-time fees are never prorated; quarterly and annual fees keep their declared totals and anchor at the component start.
  - Collars reprice at the cumulative tier position.
  - Indexation applies to period-end overage as well as cumulative overage, not to project payments or outcome fees, and contract years honor the start day.
  - Term costs that start later keep their declared total.
  - The incurred-view adjustment ignores portfolio and overhead costs.
  - A performance trigger missing from the scenario is an error; the price floor reports missing costs as an issue.
  - Components are evaluated in id order, so results never depend on list order.
  - Rebates settled after the horizon raise `TRUE_UP_OUTSIDE_HORIZON`.
- Spec v0.3.

## 0.1.0 (2026-11-04)

First release.

- Core engine: deterministic decimal monthly calculation with the specified evaluation order (allowances, tiers, collars, discounts, minimums, performance adjustments, caps), accumulation periods, entitlement ledger with rollover, proration, exact allocation, margin-layer cost policies, capacity breach modes, and input fingerprints.
- Fee methods: fixed recurring, time, dedicated resource, unit output, weighted unit output, allowance plus overage, fixed project, and outcome adjustment (gain-share, success fee, percent of outcome).
- Realization against a standard rate card: standard value, realization, write-down, effective billing rate.
- Operations: validate, calculate, explain, compare (dominance), structure search (frontier), risk exposure, price floor, break-even, and commercial constraint checks.
- Packs (data only): `base`, `alsp`, and `consulting`, with evidence records and verification status.
- Interfaces: CLI and a read-only MCP server (stdio and stateless HTTP) with discovery tools, resources, and guided prompts.
- Casebook fixtures A to H.
