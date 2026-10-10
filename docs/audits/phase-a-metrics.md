# Phase A metric definitions and measurement readiness

Read with [audit](phase-a-benchmark-audit.md). Source of truth: `locomo/metrics.py`, `locomo/run.py`, `locomo/deep_dive.py`, `common/root_cause.py`, `common/failures.py`, `mneno_suite/metrics.py` and `mneno_suite/scoring.py`. Definitions below describe current code unless explicitly marked proposed. No scoring formulas changed during this audit.

## LOCOMO quality and diagnostics

Let E be unique annotated evidence IDs, R selected search IDs normalized to dataset IDs, I included context IDs, C observable candidate IDs. Evidence references missing from the dataset remain in E when malformed evidence is allowed.

| Metric | Numerator / denominator and procedure | Direction / limitations |
|---|---|---|
| Candidate coverage | Deep-dive sum of per-inspection unique E intersect C / sum of expected-evidence list lengths | Higher. Micro aggregate on sampled failures; duplicate expected entries could make denominator inconsistent with set numerator. Missing candidate inventory is not proof of candidate failure. |
| Raw retrieval recall | Deep-dive sum of E intersect selected candidate IDs / same expected-entry denominator | Higher. Saved sample: 43/224. All-question raw-search stage aggregate is not separately persisted. Proposed all-question metric uses R and versioned availability semantics. |
| Final evidence recall | Per question: size of E intersect S / size of E, where current S=I if nonempty, else R. Empty E returns null. Aggregate is arithmetic mean of available per-question ratios, rounded to six decimals. | Higher. Macro mean, not total evidence recovered / total evidence. No persisted contributing-question count. Empty context incorrectly falls back to R. |
| Context inclusion recall | Proposed distinct size of E intersect I / size of E, null for unavailable context or empty E; zero for available empty context | Higher. Not separately persisted now. Do not relabel existing mixed-stage metric as this metric. |
| Evidence precision | size of E intersect S / size of unique S; null for empty S | Higher. Missing ground truth can yield zero precision with a nonempty S. |
| Retrieval hit rate | 1 if E intersects S, else 0; null for empty E; macro mean | Higher. Does not measure completeness. |
| Ranking failure rate | Deep dive: number classified ranking_failure / number sampled eligible failures, multiplied by 100 | Lower. 51/100; requires expected scored candidates present but not selected after preceding rules. Common failure report's broader retrieved-not-included label is not identical. |
| Session-related failure rate | Deep dive: session_bias_failure inspections / sample size (4/100); common report: session_continuity_failure records / failure-record count when presenting shares | Lower. Different taxonomies/denominators; explicit session boost displacement needed for deep-dive causal claim. Multiple session affiliations use affiliation count for session distribution, not question count. |
| Budget-related exclusions | Current classifier: affected expected IDs with exclusion/budget signals; deep dive requires ID-linked authoritative context budget events | Lower. No general scalar exclusion rate. Proposed: expected budget-excluded IDs / expected IDs reaching context selection; also report affected questions / context-available questions. Null when traces unavailable. |
| Unknown failure rate | Deep-dive unknown inspections / sampled eligible failures (42/100); common reports unknown records / all diagnostic records | Lower with caution. Fewer unknowns is useful only with stronger evidence, not more speculative attribution. |
| Answer exact match | Literal prediction=ground truth, binary; macro mean of available scores | Higher. Optional deterministic answer mode; not official run accuracy. |
| Normalized exact match / containment | Exact normalized strings / normalized truth substring respectively; binary | Higher. Normalize lowercase, punctuation/comma removal, remove a/an/the/and, collapse whitespace. Containment returns zero for empty truth. |
| Token F1 | Counter intersection of Porter-stemmed normalized tokens, harmonic mean of matched/predicted and matched/truth | Higher. Both empty gives one; no overlap gives zero. |
| Diagnostic answer score | max(normalized exact match, containment, token F1) | Higher. Optimistic local diagnostic, not calibrated accuracy. |
| Released-category-compatible candidate F1 | category 1: mean best comma-separated prediction F1 for each comma-separated truth; 2/4: token F1; 3: token F1 against truth before first semicolon; 5: literal “no information available” or “not mentioned” substring rule | Higher. Null unsupported category or missing applicable truth. Scorer compatibility alone is not official methodology validation. |
| LLM judge score | Available parsed score per requested answer; aggregate available mean, model/provider/prompt version retained | Higher. Optional subjective evaluation of local extractive candidate; no official_score promotion. Missing configuration/credentials skips. |

Current `official_score` and official category placeholders remain null. Retrieval-only produces no answer accuracy. Judge uses `LLMClient.generate`; there is no implemented provider answer-generation path. Failures/skips currently can contribute zero retrieval values from empty-ID maps: report status-stratified denominators before using summaries for comparisons.

Diagnostic records can overlap categories, so failure-record count is neither failed-question count nor execution-failure count. `retrieval_failure` says final observed evidence is missing; it does not identify candidate generation as the cause. Classify separately: generation (indexed inventory + missing candidates), ranking (candidate + ranked-out decision), selection (selected + excluded reason), normalization (raw mapped ID lost), execution (failed call/setup). Preserve unknown when a stage lacks evidence.

