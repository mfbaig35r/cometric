# Cometric implementation status

Version `0.2.0` (0.1.0 released 2026-11-04; 0.2.0 adds reconciliation and the fixes from two code reviews). The normative specification is `COMETRIC_SPEC_v0.3.md`, which incorporates every clarification below.

## Milestones

| Milestone | State | Notes |
|---|---|---|
| M0 schema freeze | Superseded by M1 | The engine was built directly; the clarifications below are the semantic questions it surfaced. |
| M1 core engine | Done | All seven casebook fixtures reproduce the report under both cost policies. |
| M2 compare, optimize, MCP | Done | Dominance comparison, structure search, risk exposure, stdio MCP with discovery, five core templates. |
| M3 knowledge packs | Done, with evidence caveats | `base` and `alsp` packs validate; 29 of 39 sources verified (see Evidence). |
| M4 release | Partly done | Stateless HTTP transport built and tested. Public on GitHub under Apache-2.0 with CI; released to PyPI as 0.1.0 (2026-11-04); no practitioner reconciliation yet. |
| M5 consulting pack | Done (pending reconciliation) | Core realization and `OUTCOME_ADJUSTMENT` built; `consulting` pack with 5 templates and illustrative Case H. Exit criterion still needs one real engagement reconciled. |

## Tests

110 tests (`uv run pytest`): T-001 to T-035, outcome and realization tests, and property tests. T-033 (every report identifier captured) runs only when the private research report is present in `docs/`; it is gitignored and not shipped.

## Clarifications made while implementing

These were decisions v0.2 left implicit. All are now part of `COMETRIC_SPEC_v0.3.md`; the list stays here for history.

1. **Tier counters always recognize cumulatively.** `PERIOD_END` recognition applies to allowances and minimums. A tier schedule's accumulation period sets when its counter resets.
2. **Tiered overage with `ALL_ELIGIBLE` scope** must use `MARGINAL` tiers and non-`PERIOD_END` recognition in v1. Other combinations are rejected with `UNSUPPORTED_COMBINATION`.
3. **Split months.** When a month spans two contract versions, fees are priced per segment, and the adjustments and commitments of the version in force at month end apply to the whole month. Allowance grants are not prorated.
4. **Collars** are evaluated per month on that month's measured quantity, with one repricing form: an alternate rate schedule for units outside the band.
5. **Rebates** credit a percentage of the period subtotal at period end when the subtotal meets the threshold.
6. **Indexation** compounds from the second contract year as `(1 + p)^n - 1` on step-4 lines.
7. **Performance adjustments.** SLA credits and bonuses multiply by a scenario trigger quantity (for example, misses in the month); holdbacks withhold unless the trigger releases them.
8. **Production standards** name a scenario quantity (optionally with a band) rather than a unit code; they derive `demand_hours`.
9. **Capacity breach** is tested cumulatively within the capacity's period. A breach is strictly greater than capacity. `BACKLOG` reduces served (and billed) units and carries the excess.
10. **Fixtures live in `src/cometric/examples/`**, not a repo-root `fixtures/` directory, so the MCP server can serve them as resources.
11. **Commitment kinds** other than `MINIMUM_SPEND` are validated and recorded but not computed (`COMMITMENT_NOT_COMPUTED` warning).
12. **The reference cost policy** uses the amortized transition view. Both views are always reported on one-time cost lines; the transition payback month uses the incurred view.
13. **Compatibility assessments number 17**, not 16: the report's table has 17 rows. COMPAT-001 to 016 are in `base`; COMPAT-017 (contingent fees with non-law-firm providers) is in `alsp`.
14. **Break-even** brackets whole driver units and interpolates linearly between them; the result says so.
15. **Proration policy** may be declared on either version at a mid-month boundary.
16. **HTTP transport** keeps DNS-rebinding protection on. Allowed hosts default to localhost; set `COMETRIC_ALLOWED_HOSTS` for a deployment.
17. **Realization** uses an engagement-level `delivery_plan.standard_rate_card` and worked hours per role (`<worked_hours_source>.<role>`), not a per-component standard schedule, so it applies to fixed and outcome fees as well as time.
18. **Outcome fees** (`OUTCOME_ADJUSTMENT`) support SHARE, SUCCESS, and PERCENT_OF_OUTCOME, are charged at the end of their accumulation period only (v1), apply attribution to SHARE and PERCENT forms, and always raise an approval requirement until `approval_reference` is recorded.

## Evidence

Each source was fetched on 2026-11-03 and checked against the claims the research uses it for; a second pass on 2026-11-04 corrected claims and checked full documents. Results are recorded on each source record (`verification` field).

| State | Count | Sources |
|---|---|---|
| Verified as cited | 27 | includes E034, checked against the full supervisory statement |
| Verified at a new URL | 3 | E013, E019, E027 |
| Verified after narrowing the claim to what the source says | 3 | E008 (no "per user"), E016 (no "guaranteed"), E032 (July 2026 update concerns critical third parties) |
| Partial: detail behind a registration form | 2 | E001, E040; affected claims carry a caveat |
| Not yet checked: publisher blocks automated access | 4 | E028, E029 (US model rules 1.5 and 5.4), E035 (UK data-protection AI contracting guidance), E039 (law-firm KPI definitions) |

The six unverified sources stay `verified: false`. The four blocked ones need a manual check in a browser; the two registration-walled ones need someone to download the full reports.

Many report statements cite sources that are not in its evidence register. The pack agent made no A or B claims for them; the affected concepts carry caveats, and the group is listed in `packs/base/excluded.yaml`.

## Not built yet

- Health indicators that need actuals over time (CHI-004, 005, 006, 008, 009, 010, 012).
- Pack-level engagement templates (the report's three offers and automation structures exist as concepts only).
- SKOS / JSON-LD export of packs.
- Monte Carlo and Margin-at-Risk.
- `COST_PLUS`, `GRADUATED_BLOCK` tiers, component-level version coexistence.
- Cumulative recognition for outcome fees.

## Open questions

- **Q-2 License.** Resolved: Apache-2.0 (`LICENSE`).
- **Q-3 Research report.** Kept out of the repository by `.gitignore`.
- **Q-5 Firm names in evidence.** Pack text never names firms; source URLs do, because they are citations.
