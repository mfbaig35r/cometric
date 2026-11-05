# Changelog

## Unreleased

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
