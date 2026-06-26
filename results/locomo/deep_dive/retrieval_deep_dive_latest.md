# Retrieval Deep Dive

## Summary

- Benchmark: **locomo**
- Provider: **mneno**
- Run ID: `locomo-20260623T200726Z-b0931749`
- Total retrieval failures: **906**
- Sampled failures: **100**
- Retrieval recall in sample: **19.2%**
- Candidate coverage in sample: **91.1%**

## Top Root Causes

| Root cause | Count | Percentage |
| --- | ---: | ---: |
| ranking_failure | 51 | 51.0% |
| unknown | 42 | 42.0% |
| session_bias_failure | 4 | 4.0% |
| lexical_mismatch | 3 | 3.0% |

## Statistics

### By Conversation

| Conversation | Count | Percentage |
| --- | ---: | ---: |
| conv-26 | 10 | 10.0% |
| conv-30 | 10 | 10.0% |
| conv-41 | 10 | 10.0% |
| conv-42 | 10 | 10.0% |
| conv-43 | 10 | 10.0% |
| conv-44 | 10 | 10.0% |
| conv-47 | 10 | 10.0% |
| conv-48 | 10 | 10.0% |
| conv-49 | 10 | 10.0% |
| conv-50 | 10 | 10.0% |

### By Question Type

| Question type | Count | Percentage |
| --- | ---: | ---: |
| adversarial | 20 | 20.0% |
| factual_recall | 20 | 20.0% |
| multi_hop_reasoning | 20 | 20.0% |
| open_domain | 20 | 20.0% |
| temporal_reasoning | 20 | 20.0% |

### By Session

| Session | Count | Percentage |
| --- | ---: | ---: |
| session_1 | 8 | 4.3% |
| session_27 | 8 | 4.3% |
| session_4 | 8 | 4.3% |
| session_13 | 7 | 3.7% |
| session_2 | 7 | 3.7% |
| session_20 | 7 | 3.7% |
| session_21 | 7 | 3.7% |
| session_7 | 7 | 3.7% |
| session_10 | 6 | 3.2% |
| session_11 | 6 | 3.2% |
| session_12 | 6 | 3.2% |
| session_14 | 6 | 3.2% |
| session_15 | 6 | 3.2% |
| session_16 | 6 | 3.2% |
| session_18 | 6 | 3.2% |
| session_19 | 6 | 3.2% |
| session_23 | 6 | 3.2% |
| session_25 | 6 | 3.2% |
| session_28 | 6 | 3.2% |
| session_3 | 6 | 3.2% |
| session_5 | 6 | 3.2% |
| session_6 | 6 | 3.2% |
| session_8 | 6 | 3.2% |
| session_17 | 5 | 2.7% |
| session_22 | 5 | 2.7% |
| session_24 | 5 | 2.7% |
| session_26 | 5 | 2.7% |
| session_29 | 5 | 2.7% |
| session_9 | 5 | 2.7% |
| session_30 | 4 | 2.1% |
| session_31 | 4 | 2.1% |
| session_32 | 1 | 0.5% |

## Top Failure Cases

### 1. conv-26:qa-0003

- Question: What fields would Caroline be likely to pursue in her educaton?
- Expected evidence: `D1:9, D1:11`
- Retrieved evidence: `D9:13, D7:3, D17:26, D19:9, D15:24`
- Root cause: **ranking_failure**
- Trace IDs: `4167c753-6609-46b8-ac7b-c29cb0750859, 05b8b369-20b4-414c-be05-826c3ea1dfdb, 5dbc3849-9d44-48db-a3b9-160a07469164`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 2. conv-30:qa-0037

- Question: When did Jon and Gina decide to collaborate to create dance content?
- Expected evidence: `D18:18`
- Retrieved evidence: `D9:1, D9:5, D18:13, D18:14, D11:11`
- Root cause: **session_bias_failure**
- Trace IDs: `0dfb3f4d-c8f6-4abc-90be-1e3ba6914008, e6011a38-9da5-4d97-bfc5-5bf7db19367e, 1388526c-44af-424e-be20-b8af3d978fc3`
- Explanation: An explicit active-session boost displaced expected evidence from the final result set.

### 3. conv-47:qa-0181

- Question: What does James feel about starting the journey as a programming mentor for game developers?
- Expected evidence: `D26:5`
- Retrieved evidence: `D26:4, D26:3, D9:22, D26:1, D26:2`
- Root cause: **lexical_mismatch**
- Trace IDs: `6e415f66-4701-42f9-aff1-f677f94de1f1, 0823f10c-abc7-4ded-bf48-8d483f9209a1, ae53a154-49c9-46c8-b9ef-17e3011b5ea4`
- Explanation: Expected evidence was a candidate, received zero lexical relevance, and semantic retrieval was explicitly skipped.