## Context Rot definitions

All are deterministic ratios rounded to six decimals; `_ratio` clamps to [0,1] and returns zero for nonpositive denominator. Higher is better except forbidden error.

- Expected recall: expected IDs selected / expected IDs; empty expected set returns 1.
- Stale suppression: forbidden IDs avoided / forbidden IDs; empty forbidden set returns 1. Forbidden error is forbidden IDs selected / forbidden IDs; empty set returns 0.
- Context efficiency: estimated tokens in selected-and-expected memories / estimated tokens in selected memories. Token estimates use regex word/punctuation pieces multiplied by 1.15, rounded, at least one for nonempty text. This is an estimate, not tokenizer or billing usage.
- Lifecycle alignment: active expected IDs selected + inactive forbidden IDs avoided, divided by active expected + inactive forbidden IDs; empty denominator returns 1. Inactive states: archived, expired, rejected, stale, superseded.
- Session continuity: current-session expected selected + other-session forbidden avoided, divided by those two groups; no current session or empty groups returns 1.
- Compaction retention: expected memories of importance >=0.8 retained / such important expected memories; empty important set returns 1. Preview is not a measured destructive compaction/reload test.
- Explainability coverage: event/decision/explanation counts plus inclusion/exclusion reasons and conflict/hierarchy/session events divided by max(unique retrieved count,1), capped at 1. It counts evidence volume, not unique memory decisions proven explained. Runner gates unavailable capabilities to null; helper alone returns zero without traces. Empty/miscellaneous events can inflate the ratio.
- Context Rot Score: available weighted terms / available weights: recall .25, suppression .20, inverse forbidden error .15, efficiency .15, lifecycle .10, session .10, explainability .05. Compaction is separate. Missing terms change effective denominator, so scores with different capability masks are not directly comparable. Retain published regression score but never use it as the Phase B quality/resource/reliability composite.

## Efficiency instrumentation inventory

| Dimension | Current collection / reliability | Missing procedure | Complexity |
|---|---|---|---|
| Retrieval p50/p95 | Baseline perf_counter milliseconds per call; SDK metric latency when provided, else fabricated 0 in runner | External wall timer, timing boundaries, null missing SDK values, sample counts and quantiles; serial runs | Small |
| Context construction p50/p95 | Some trace durations; no dedicated complete call distribution | Time build_context separately from evaluate_context/search; record trace vs wall duration | Small |
| Ingestion total/throughput | Memory-load counts and traces in suite; no reliable timed total | Time successful insertion interval; successes/second plus failed insertions | Small |
| Peak RAM | Not collected | OS peak RSS for runner and child processes; distinguish cumulative child peaks from simultaneous tree peak | Medium |
| CPU | Not collected | User/system CPU seconds, process tree and elapsed time; utilization derived and labeled | Medium |
| Storage/index size | Not collected | Fixed persistent DB location, files/sidecars, checkpoint WAL before size snapshot; separate index/data size if SDK exposes it | Medium, Core dependency |
| Recall per 1,000 context tokens | Context token estimates per case exist; no ratio | Report 1,000*sum per-question final recalls / sum context token estimates on same eligible completed cases, with both sums and count; null zero denominator. Also show recall and tokens separately | Small |
| Model input/output tokens | Completion returns only string; usage discarded | Preserve response usage and requested/resolved model without provider logic in runners | Medium |
| Provider requests/errors/retries | Thread-shared attempts, successes, terminal failures, 429s, retries, Retry-After seconds; reranker logical requests/hits/docs | Per-call status/latency ledger and segment totals. Counters increment before response validation, so request success != valid output | Medium |
| Estimated API cost | Not collected | Dated published tariff + usage + currency; include rerank billing unit if applicable; unavailable if usage/rate absent | Small after usage capture |
| Reliability | Per-system status/error/skip, case checkpoint states | Unique requested/completed/failed/skipped question counts; initialization causes, retry outcome and judge phase availability | Small–medium |
| Cold/warm start | Not collected | Time open/load/reopen; separate persistent index construction from retrieval warming | Medium, Core dependency |

Never invent costs for local models. RAM/CPU/storage are measured quantities; context tokens are current deterministic estimates; costs would be tariff estimates. Historical parallel latency is explicitly marked incomparable. Random baseline timing starts after shuffle, so its latency excludes most work and cannot support equal-boundary efficiency claims.

## Fairness requirements

Freeze raw dataset hash, loader and formatting revision, ordered questions, malformed-annotation policy, metric implementation, per-system availability masks, k, candidate cap, explicit token budget/token counting, worker count, ingestion/session order, cache policy and seeds. Preserve unbounded Full Context as an explicitly separate quality/cost reference. Report macro and micro quantities separately, with numerator, denominator, unavailable reasons and status counts. Provider costs and retries belong to operational reports, not retrieval ground truth. Dataset annotations must remain unchanged.
