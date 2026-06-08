# AGENTS.md

## Project Overview

Mneno Bench validates Mneno, an explainable memory runtime for AI systems. The
repository measures whether Mneno keeps long-running context useful, compact,
lifecycle-aware, and verifiable compared with simple baselines.

This is not a generic benchmark platform. Mneno is the primary system under
test.

## Repository Structure

- `benchmarks/common/`: shared schemas, clients, baselines, metrics, and file
  utilities.
- `benchmarks/mneno_suite/`: first-party Mneno Context Rot Suite.
- `benchmarks/{locomo,longmemeval,beam}/`: external benchmark placeholders.
- `data/synthetic/`: small redistributable development fixtures.
- `configs/`: LiteLLM-ready provider configuration.
- `results/`: generated local JSON and Markdown reports.
- `src/`: static React dashboard.
- `docker/bench/`: Python benchmark container.
- `vendor/`: local Mneno wheels and private integration notes.

## Mneno-First Benchmark Philosophy

Start with failure modes that matter to Mneno: stale memory suppression,
preference changes, contradiction handling, session continuity, lifecycle-aware
retrieval, context budget efficiency, compaction retention, and explainability.

Public benchmarks validate the product later. They do not define the initial
product contract.

## Mneno Context Rot Suite Rules

- Mneno Context Rot Suite is the flagship benchmark.
- Keep every suite case and metric deterministic; do not use LLM judges unless
  a later step explicitly adds them.
- Do not tune synthetic fixtures to fabricate or guarantee Mneno performance.
- Every case must identify expected and forbidden memory IDs where relevant.
- Keep the full-context baseline so token inefficiency and stale-memory risk are
  visible rather than hidden.
- Keep Mneno-specific metrics explainable through explicit numerators,
  denominators, lifecycle states, sessions, and trace evidence.

## Development Setup

Use Python 3.11+ and Node.js 22+.

```bash
python3 -m venv .venv
source .venv/bin/activate
scripts/setup_dev.sh
scripts/check.sh
```

## Docker Setup

`docker compose up --build` starts the Vite web service and the Python benchmark
service. The benchmark container mounts `benchmarks/`, `data/`, `results/`,
`configs/`, and `vendor/`. Generated results must remain visible on the host.

## Python Benchmark Layer

- Use Pydantic v2 models from `benchmarks/common/schema.py`.
- Keep runners executable with `python -m`.
- Keep deterministic retrieval and scoring separate from optional LLM judges.
- Keep baseline interfaces comparable with Mneno inputs and outputs.
- Emit one `BenchmarkRun` JSON file per run.
- Record skipped and failed systems explicitly; do not silently omit them.

## React UI Layer

- Use React, Vite, TypeScript, Tailwind CSS, and PostCSS.
- Do not introduce Next.js.
- Keep state local and simple until generated result loading requires more.
- UI examples must be labeled synthetic or static.
- Preserve accessible navigation, visible focus states, semantic tables, and
  readable status text.
- Do not add auth or a database in the MVP.

## LiteLLM Rules

- All model calls go through `benchmarks/common/llm_client.py`.
- External calls are disabled by default.
- Tests and the demo must not require API keys or network model access.
- Provider-specific code must not leak into benchmark runners.
- Keep temperature at zero for deterministic evaluation unless a benchmark
  explicitly requires sampling.

## Mneno SDK Integration Rules

- Treat `mneno` as an optional dependency.
- Import it through `benchmarks/common/mneno_client.py`.
- Support installation from PyPI and `vendor/wheels/`.
- Benchmark against real Mneno evaluation APIs whenever the SDK is available.
- Missing Mneno must produce a clear skipped result, not a crashed run.
- Never fabricate Mneno benchmark results or fill missing trace metrics with zero.
- Preserve raw Mneno benchmark exports and raw trace exports as local JSON.
- Normalize SDK output only for comparison and dashboard consumption.
- Keep SDK-specific object conversion inside the adapter.
- Preserve Mneno trace and lifecycle semantics when normalizing Core exports.
- Exercise real Mneno session, conflict, hierarchy, compaction-preview, and
  context-building behavior whenever the installed SDK supports it.
- Missing or signature-incompatible Mneno capabilities must degrade gracefully.
- Never fabricate a metric that depends on unavailable Core behavior; preserve
  it as unavailable with a reason.
- Keep dataset memory IDs stable and normalize generated Core IDs through an
  explicit bidirectional mapping.
- Use trace decisions and reasons for explainability metrics where possible.

## Result Schema

`BenchmarkRun` is the durable top-level artifact. It contains schema version,
run metadata, systems, case results, summary metrics, errors, and export
metadata. `BenchmarkResult` stores comparable baseline and Mneno outputs.
`TraceSummary` stores dashboard-ready trace facts and a reference to raw trace
data where available.

Schema changes must remain explicit and versioned. Prefer additive changes.

## Metrics Philosophy

- Use deterministic metrics first.
- State the numerator, denominator, and direction for every metric.
- Keep metric functions system-independent.
- Treat placeholder metrics as placeholders in code and documentation.
- Never convert missing trace data into a zero score when the correct state is
  unavailable or skipped.
- Report context cost alongside retrieval quality.

## Adding a Mneno-Specific Benchmark

1. Add small synthetic fixtures with explicit expected and stale memory IDs.
2. Define the memory lifecycle or context-rot failure being tested.
3. Run at least one transparent baseline on the same inputs.
4. Normalize Mneno output through the adapter and shared schema.
5. Add deterministic metrics and focused tests.
6. Write local JSON and a human-readable report.
7. Label any LLM-judged metric and keep it optional.

## Adding Public Benchmark Support

1. Review the upstream license and redistribution terms.
2. Keep datasets outside Git unless redistribution is explicitly permitted.
3. Document acquisition and preprocessing without changing official labels.
4. Preserve official scoring separately from Mneno-specific supplemental
   metrics.
5. Validate the runner against upstream examples before publishing claims.

## Do NOT

- Do not turn the MVP into a generic benchmark framework.
- Do not fake LOCOMO, LongMemEval, BEAM, or Mneno scores.
- Do not commit licensed datasets without redistribution permission.
- Do not require external API keys for tests or the demo.
- Do not call LiteLLM outside the shared client abstraction.
- Do not tightly couple baseline code to Mneno SDK types.
- Do not remove Mneno as the primary system under test.
- Do not use nondeterministic metrics when deterministic evidence is available.
- Do not add a database, authentication, or complex state management in Step 1.
- Do not present static UI preview values as benchmark results.