### 4. conv-41:qa-0017

- Question: When did John get his degree?
- Expected evidence: `D9:2`
- Retrieved evidence: `D9:3, D9:6, D9:4, D9:11, D19:7`
- Root cause: **unknown**
- Trace IDs: `db7e9982-4308-420f-9e91-d43af32f5182, 843e44ed-7abe-40ad-81a7-9aa3019f6e30, 90de7f89-8903-42f3-8ad1-19c0c4488dd5`
- Explanation: Expected evidence was absent from the observable candidate set, but the artifacts do not distinguish indexing, lifecycle filtering, or candidate-generation causes.

### 5. conv-42:qa-0067

- Question: What alternative career might Nate consider after gaming?
- Expected evidence: `D5:8, D19:3, D25:19, D28:25`
- Retrieved evidence: `D9:9, D28:16, D28:13, D19:1, D10:4`
- Root cause: **ranking_failure**
- Trace IDs: `0c7cf1b6-1505-435c-8648-c0285aec674b, ebd7f455-d42e-4c50-9151-4453b52564d0, 8856da2d-0410-4ea5-8b61-91737c93545c`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 6. conv-48:qa-0234

- Question: What did Jolene do with their mom's old friends?
- Expected evidence: `D28:7`
- Retrieved evidence: `D28:4, D22:1, D4:35, D12:1, D4:41`
- Root cause: **lexical_mismatch**
- Trace IDs: `87e1fdb6-b17b-4924-8112-612309e23158, 67dd900b-cefa-4c5d-b847-e19439b12baf, f31a3a47-3ac4-482a-8aa9-78fe956adb07`
- Explanation: Expected evidence was a candidate, received zero lexical relevance, and semantic retrieval was explicitly skipped.

### 7. conv-49:qa-0039

- Question: What role does nature and the outdoors play in Evan and Sam's mental well-being?
- Expected evidence: `D22:1, D22:2, D9:10, D9:11`
- Retrieved evidence: `D9:12, D9:8, D25:13, D8:22, D14:8`
- Root cause: **session_bias_failure**
- Trace IDs: `a70fe1d5-e96f-4a4a-84d8-538408c91b32, 146b2ae1-71f0-46e5-a380-ade66957339c, 1c303774-0810-439c-a306-95519c0caf81`
- Explanation: An explicit active-session boost displaced expected evidence from the final result set.

### 8. conv-43:qa-0042

- Question: What kind of fiction stories does Tim write?
- Expected evidence: `D15:3, D16:1`
- Retrieved evidence: `D6:6, D19:17, D15:3, D4:5, D27:35`
- Root cause: **unknown**
- Trace IDs: `f4facf58-b4ea-47db-b8b5-0353b5fe5a71, a1c85cba-96a8-4001-8982-dfe28db0c9f4, 1b5fcd77-fbe8-424f-993f-9dd45a0f770c`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 9. conv-44:qa-0017

- Question: When is Andrew going to go hiking with Audrey?
- Expected evidence: `D11:7`
- Retrieved evidence: `D12:4, D11:25, D4:2, D23:26, D14:1`
- Root cause: **ranking_failure**
- Trace IDs: `d52c4ffe-6f85-4e13-b923-0ba48c19d9c3, 0ffbd174-4e12-418e-abd8-bd9e38218893, 38950bfc-bf95-45b0-a199-2f0e545202fd`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 10. conv-50:qa-0047

- Question: What is Dave's favorite activity?
- Expected evidence: `D21:4, D22:7, D19:7`
- Retrieved evidence: `D30:1, D28:31, D25:15, D21:4, D13:4`
- Root cause: **unknown**
- Trace IDs: `72f84f0f-5aeb-439a-9ba5-9edb3c17ea5e, 24f4ea9e-8230-454a-9247-f5b69cd146c9, c16b60ef-3685-437c-9914-80a13ea1e694`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 11. conv-30:qa-0101

- Question: How does Gina use the clipboard with a notepad attached to it?
- Expected evidence: `D13:11`
- Retrieved evidence: `D9:14, D18:15, D17:14, D16:1, D12:1`
- Root cause: **lexical_mismatch**
- Trace IDs: `f585ea97-1306-462b-9f9d-d8ee3d2997b4, 8bf352b7-f10b-4831-b41b-0ea1c1078e5e, 6fdc9b43-9f7d-40d4-8988-8b0f40e4e3a0`
- Explanation: Expected evidence was a candidate, received zero lexical relevance, and semantic retrieval was explicitly skipped.

### 12. conv-47:qa-0023

