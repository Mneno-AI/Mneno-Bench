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

## Step 8 Scope

The current repository provides:

- Deterministic Python baselines and metrics.
- A synthetic, credential-free demo benchmark.
- Optional Mneno Core evaluation, benchmark export, and trace export integration.
- Version-tolerant normalization for search, context, and compaction evaluations.
- Validated `mneno.benchmark.result` v1 and `mneno.trace` v1 loaders.
- System-independent metric comparison.
- Mneno Context Rot Suite v1 with 48 synthetic memories and 24 deterministic
  cases across eight Mneno-specific failure categories.
- Capability-aware Mneno Core execution with sessions, ordered insertion,
  conflict reports, hierarchy evaluation, compaction preview, per-case context
  building, memory-ID normalization, and trace decision analysis.
- Pydantic v2 result schemas and local JSON result storage.
- A React dashboard that reads generated local result JSON at build/dev time.
- Deterministic failure classification with trace-linked evidence, durable JSON
  reports, Markdown summaries, and a dedicated dashboard page.
- A LOCOMO Retrieval Deep Dive that samples failures across conversations,
  question types, sessions, and categories, then inspects raw candidates,
  scores, context decisions, and traces without changing retrieval behavior.
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

**Mneno Context Rot Suite is a regression benchmark. LOCOMO is an external
validation benchmark.**

## LOCOMO Integration

LOCOMO is the first external benchmark supported by Mneno Bench. It evaluates
long-term conversational memory over independently authored multi-session
conversations, complementing the Mneno-aligned Context Rot Suite without
replacing it.

Step 5 implements dataset loading and validation, keyword and full-context
baselines, optional Mneno execution, normalized local results, trace
preservation, Markdown reporting, and dashboard states. Step 6 adds retrieval,
deterministic-answer, and optional LLM-judge evaluation while keeping official,
diagnostic, retrieval, and judge scores explicitly separated.

Obtain `data/locomo10.json` from the official Snap Research repository:

https://github.com/snap-research/locomo

Methodology reference: https://aclanthology.org/2024.acl-long.747/

Place it at `data/locomo/raw/locomo10.json`, then run:

```bash
python -m benchmarks.locomo.run
```

### LOCOMO Evaluation Modes

`retrieval_only` is the default. It is deterministic, requires no API key, and
reports evidence retrieval and context-construction diagnostics only. Do not
compare a `retrieval_only` score with the official LOCOMO leaderboard.

```bash
python -m benchmarks.locomo.run --mode retrieval_only
```

LOCOMO conversations are independent and can be evaluated in parallel. Use
process workers for throughput runs; results are merged back into the official
dataset order:

```bash
python -m benchmarks.locomo.run --mode retrieval_only --workers 4
```

Parallel execution preserves retrieval and answer metrics, but concurrent CPU
and disk contention changes per-case latency. Use the default `--workers 1`
when comparing latency between runs.

### NVIDIA NIM Reranking

LOCOMO can inject an optional LiteLLM-backed reranker into the real Mneno
`MemoryClient`. The default benchmark remains unchanged and makes no external
calls. A NIM run is an explicitly configured Mneno production variant; its
model, provider, candidate limit, request count, cache hits, and documents sent
are recorded in `export_metadata.mneno_reranker`.

The included hosted-NIM profile sends only the strongest 50 candidates to the
ranking endpoint and caches identical query/candidate requests within each
conversation. Mneno preserves candidates outside that prefix in their original
order.

Set the shared credential in `.env`:

```dotenv
LITELLM_API_KEY=nvapi-your-key
```

Run the complete profile:

```bash
python -m benchmarks.locomo.run \
  --config configs/nvidia-nim-reranker.yaml
```

For a fast validation before the full 1,986-question run:

```bash
python -m benchmarks.locomo.run \
  --mode retrieval_only \
  --workers 10 \
  --max-cases 100 \
  --allow-malformed-evidence \
  --allow-external-calls \
  --mneno-reranker-model nvidia_nim/nv-rerank-qa-mistral-4b:1 \
  --mneno-reranker-provider nvidia_nim \
  --mneno-reranker-api-base https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking \
  --mneno-reranker-candidate-limit 50
```

For a self-hosted Ranking NIM, also set
`MNENO_RERANKER_API_BASE=http://localhost:8000` and pass
`--no-mneno-reranker-api-key-required`. Keep `--allow-external-calls`: it is the
explicit safety gate for every network model call, including localhost.

Do not compare latency from a NIM-enabled run with the default Mneno run as if
they were the same system. Compare retrieval quality and context cost, and
report endpoint, model, worker count, and cache statistics with the result.

`deterministic_answer` creates a local extractive answer candidate and reports
exact match, normalized exact match, token F1, answer containment, and the
released LOCOMO category scorer applied to that candidate. These remain
diagnostics: a compatible scorer does not make the deterministic answer
generation path an official benchmark run, so `official_score` remains null.

```bash
python -m benchmarks.locomo.run --mode deterministic_answer
```

