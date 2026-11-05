# Cometric

[![CI](https://github.com/mfbaig35r/cometric/actions/workflows/ci.yml/badge.svg)](https://github.com/mfbaig35r/cometric/actions/workflows/ci.yml)

**Commercial Intelligence Engine.** Cometric models the commercial arrangements behind service engagements, simulates their economics month by month, and searches for structures that balance profitability, risk, and client value.

1. **Model.** Arrangements are compositions, not a single "pricing model": billing bases, rate schedules, allowances, minimums, adjustments, delivery costs, and capacity, each typed and validated.
2. **Simulate.** A deterministic decimal engine computes contractual fees, costs by margin layer, contribution, client effective unit price, capacity use, and who absorbs each deviation from plan.
3. **Optimize.** A grid search over the parameters you declare returns the trade-off frontier. Nothing is ranked unless you supply an objective, and every recommendation is marked for human review.

It is built for any service relationship priced through a composite arrangement: consulting, outsourcing, managed services, and alternative legal services. Sector knowledge ships as data-only packs.

## Guarantees

- **No model arithmetic.** Every amount is computed by decimal code. Floating-point input is rejected.
- **Reproducible.** Each result carries a SHA-256 fingerprint of its canonical inputs, engine version, and policies.
- **Traceable.** Every fee line records its evaluation step, formula, quantity, and contract version.
- **Explicit policy.** Cost layering, capacity ceilings, recognition rules, and risk tolerances are inputs. Missing economic policy is an error, never a silent default.
- **Labeled knowledge.** Pack concepts and claims carry evidence classes. Inference and proposals are always labeled as such.

## Install

```bash
pip install "cometric[mcp]"           # or: uv pip install "cometric[mcp]"
uv sync --all-extras                  # from a checkout
```

[![PyPI](https://img.shields.io/pypi/v/cometric)](https://pypi.org/project/cometric/)

Python 3.11 or later.

## Quickstart

```bash
cometric validate src/cometric/examples/spec_example.json
cometric calculate src/cometric/examples/case_a.json --scenario base --cost-policy reference
cometric explain src/cometric/examples/spec_example.json --period 2027-01
cometric break-even src/cometric/examples/case_b.json --driver contracts --scenario base --cost-policy reference
cometric floor src/cometric/examples/case_b.json --cost-policy reference --target-margin 0.20
cometric template base_plus_overage
cometric lookup PM-023
```

```python
import json

import cometric

case = json.load(open("src/cometric/examples/case_a.json"))
result = cometric.calculate_periods(case["engagement"], case["scenarios"][1], "reference", detail="periods")
print(result["term"]["contribution_margin"], result["input_fingerprint"])
```

## MCP server

Cometric ships a read-only, stateless MCP server: 17 tools, schema and template discovery, resources for the glossary, schemas, concept schemes, rules, coverage, templates, and worked examples, and six guided prompts.

```bash
cometric mcp                                   # stdio
COMETRIC_ALLOWED_ROOT=/path/to/models cometric mcp   # stdio, may read input files under that root
cometric mcp --transport http --port 8765      # stateless streamable HTTP at POST /mcp
```

Claude Code:

```bash
claude mcp add cometric -- uvx --from "cometric[mcp]" cometric mcp
```

The HTTP transport keeps no session state, answers `GET /mcp` with 405, keeps DNS-rebinding protection on (set `COMETRIC_ALLOWED_HOSTS` for your hostname), and checks a bearer token when `COMETRIC_MCP_TOKEN` is set.

## Concepts

| Concept | Meaning |
|---|---|
| Engagement | Parties, units, services, effective-dated arrangement versions, delivery plan |
| Fee component | One charge computed by one method: fixed recurring, time, dedicated resource, unit output, weighted unit output, allowance plus overage, fixed project, outcome adjustment (gain-share, success fee, percent of outcome) |
| Realization | Contractual fee against hours worked at a standard rate card, with write-down and effective billing rate |
| Accumulation period | Allowances, minimums, tiers, and capacity accumulate over a declared period independent of the monthly grain |
| Evaluation order | Resolve, measure, consume allowances, price, collar, discount, minimum, performance, cap |
| Cost policy | Maps each cost category to exactly one margin layer; `reference` is shipped and must be named |
| Scenario | Immutable, origin-labeled assumptions spread to months by exact allocation |
| Derived risk | Who absorbs a deviation: provider contribution versus client unit price |
| Dominance | A candidate is dominated when another is at least as good on every metric and better on one |

## Packs

Packs are YAML only, with no executable code. `base` holds domain-neutral commercial knowledge: billing bases, 34 pricing models, 61 levers, 16 commercial dimensions, 49 metrics and indicators, cost categories, compatibility and reasoning rules, selection heuristics, mechanisms, and negotiation exchanges. `alsp` extends it for alternative legal services with service categories, unit templates, provider types, regulatory review rules, sector prevalence overlays, and evidence. `consulting` extends it for advisory work with realization and staffing concepts, outcome-fee review rules, and five templates: role-based time and materials, capped time and materials, phased fixed fee, hours-drawdown retainer, and fixed fee plus success fee.

```bash
cometric packs
cometric validate-pack alsp
cometric validate-pack consulting
```

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run python scripts/build_fixtures.py   # regenerate casebook fixtures
```

The specification is in `docs/COMETRIC_SPEC_v0.2.md`. Implementation status and clarifications are in `docs/STATUS.md`.

## License

Apache License 2.0. See `LICENSE`.