- Question: Who or which organizations have been the beneficiaries of John's charity tournaments?
- Expected evidence: `D10:10, D10:12, D29:1`
- Retrieved evidence: `D9:13, D10:4, D11:1, D12:5, D27:1`
- Root cause: **session_bias_failure**
- Trace IDs: `24035cf7-b39d-451d-96b9-54022f9b8189, 6715acc9-2471-4696-b315-42c88a3bdbd6, 0e5ca38c-e0a7-448d-964a-58aa77d84e16`
- Explanation: An explicit active-session boost displaced expected evidence from the final result set.

### 13. conv-26:qa-0023

- Question: Would Caroline likely have Dr. Seuss books on her bookshelf?
- Expected evidence: `D6:9`
- Retrieved evidence: `D7:10, D18:23, D17:10, D7:11, D7:9`
- Root cause: **ranking_failure**
- Trace IDs: `465c928b-9c5b-4a9d-aa38-872c60fdda6a, 61d01f2e-ba51-4893-8ed3-245acc47dd6b, 8b2e4cd4-6620-4f5f-a571-39a4b0f251e4`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 14. conv-41:qa-0057

- Question: When did John participate in a 5K charity run?
- Expected evidence: `D29:2, D29:4`
- Retrieved evidence: `D29:4, D10:10, D29:9, D29:5, D6:1`
- Root cause: **unknown**
- Trace IDs: `b9550096-bb16-4a48-9a42-c44bd3b15ca4, ebb2abf2-1071-47bb-b8b8-40ce8c86e36f, 51d906ae-9c50-4651-a394-d62d85c8cad5`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 15. conv-47:qa-0190

- Question: What is the name of James's cousin's dog?
- Expected evidence: `D31:22`
- Retrieved evidence: `D31:20, D21:3, D31:21, D9:12, D14:13`
- Root cause: **session_bias_failure**
- Trace IDs: `334b9fc0-fdc8-42c1-80ab-09591810c6d0, ecd8d209-7ff3-449c-bf03-11b41c4ddfd6, d8d4ebc1-ceb6-48ec-91a0-023a489fb044`
- Explanation: An explicit active-session boost displaced expected evidence from the final result set.

### 16. conv-42:qa-0110

- Question: What was Joanna's audition for?
- Expected evidence: `D6:2`
- Retrieved evidence: `D9:7, D27:2, D21:5, D2:7, D27:7`
- Root cause: **ranking_failure**
- Trace IDs: `2d9201f8-7930-4029-a2c7-9dd262419796, 354d6082-4583-40e9-80ae-14d1990273a7, 34a5c2c0-8156-401d-baf2-4bef58643873`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 17. conv-43:qa-0067

- Question: What is a Star Wars book that Tim might enjoy?
- Expected evidence: `D27:19, D27:21`
- Retrieved evidence: `D27:21, D22:9, D19:15, D4:5, D3:30`
- Root cause: **unknown**
- Trace IDs: `9300fef3-8a3d-4618-a1d8-72886083d342, 40c680b7-f1fe-490d-a874-a11b848528be, 81000058-865c-4d70-bd0f-276b23d73cdc`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 18. conv-44:qa-0025

- Question: Did Audrey and Andrew grow up with a pet dog?
- Expected evidence: `D2:16, D13:10`
- Retrieved evidence: `D6:2, D24:2, D22:1, D20:2, D2:1`
- Root cause: **ranking_failure**
- Trace IDs: `3a2a60d3-2a01-4673-929d-f0f90e14e696, b27a2bdc-2bb8-4514-9418-b499bc6895f4, bb9c24a6-9205-497b-8561-06a5bb855472`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 19. conv-48:qa-0078

- Question: Where did Jolene and her partner find a cool diving spot?
- Expected evidence: `D27:1, D29:4`
- Retrieved evidence: `D30:2, D23:1, D29:5, D29:4, D4:31`
- Root cause: **unknown**
- Trace IDs: `de90b9de-c341-4043-ab65-55f2386f45d2, 4b45ee5a-8288-42e3-8649-dc278dbd9a6c, 5009d670-75d4-4e4a-b212-41c9fcc0503c`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 20. conv-49:qa-0033

- Question: What recurring frustration does Evan experience?
- Expected evidence: `D6:13, D21:20`
- Retrieved evidence: `D14:2, D9:2, D9:3, D14:1, D18:3`
- Root cause: **ranking_failure**
- Trace IDs: `68a6e9cc-a20c-464f-92fd-e03bca4d9f1e, d97a9416-5a56-492f-a954-e352deb32024, 767880f3-a26c-483c-a565-e051969ce4de`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 21. conv-50:qa-0067