`llm_judge` optionally evaluates generated answers through the shared LiteLLM
client. It requires an enabled model configuration, records model, provider,
prompt version, raw responses, and optionally prompts, and skips cleanly when
configuration or credentials are unavailable. The result is labeled
`llm_judge_score`; it is not promoted to `official_score` unless the complete
official methodology is implemented and validated.

```bash
python -m benchmarks.locomo.run --mode llm_judge \
  --judge-config configs/local.example.yaml
```

When `LITELLM_MODEL`, `LITELLM_PROVIDER`, and `LITELLM_API_KEY` are set in
`.env`, run the judge directly with:

```bash
python -m benchmarks.locomo.run --mode llm_judge --allow-external-calls
```

Without `--mode llm_judge`, LOCOMO remains in its default `retrieval_only`
mode and does not use the configured model or API key.

Docker Compose passes the same `.env` values to the `bench` service at runtime.
After changing `.env`, recreate the service and run LOCOMO inside it:

```bash
docker compose up -d --build --force-recreate bench
docker compose exec bench python -m benchmarks.locomo.run \
  --mode llm_judge \
  --allow-external-calls \
  --allow-malformed-evidence
```

The project `.dockerignore` excludes `.env`, so credentials are not copied into
the benchmark image. `--allow-malformed-evidence` does not repair or discard
upstream annotations; it preserves missing evidence references as dataset
warnings and failure-analysis evidence while allowing the remaining cases to
run.

The fixed outputs are:

- `results/locomo/locomo_latest.json`
- `results/locomo/locomo_latest.md`
- `results/locomo/raw/` for preserved Mneno outputs
- `results/locomo/traces/` for available Mneno traces
- `results/locomo/judge/prompts/` for enabled judge prompt preservation
- `results/locomo/judge/responses/` for raw judge responses

The dataset is optional and ignored by Git. If absent, the command writes a
`dataset_missing` result and skipped report instead of raising an exception.
See `data/locomo/README.md` for accepted formats.

## Failure Analysis

Scores show performance. Failure analysis shows where to improve.

The failure framework examines each provider and benchmark case after scoring.
It uses expected, retrieved, included, excluded, forbidden, session, compaction,
answer, judge, dataset, and trace facts to classify observed problems. It is
deterministic, local-first, and does not require an LLM judge or external API.

The supported categories are:

- `retrieval_failure`: expected evidence was absent from retrieval and context.
- `ranking_failure`: expected evidence was retrieved but not selected, or had a
  documented rank below the usable cutoff.
- `context_budget_failure`: trace evidence shows expected evidence was excluded
  when the context budget was exhausted.
- `lifecycle_filter_failure`: expected evidence was filtered as archived,
  superseded, inactive, or lifecycle-penalized.
- `session_continuity_failure`: expected current-session evidence was not
  retrieved or included.
- `conflict_resolution_failure`: forbidden stale, superseded, or conflicting
  evidence was used.
- `compaction_failure`: available compaction output did not retain expected
  evidence.
- `answer_generation_failure`: required evidence reached context, but the local
  answer metric failed.
- `judge_failure`: an explicitly requested optional judge skipped, errored, or
  returned invalid output.
- `dataset_issue`: evidence references or required annotations were missing or
  malformed.
- `skipped`: an optional provider or capability did not execute.
- `unknown`: a failure was observed, but the available evidence does not support
  a more specific root cause.

Each failure records its reason, supporting evidence, expected/retrieved/context
IDs, trace IDs, severity, and a suggested investigation action. Multiple
categories may apply when each has independent evidence. Missing traces do not
crash analysis, and `unknown` is preferred over an unsupported claim.

Every report contains a global summary, per-provider summaries, a Mneno-only
summary, and a baseline-only summary. The dashboard defaults to the complete
visible failure set and provides All, Mneno, Keyword, Full Context, and Random
provider tabs. Use the Mneno view for product root-cause conclusions; the All
view intentionally mixes product and comparison evidence.

Baseline failures are never hidden. Full Context including stale or forbidden
memories is expected because it includes everything, Random misses provide a
lower bound, and Keyword retrieval or session failures expose lexical and
session-awareness limitations. Their suggested actions are labeled comparison
evidence, while Mneno failures point to potential Mneno Core improvements.

The fixed outputs are:

- `results/mneno/failures/context_rot_suite_failures_latest.json`
- `results/reports/context_rot_suite_failures_latest.md`
- `results/locomo/failures/locomo_failures_latest.json`
- `results/locomo/locomo_failures_latest.md`

Use the dashboard Failure Analysis page to compare category and provider
breakdowns, inspect the worst cases, follow trace IDs, and review suggested
actions. These reports guide product investigation without changing benchmark
fixtures, benchmark labels, or Mneno Core to overfit a score.

## Retrieval Deep Dive

Failure Analysis identifies which cases failed and records the evidence visible
in normalized benchmark results. Retrieval Deep Dive goes one level deeper for
LOCOMO: it reads the completed run, raw Mneno outputs, dataset evidence text,
candidate scores, context inclusions and exclusions, and raw trace events to
explain where expected evidence left the retrieval path.

