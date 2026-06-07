# Mneno Bench

Mneno Bench is the benchmark platform built specifically to validate Mneno.
Mneno is an explainable memory runtime for AI systems. Its purpose is to keep
long-running context useful, compact, lifecycle-aware, and verifiable.

This repository is intentionally not a generic benchmark framework. It asks a
narrower question: does Mneno improve context management compared with simple,
transparent baselines?

## Why Mneno Bench Exists

Long-running AI systems accumulate facts, preferences, corrections, intermediate
work, and noise. Context rot occurs when that growing history becomes less
useful: stale facts reappear, current facts are crowded out, contradictions are
resolved poorly, or compaction removes evidence that still matters.

Mneno Bench starts with a proprietary Mneno Context Rot Suite because the first
job is product validation. Public benchmarks come later as independent
validation layers, not as substitutes for testing Mneno's actual contract.

## Step 3 Scope

The current repository provides:

- Deterministic Python baselines and metrics.
- A synthetic, credential-free demo benchmark.
- Optional Mneno Core evaluation, benchmark export, and trace export integration.
- Version-tolerant normalization for search, context, and compaction evaluations.
- Validated `mneno.benchmark.result` v1 and `mneno.trace` v1 loaders.
- System-independent metric comparison.
- Mneno Context Rot Suite v1 with 48 synthetic memories and 24 deterministic
  cases across eight Mneno-specific failure categories.
- Pydantic v2 result schemas and local JSON result storage.
- A React dashboard that reads generated local result JSON at build/dev time.
- LiteLLM-ready provider configuration behind one client abstraction.
- Docker Compose services for the web UI and benchmark runner.
- Placeholders for LOCOMO, LongMemEval, and BEAM.

It does not ship external datasets, call model providers during tests, or report
official public benchmark scores.

## Mneno-Specific Metrics

- **Context efficiency:** useful evidence tokens divided by supplied context
  tokens.
- **Context rot resistance:** retention of useful, current evidence across
  long-running sessions.
- **Stale memory suppression:** avoidance of obsolete or superseded memories.
- **Conflict resolution:** preference for the correct current fact when
  memories contradict.
- **Memory lifecycle behavior:** correct treatment of active, superseded,
  expired, and compacted memories.
- **Compaction quality:** preservation of answer-critical evidence after
  compression.
- **Retrieval quality:** deterministic precision, recall, and reciprocal rank.
- **Explainability coverage:** share of memory decisions backed by trace
  evidence.

The suite is the flagship product benchmark, but its synthetic scores are not
public-benchmark claims.

## Mneno Context Rot Suite

Mneno Context Rot Suite v1 is the flagship first-party benchmark. It asks
whether Mneno keeps accumulated context useful, compact, lifecycle-aware, and
verifiable better than keyword retrieval, deterministic random retrieval, and
passing the full context unchanged.

The suite contains three deterministic cases in each category:

- stale preference suppression
- preference changes
- contradiction handling
- lifecycle-aware retrieval
- session continuity
- context budget efficiency
- compaction retention
- explainability coverage

Unlike LOCOMO, LongMemEval, and BEAM, this suite is designed around Mneno's
product contract. It uses only local synthetic fixtures, has explicit expected
and forbidden memory IDs, requires no model judge, and preserves raw Core
exports and traces whenever Mneno is installed.

Run it with either command:

```bash
scripts/run_demo.sh
python -m benchmarks.mneno_suite.run
```

The fixed outputs are:

- `results/mneno/context_rot_suite_latest.json`
- `results/reports/context_rot_suite_latest.md`
- `results/mneno/exports/` for raw Core benchmark exports
- `results/mneno/traces/` for raw Core traces

The **Mneno Context Rot Score** weights expected recall at 25%, stale
suppression at 20%, inverse forbidden-memory error rate at 15%, context
efficiency at 15%, lifecycle alignment at 10%, session continuity at 10%, and
explainability coverage at 5%. Compaction retention is reported separately so
its behavior remains visible without silently changing the published score.

Stale suppression measures forbidden memories avoided. Context efficiency
measures useful expected-memory tokens divided by supplied tokens. Lifecycle
alignment rewards active evidence and avoidance of inactive evidence.
Explainability coverage requires trace events, decisions, or reasons; missing
trace data is not converted into a successful score.