- Question: Do all of Dave's car restoration projects go smoothly?
- Expected evidence: `D27:10, D13:7, D25:17, D20:1`
- Retrieved evidence: `D14:11, D25:17, D6:3, D20:2, D20:1`
- Root cause: **unknown**
- Trace IDs: `b8c305d2-7822-4d27-b16e-f9c1c6f21ab6, e1713dfd-7ae5-48cd-b275-9d3f24719f7a, 876f2887-4b52-48f5-adce-33510a0defca`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 22. conv-26:qa-0043

- Question: Would Melanie be more interested in going to a national park or a theme park?
- Expected evidence: `D10:12, D10:14`
- Retrieved evidence: `D17:26, D18:23, D18:22, D18:19, D18:5`
- Root cause: **ranking_failure**
- Trace IDs: `d541fd35-1535-4911-ba1c-81a1c8cbfb23, ff972723-b1e6-44e6-bb91-607f4838ca2f, efa3f7f6-c060-47d0-abb4-50c59b2fec5a`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 23. conv-30:qa-0024

- Question: How did Gina promote her clothes store?
- Expected evidence: `D5:5, D16:3, D8:4, D13:4`
- Retrieved evidence: `D2:1, D5:5, D8:12, D10:2, D8:4`
- Root cause: **unknown**
- Trace IDs: `f538362b-d6d4-4705-ad7a-ede1ca8221a9, 464c5382-eb54-4f8c-99dc-aad83f225482, b31f6370-8b73-4706-8e1f-5a58b19f880d`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

### 24. conv-41:qa-0046

- Question: Would John be open to moving to another country?
- Expected evidence: `D24:3, D7:2`
- Retrieved evidence: `D9:6, D9:7, D15:6, D8:18, D13:32`
- Root cause: **ranking_failure**
- Trace IDs: `8e407a54-8457-4d17-891b-328ebb0a5b71, f13c08b6-fc0f-469b-a7bc-6f0d98e58aeb, 57c8b565-fb0a-4707-a148-e61f8e2df819`
- Explanation: Expected evidence appeared in the scored candidate set but was not selected.

### 25. conv-42:qa-0012

- Question: What is Joanna allergic to?
- Expected evidence: `D4:4, D5:11, D2:23`
- Retrieved evidence: `D2:15, D5:11, D28:28, D24:6, D2:23`
- Root cause: **unknown**
- Trace IDs: `0b699886-a130-4ec6-a894-bce30a48cf23, c443435f-052b-4482-a4c0-4fa75e258f0c, 4b989fec-55be-4201-82fa-a2274972d050`
- Explanation: Raw artifacts show expected evidence selected or included, but the normalized benchmark result does not preserve that evidence ID. This is not evidence of a Core retrieval miss.

## Improvement Opportunities

### Candidate ranking

- Evidence: 51/100 sampled failures (51.0%); example_cases=conv-44:qa-0058,conv-43:qa-0060,conv-47:qa-0162,conv-48:qa-0056,conv-30:qa-0041
- Expected impact: Improve ordering when expected evidence is present in the candidate pool but below the selection cutoff.
- Confidence: **high**
- Suggested Core area: Retrieval ranking

### Session-aware ranking

- Evidence: 4/100 sampled failures (4.0%); example_cases=conv-49:qa-0039,conv-30:qa-0037,conv-47:qa-0023,conv-47:qa-0190
- Expected impact: Revisit how active-session boosts interact with cross-session factual and temporal evidence.
- Confidence: **high**
- Suggested Core area: Retrieval ranking and session weighting

### Lexical matching coverage

- Evidence: 3/100 sampled failures (3.0%); example_cases=conv-47:qa-0181,conv-30:qa-0101,conv-48:qa-0234
- Expected impact: Reduce misses where candidate evidence receives no lexical relevance and no semantic stage is available.
- Confidence: **high**
- Suggested Core area: Query matching and candidate scoring

### Memory identity and trace observability

- Evidence: 42/100 sampled failures remain unknown; Unknown is retained where artifacts cannot distinguish indexing, filtering, and candidate generation.
- Expected impact: Make future retrieval failures classifiable without changing retrieval behavior.
- Confidence: **high**
- Suggested Core area: Trace exports and memory identity metadata

### Candidate coverage measurement

- Evidence: sample_candidate_coverage=0.9107
- Expected impact: Track whether future Core changes improve recall before ranking and context selection.
- Confidence: **high**
- Suggested Core area: Retrieval diagnostics

## Recommended Core Priorities

1. Candidate ranking
2. Session-aware ranking
3. Lexical matching coverage
4. Memory identity and trace observability
5. Candidate coverage measurement
