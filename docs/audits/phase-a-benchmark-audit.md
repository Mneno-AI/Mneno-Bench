# Phase A benchmark integrity audit

Audit date: 2026-10-10. Inspected Bench revision: `5ab10e8a8e0f32995b479eae7db70ce5b8521b58` (clean at start). Scope: repository documentation, configuration, Python runners/adapters/metrics/classifiers, regression tests, tracked artifacts, React loaders/pages, setup and Docker configuration. Core source was not inspected or modified. No full benchmark or external model call was executed. This is an infrastructure audit, not a performance claim.

## Assessment

Useful deterministic regression infrastructure exists, but historical projections are insufficient to reproduce scores and current stage attribution and run identity need corrections before controlled Core comparisons. No historical result qualifies as verified and reproducible. Core 0.4.1 is not established here: the retained run records 0.4.0; no Mneno installation or wheel is present in this workspace.

## Architecture and lifecycle

- `benchmarks/locomo/loader.py` accepts optional official/normalized local JSON; validator checks IDs and annotations, with explicit malformed-evidence warnings. Missing data produces a durable skipped run. Invalid data can raise validation errors before a run is persisted.
- `locomo/run.py` groups questions by independent conversation, ingests timestamp/speaker-prefixed messages, creates sessions where possible, and records dataset-to-Core IDs plus their reverse in runtime. Each conversation owns a client and optional cached reranker. Baselines share the formatted memories.
- `common/mneno_client.py` is the SDK boundary; signature filtering and JSON conversion permit version tolerance. LOCOMO executes search evaluation, context evaluation, and context construction separately. These may be separate retrieval passes, with distinct traces and provider/cache effects.
- ID extraction and reverse mapping in LOCOMO precede deterministic scoring. Raw outputs and traces are saved by run/case, then atomic per-case checkpoints are written. Conversation jobs use processes for local parallel work and threads with a shared limiter for external calls. Results merge by question ID into dataset order.
- Summary aggregation, JSON/Markdown, failure reports, and compact dashboard projections follow execution. `BenchmarkRun` is the durable shared Pydantic artifact; the compact projection is not its evidentiary replacement.
- React imports local projections eagerly via Vite; `listRuns()` returns that parsed static collection. A deployed build does not poll disk. Missing generated results use labeled synthetic previews.
- Context Rot has a separate fixture loader, runtime/execution layer, deterministic scoring and trace analysis. LongMemEval and BEAM remain outside this phase.

## Historical verification

“Verified but not reproducible” below verifies that the value is recorded in a saved summary, **not** that its calculation or execution is independently verified. Recomputing the aggregate needs the missing original cases and dataset. The three claimed values must not be shown as a controlled three-way comparison.

| Historical observation | Classification | Evidence |
|---|---|---|
| Mneno Core 0.2755 | Unverified | No matching aggregate or original run found in workspace artifacts or tracked files. Command, dataset checksum, question count, revision, SDK, budgets, provider, cache, failures and timestamp unknown. |
| Keyword 0.3902 | Verified but not reproducible | `results/locomo/dashboard/runs/locomo_dashboard_latest.json` records 0.390220. It is a projection with `results: []`, not a complete run. |
| Mneno + NIM 0.5919 | Verified but not reproducible | Same projection records 0.591924. Original run, checkpoints, source dataset and raw per-case exports are absent. |

Projection SHA-256: `820cc4cac012eef6bca024128cf0d9ad87b3d5256f8eb738801dfcebac1a4a76`.

| Required provenance | Keyword and NIM retained evidence |
|---|---|
| Exact command | Not retained. A plausible reconstruction is `python -m benchmarks.locomo.run --mode retrieval_only --workers 10 --resume --allow-malformed-evidence --allow-external-calls --mneno-reranker-model nvidia_nim/nv-rerank-qa-mistral-4b:1 --mneno-reranker-provider nvidia_nim --mneno-reranker-api-base https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking --mneno-reranker-candidate-limit 50`; this is **not** verified execution history. |
| Configuration | Embedded `config` is retained; retrieval only, 10 threads, malformed evidence allowed, full phase, resume enabled. |
| Dataset | Named `locomo10`, 10 conversations, 5,882 messages, 1,986 questions. Recorded original path `/Users/lollopanta/Projects/Mneno-Bench/data/locomo/raw/locomo10.json` is absent here. Upstream revision and checksum unavailable. |
| Evaluated questions | Projection claims 1,986 cases; number with nonempty evidence and denominator for the mean are not recorded. |
| Git revision | Not retained. Bench version 0.6.0 is not a commit identity. Current checkout must not be attributed to the run. |
| Mneno version | Recorded 0.4.0; wheel hash, Core revision and environment lock absent. Keyword ran as a companion baseline. |
| Retrieval/top-k | Keyword lexical overlap baseline; Mneno reranked with NIM. Mean supplied-dialog count 5 suggests k=5, also current default; exact historical CLI k is not persisted in config. |
| Token budget | No explicit LOCOMO token budget recorded or passed by current runner. SDK defaults unknown. Full Context is unbounded. |
| Provider/model | `nvidia_nim/nv-rerank-qa-mistral-4b:1`, endpoint above; requested identity, no resolved deployment revision. Keyword has no model. Judge not requested. |
| Cache | Per-conversation LRU, capacity 4,096, prefix 50; recorded 347 hits, 3,166 misses/API calls, 158,300 documents. 815 cases resumed, so invocation counters are not full-run totals. |
| Failure/skip counts | Systems say completed; error lists empty. Per-case execution counts cannot be independently verified. Failure projection records 2,195 diagnostic records: Keyword 1,269, Mneno 914, Full Context 12. These are not execution failures/skips. |
| Metric | Current implementation: macro mean of available per-question set evidence recalls, using included IDs if nonempty, else search IDs. Historical executable revision unavailable. |
| Timestamp | Started 2026-06-23T20:07:26.046341Z; finished 2026-06-23T21:22:11.230647Z. Resumed case timestamps unavailable. |