The deep dive is diagnostics only. It does not call Mneno Core, alter benchmark
logic, change retrieval behavior, or improve scores. Classification is
conservative: unsupported causes remain `unknown`. Core IDs are mapped back to
LOCOMO dialog IDs by exact normalized memory content when the raw artifacts
provide enough evidence.

Run it after a LOCOMO execution and before modifying Mneno Core:

```bash
python -m benchmarks.locomo.deep_dive --max-cases 100 --seed 8
```

The deterministic sampler balances conversations, question types, expected
evidence sessions, and benchmark categories. The report includes retrieval
recall, candidate coverage, root-cause percentages, 25 informative failures,
improvement opportunities, and recommended Core priorities.

The fixed outputs are:

- `results/locomo/deep_dive/retrieval_deep_dive_latest.json`
- `results/locomo/deep_dive/retrieval_deep_dive_latest.md`

Use the dashboard Deep Dive page to filter by provider and root cause, inspect
expected and retrieved evidence, follow trace IDs, and review evidence-backed
opportunities. Any Step 9 Core change should cite evidence from this report
rather than intuition or benchmark-score pressure.

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

The demo requires no API key. Optional LiteLLM calls use one shared
`LITELLM_API_KEY`, regardless of provider.

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

## Realistic Mneno Core Execution

When Mneno is installed, the suite discovers supported runtime capabilities
before execution. It creates stable synthetic sessions where supported, inserts
memories in `session_id`, `sequence_index`, and dataset-ID order, and prefers
`add_with_report()` so conflict reports, resolution actions, internal memory
IDs, and insertion traces can be preserved.

After loading memory, the runner calls `evaluate_hierarchy()` and
`preview_compaction()` when available. Hierarchy transitions and compaction
preview statistics are stored in the execution summary; preview output is used
for compaction-retention metrics without mutating Core storage.

Every case calls search and context evaluation when supported, then calls
`build_context()` with the case budget and current session. Mneno-generated IDs
are mapped back to stable dataset IDs before deterministic metrics are computed.
Included and excluded context IDs, trace IDs, conflict events, hierarchy events,
session events, and inclusion/exclusion reasons are retained per case.

The tracked capabilities are `add_with_report`, `evaluate_search`,
`evaluate_context`, `evaluate_compaction`, `build_context`, `create_session`,
`evaluate_hierarchy`, `preview_compaction`, `export_trace`, and
`export_all_traces`. Missing or signature-incompatible capabilities are recorded
and skipped without failing baseline execution. Metrics that require unavailable
hierarchy, context, compaction, or trace evidence remain `null` and are omitted
from the weighted denominator rather than fabricated as zero.

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
must be enabled explicitly by a benchmark runner.

Configure the model and its credential in `.env`:

```dotenv
LITELLM_MODEL=nvidia_nim/meta/llama-3.1-70b-instruct
LITELLM_PROVIDER=nvidia_nim
LITELLM_API_KEY=nvapi-your-key
```

`LITELLM_API_KEY` is passed directly to LiteLLM for the selected model, so the
project does not require separate OpenAI, NVIDIA, Azure, or other provider key
variables. Set `LITELLM_API_BASE` only when the selected provider needs a custom
endpoint. Local configurations such as Ollama can set `api_key_required: false`.

## Integration Flow

1. The runner detects Mneno and records the Core version.
2. One traced `MemoryClient` is populated from the suite fixture with lifecycle,
   importance, layer, tag, and session metadata.
3. Core conflict reports, hierarchy evaluation, and compaction preview are
   captured when supported.
4. Each case executes search/context evaluation and builds session-aware context
   where supported.
5. Core benchmark and trace exports are preserved as local JSON.
6. Loaders validate v1 envelopes and produce `BenchmarkRun`, `BenchmarkResult`,
   and `TraceSummary` models.
7. Baseline and Mneno normalized results can be passed to `compare_results()`.
8. The dashboard parses capabilities, execution summaries, case decisions, and
   trace evidence from durable local runs.
9. Failure analysis classifies evidence-backed root causes and writes local JSON
   and Markdown reports.

## External Benchmark Sequence

- **LOCOMO:** first external validation pipeline.
- **LongMemEval:** medium validation for longer memory histories.
- **BEAM:** harder stress testing after lifecycle and trace integration matures.

Public benchmark dataset files are not bundled. Integrations must respect
upstream licenses and must never fabricate scores.

## Roadmap

1. Mneno Core export and trace integration: complete
2. Mneno Context Rot Suite v1: complete
3. Richer lifecycle/session setup and trace-level decision explanations: complete
4. Regression tracking across Mneno versions
5. UI comparison and trace exploration
6. LOCOMO execution pipeline: complete
7. LOCOMO evaluation modes and official-compatible scoring: complete
8. Failure analysis framework: complete
9. Real LOCOMO subset evaluation and first failure-driven improvement plan
10. LongMemEval
11. BEAM