## Requirements

- Python 3.11 or newer
- Node.js 22 or newer
- Docker with Compose, optional

## Install

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
scripts/setup_dev.sh
```

The demo requires no API keys. LiteLLM provider variables may remain empty.

## Using Mneno Core

Mneno is optional. When it is unavailable, benchmark baselines still run, every
Mneno case is marked `skipped`, and the dashboard continues to load.

Install from PyPI when the distribution is available:


```bash
pip install mneno
```

Install a local Core wheel:

```bash
pip install vendor/wheels/mneno-*.whl
```

Or install a specific wheel during setup:

```bash
MNENO_WHEEL_PATH=/absolute/path/to/mneno.whl scripts/setup_dev.sh
```

If Mneno is unavailable, the demo still completes and marks Mneno results as
`skipped`.

`MnenoAdapter` in `benchmarks/common/mneno_client.py` is the only supported SDK
boundary. It creates `MemoryClient(trace_enabled=True)`, invokes
`evaluate_search()`, `evaluate_context()`, and `evaluate_compaction()`, and
calls the benchmark and trace export APIs.

Mneno benchmark exports use the `mneno.benchmark.result` v1 envelope. They are
preserved as raw JSON under `results/mneno/exports/` and can be loaded through
`EvaluationLoader`. Mneno traces use the `mneno.trace` v1 envelope. Individual
and aggregate trace exports are preserved under `results/mneno/traces/`, while
`TraceLoader` derives dashboard-ready operation, event, decision, and duration
summaries.

Search, context, and compaction evaluations are normalized only for comparison.
Their raw results, trace IDs, provider, query, and metric values remain attached
to the normalized models. The normalization layer hides SDK version and
baseline shape differences without replacing the authoritative Core exports.

## Run the Demo

```bash
scripts/run_demo.sh
```

The runner reads `data/mneno_suite/`, writes the stable latest `BenchmarkRun`
under `results/mneno/`, preserves available Core exports, and writes a Markdown
summary under `results/reports/`.

These outputs are synthetic development artifacts. They are not LOCOMO,
LongMemEval, or BEAM scores.

## Start the UI

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite reads local
`results/mneno/*.json` files and falls back to a clearly labeled synthetic
sample when no generated run exists. No backend is required.

## Checks

```bash
scripts/check.sh
scripts/format.sh
```

## Docker

Start both services:

```bash
docker compose up --build
```

The UI is available at [http://localhost:5173](http://localhost:5173). The
benchmark service runs the demo once and remains available for additional runs:

```bash
docker compose exec bench scripts/run_demo.sh
```

Results are written to the host `results/` directory.

## LiteLLM

Provider examples live in `configs/`. `benchmarks/common/llm_client.py` is the
only supported route for model calls. External calls are disabled by default and
must be enabled explicitly by a future benchmark runner.

## Integration Flow

1. The runner detects Mneno and records the Core version.
2. One traced `MemoryClient` is populated from the suite fixture with lifecycle,
   importance, layer, tag, and session metadata.
3. Each case executes search evaluation, plus context or compaction evaluation
   where the category requires it.
4. Core benchmark and trace exports are preserved as local JSON.
5. Loaders validate v1 envelopes and produce `BenchmarkRun`, `BenchmarkResult`,
   and `TraceSummary` models.
6. Baseline and Mneno normalized results can be passed to `compare_results()`.
7. The dashboard parses durable local runs and exposes version and trace data.

## Why Public Benchmarks Come Later

- **LOCOMO:** easy external validation after the first-party suite is credible.
- **LongMemEval:** medium validation for longer memory histories.
- **BEAM:** harder stress testing after lifecycle and trace integration matures.

Public benchmark dataset files are not bundled. Future integrations must
respect upstream licenses and must never fabricate scores.

## Roadmap

1. Mneno Core export and trace integration: complete
2. Mneno Context Rot Suite v1: complete
3. Richer lifecycle/session setup and trace-level decision explanations
4. UI comparison and trace exploration
5. LOCOMO
6. LongMemEval
7. BEAM
