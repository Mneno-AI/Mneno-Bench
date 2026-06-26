# LOCOMO Dataset

Mneno Bench does not redistribute LOCOMO data. Obtain the dataset from the
official Snap Research repository:

https://github.com/snap-research/locomo

Download `data/locomo10.json` from that repository and place it at:

```text
data/locomo/raw/locomo10.json
```

The loader also accepts `data/locomo/processed/locomo10.json` and explicit JSON
paths. Raw and processed dataset files are ignored by Git.

## Expected Official Format

The official root is a JSON list. Each item contains:

- `sample_id`: stable conversation identifier.
- `conversation`: `speaker_a`, `speaker_b`, chronological `session_<n>` arrays,
  and corresponding `session_<n>_date_time` values.
- dialog turns with `speaker`, `dia_id`, `text`, and optional image metadata.
- `qa`: questions with `question`, `answer`, numeric `category`, and optional
  `evidence` dialog IDs.
- optional `observation`, `session_summary`, and `event_summary` annotations.

Mneno Bench preserves these optional annotations as metadata. It does not alter
the source dataset. Duplicate IDs, malformed records, and evidence references to
missing dialog IDs fail with explicit validation errors.

The repository and dashboard continue to work when this file is absent. Running
LOCOMO without it writes a `dataset_missing` result and Markdown report.

Validation is intentionally strict. If an upstream release contains malformed
or unresolved evidence references, the loader reports them explicitly rather
than silently rewriting or dropping benchmark annotations. Corrections should be
made by the dataset publisher and retained with clear provenance.

To run diagnostics against an upstream copy that contains unresolved evidence
references, opt into permissive loading explicitly:

```bash
python -m benchmarks.locomo.run --mode retrieval_only --k 5 \
  --allow-malformed-evidence
```

The run artifact records each unresolved reference under validation warnings.
Recoverable formatting variants, such as space-separated IDs and zero-padded
turn numbers, are normalized while their original values remain in question
metadata as `raw_evidence`.