Keyword and NIM summaries share a run ID and nominal dataset but their comparability cannot be proven from the projection. The unidentified deterministic Core run is incomparable with this pair as an experiment; its primary verification status remains unverified.

## LOCOMO normalization and confirmed defects

Existing `tests/test_locomo_runner.py` already covers `selected_memory_ids`, structured `included[*].memory_id` and `excluded[*].memory_id`, UUID mapping, and structured trace ID remapping end to end. Adapter conversion handles Pydantic, `to_dict`, mappings, iterables and public object attributes. `_normalize_ids` preserves unmapped UUIDs instead of deleting them; however unmatched UUIDs cannot match dataset evidence and no explicit normalization warning is emitted.

1. **Fixed in Phase A: empty legacy fields shadow valid structured IDs.** `_extract_ids` previously returned immediately for `retrieved_memory_ids: []` even when `selected_memory_ids` contained evidence. `_context_ids` similarly preferred empty legacy arrays over structured entries. Small fallback correction plus focused regression covers included/excluded and unknown UUID preservation. Nonempty field precedence is retained; candidate inventories are not unioned into selected results. Scope: LOCOMO extraction helpers and runner regression only; schema, ground truth, scoring formula, fixtures and historical artifacts unchanged. Scores on formerly misnormalized outputs may change legitimately.
2. **Context-selection ambiguity:** `metric_ids = included_ids or retrieved_ids` credits search evidence when a valid constructed context is empty. The main recall therefore mixes stages; `context_available` inferred from nonempty IDs also hides empty context. Requires an explicit versioned stage contract, not an undocumented score change.
3. **Mapping evidence is ephemeral:** bidirectional mapping is built during ingestion but not persisted in LOCOMO raw output. Reverse-map collisions can overwrite dataset identities if Core coalesces memories. Deep dive reconstructs UUIDs by exact formatted content; identical text can be ambiguous. Record stable mappings and detect collisions/unmapped IDs before diagnosing Core.
4. **Initialization errors lose cause:** `_initialize_mneno_conversation` catches every exception and returns `None`, losing ingestion/provider setup details. Failed question calls have `FAILED` and error text, but retrieval metrics computed from empty IDs become zero. Missing capabilities also yield empty-ID metrics. Completed empty retrieval must be separated from unavailable/failed execution in summaries.
5. **Methodology attribution:** common classifier labels retrieved-but-not-included evidence ranking failure without proof of the selection reason; broad budget-exhausted trace signals can affect other IDs. This is context-selection evidence, not conclusive ranking causality. Deep-dive classifier is more conservative but raw-selected/normalized-missing remains unknown, appropriately avoiding a Core accusation.
6. **Provenance gap:** content hash, Bench revision/dirty hash, Core build hash, effective endpoint/model configuration and explicit budgets are absent from durable identity.
7. **Build setup defect:** `package.json` contains self-dependency `mneno-bench: link:`; documented npm setup and Docker web `npm install` fail with `EUNSUPPORTEDPROTOCOL`. pnpm frozen-lockfile installation works. Not changed as unrelated to score validity.

## Diagnostic claim verification

`results/locomo/deep_dive/retrieval_deep_dive_latest.json` links run `locomo-20260623T200726Z-b0931749`, timestamp 2026-06-23T21:22:11.230647Z, seed 8, provider Mneno, 906 eligible retrieval failures and 100 sampled failures. Its saved inspections independently recount 224 expected evidence entries, 204 present in candidates (91.0714%), 43 selected (19.1964% micro recall), 51 ranking cases, 42 unknown, four session-bias and three lexical-mismatch cases. These percentages describe a deliberately balanced failure sample, not unbiased population rates or all-question recall. Thirty inspections explicitly flag `normalized_expected_selected=false` despite raw selection. That supports a normalization discrepancy warning, not a retrospective score correction without original artifacts. Root causes can be recounted from saved records; missing original traces/dataset prevent complete independent reclassification.

## Resume and artifact reliability

Atomic temporary-file replacement protects individual JSON writes; partial/corrupt case files are ignored and rerun; failed cases rerun by default. Completed cases are keyed by ID and skipped; merge restores dataset order. Tests cover these flows, explicit k fingerprint mismatch, and predict/evaluate phases.

