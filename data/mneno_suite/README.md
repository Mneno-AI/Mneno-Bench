# Mneno Context Rot Suite v1 Dataset

This directory contains the deterministic, synthetic dataset for the flagship
Mneno Context Rot Suite. It is designed to test lifecycle, session, compaction,
budget, and explainability behavior without external data or model judges.

- `memories.jsonl`: 48 synthetic memory records across active, operational,
  superseded, stale, archived, and noisy states.
- `cases.jsonl`: 24 cases, with three cases in each of the eight suite
  categories.

Every referenced expected or forbidden memory ID is validated by the loader.
The records are development fixtures and must not be presented as public
benchmark results.

Memory records preserve stable dataset IDs and include `session_id`,
`sequence_index`, `memory_type`, `importance`, `tags`, lifecycle `status`, and
optional `layer`. The loader also supports `expected_status`, `expected_layer`,
`conflict_group`, `supersedes`, `stale`, and `noise`. During Core execution it
derives `metadata.created_order` from `sequence_index` and retains all original
metadata, including existing `supersedes`, `superseded_by`, and conflict links.
