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