Current fingerprint includes Bench version, SDK version, dataset path/size/mtime/counts/IDs, k, mode, workers, reranker settings/cache capacity. It catches many differences but same-size content changes with restored mtime evade it; moving identical data invalidates it. Same-version Core or Bench edits evade it. Effective environment endpoint/judge config file content are missing. Evaluation fingerprint hashes judge config **path**, not its content or resolved environment values. Worker count is identity-sensitive, while external retry/rate policy is excluded. Predictions can be evaluated separately, but judge failure/skip is not part of `case_state`, so checkpoints lack a reliable judge-phase completion contract. Conversation workers create their checkpoint store without `evaluation_fingerprint`, whereas full llm_judge resume requires that fingerprint; ordinary fully judged checkpoints can therefore be rejected and rerun unnecessarily. Evaluate-only rewrites do carry the fingerprint. A baseline-completed/Mneno-skipped case is “completed”. Corrupt or absent manifest permits case loading; duplicate case IDs overwrite in load order; envelope identity/index is not cross-checked against the result. No directory lock prevents simultaneous writers.

Clients are rebuilt and conversations reingested when outstanding questions remain; resumed questions do not replay their reranker cache history. Resumed latency and request totals therefore differ from uninterrupted runs. Run counters sum new work only and are not a ledger of resumed segments. Final latest JSON and multiple projections are individually atomic, not a single transaction; a crash during reporting can leave mismatched run IDs. Immutable run artifacts plus validated projection links are needed. Existing saved files were preserved.

## Internal independence and dashboard

Context Rot v1: 48 Git-tracked memories, 24 cases, eight categories, explicit expected/forbidden IDs and deterministic fixtures/scoring. Git history records introduction in `3759e7b` and execution metadata changes in `69dc909`; suite name/version does not hash fixtures. Regression and product evaluation share the same cases; no held-out split exists. Whether Core was tuned against them cannot be established without Core-team history. Keep them regression evidence and LOCOMO external evidence; do not claim generalization from this suite alone. SDK effects and timings are not guaranteed deterministic merely because fixtures are. Current fixture hashes: cases SHA-256 `89a7dbaf95943a43b4dfe9cc47de196c56abb140ba4a7a505c0fc2c021474969`; memories SHA-256 `e17645c8eec413f66d065154d99caba4ac7ce8cd373f170f9929f3b925b1faf3`.

Dashboard aggregate recall matches persisted summaries. Compact projections intentionally omit case payloads; failure projections preserve full summary but only a subset of details. Build-time imports can stay stale; counts must distinguish population and visible subset. Main metric fallback chooses Keyword if Mneno summary is absent; source/system identity needs to remain visible. Trace totals from empty projected case arrays cannot establish absence of tracing. Top-k, token budget, immutable dataset identity, effective provider metadata and metric denominators are incomplete in the UI/schema. Current labels describe evidence as “available official evidence IDs” although malformed references stay in the denominator. No UI redesign was made; prioritize validated artifacts and additive provenance before display work.

## Verification and limitations

See the check record appended below. SDK behavior is assessed through source and fake-adapter regressions; no live Core, NIM endpoint, Docker runtime or historical replay was tested. Dataset and originals are absent. Model availability was not probed and requested NIM identity is not treated as an availability guarantee. Phase B is specified, not implemented.

### Check record

- Python 3.11.17 isolated environment, requirements installed excluding optional Mneno; no Core wheel installed. System Python 3.9.6 was unsuitable and was not used for repository validation. Key installed versions: Pydantic 2.14.0, pytest 8.4.2, Ruff 0.17.0, mypy 1.20.2, LiteLLM 1.104.2. This is a fresh dependency resolution, not historical environment reproduction.
- `PYTHONPATH=. /tmp/mneno-bench-phase-a-py311/bin/pytest`: **128 passed**. After a local variable rename to resolve mypy's no-redef diagnostic, reran the affected runner tests: **18 passed**.
- `/tmp/mneno-bench-phase-a-py311/bin/mypy benchmarks --ignore-missing-imports`: **passed**, 45 source files.
- `/tmp/mneno-bench-phase-a-py311/bin/ruff check benchmarks tests`: **failed**, 71 diagnostics. Comparing original HEAD and edited files through the same Ruff configuration: runner 16 before/after, runner tests two before/after, no new diagnostics. No broad unrelated lint cleanup performed.
- Node 24.21.0; `npm ci --ignore-scripts`: **failed**, existing unsupported `link:` dependency. `pnpm install --frozen-lockfile --ignore-scripts` succeeded with pnpm 12.10.1; no tracked dependency/lockfile changes.
- `npm run build`: **passed**, TypeScript and Vite; existing >500 kB bundle warning (813.10 kB JavaScript).
- `npm run test:ui`: **20 passed** across five files.
- Saved deep-dive inspection recomputation: expected 224, candidate matched 204, selected matched 43; category counts 51/42/4/3; 30 normalization discrepancy flags. This does not validate missing underlying raw exports.

The checks were invoked separately so the existing lint failure did not prevent tests/typecheck/build. No expensive benchmark, live provider, Core source, fixture or saved result was modified.
