# Changelog

## Unreleased

- `reconcile`: compare computed figures with recorded actuals by month and term, with a publishable summary that carries no amounts, dates, or names (API, CLI, MCP tool). Guide in `docs/RECONCILIATION.md`.
- Fix: ALL_UNITS cliff detection now reports bands across non-adjacent tiers, with an inclusive lower bound where a band starts at a tier edge. Found by property testing.
- MCP resource `cometric://packs/{pack}/templates/{id}`; CLI `templates --pack` and `template --pack`.
- `TIER_CLIFF` warnings: one per threshold with a `bands` list (lower, lower_inclusive, upper_exclusive), replacing the single `band` pair.
- Fixed from code review of `reconcile`: uncalculated costs are reported as not computed instead of zero (decided once in the shared calculation step); invalid actuals and tolerances return issues instead of raising; infeasible scenarios never report `reconciled`; unknown metrics are errors; the result has its own fingerprint over actuals and tolerances; month numbers count from the engagement start; repeated scans removed.
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
