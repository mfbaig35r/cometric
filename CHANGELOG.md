# Changelog

## 0.1.0 (2026-11-04)

First release.

- Core engine: deterministic decimal monthly calculation with the specified evaluation order (allowances, tiers, collars, discounts, minimums, performance adjustments, caps), accumulation periods, entitlement ledger with rollover, proration, exact allocation, margin-layer cost policies, capacity breach modes, and input fingerprints.
- Fee methods: fixed recurring, time, dedicated resource, unit output, weighted unit output, allowance plus overage, fixed project, and outcome adjustment (gain-share, success fee, percent of outcome).
- Realization against a standard rate card: standard value, realization, write-down, effective billing rate.
- Operations: validate, calculate, explain, compare (dominance), structure search (frontier), risk exposure, price floor, break-even, and commercial constraint checks.
- Packs (data only): `base`, `alsp`, and `consulting`, with evidence records and verification status.
- Interfaces: CLI and a read-only MCP server (stdio and stateless HTTP) with discovery tools, resources, and guided prompts.
- Casebook fixtures A to H.
