import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { BenchmarkRun, LocomoSummary } from "../lib/schema";
import { LocomoPage } from "./locomo";

function makeRun(locomo: LocomoSummary): BenchmarkRun {
  return {
    id: "locomo-test",
    suite: "locomo",
    startedAt: "2026-06-08T12:00:00Z",
    status: locomo.datasetStatus === "dataset_missing" ? "dataset_missing" : "completed",
    systems: ["keyword_baseline", "full_context_baseline", "mneno"],
    cases: locomo.questionCount,
    source: "external",
    mnenoStatus: "skipped",
    metrics: [],
    trace: {
      operations: 0,
      events: 0,
      decisions: 0,
      durationMs: null,
      retrieved: 0,
      selected: 0,
      suppressed: 0,
      conflictsResolved: 0,
      explanations: 0,
    },
    benchmarkVersion: "0.5.0",
    mnenoVersion: null,
    locomo,
  };
}

const missing: LocomoSummary = {
  datasetStatus: "dataset_missing",
  executionStatus: "skipped",
  evaluationMode: "retrieval_only",
  conversationCount: 0,
  messageCount: 0,
  questionCount: 0,
  categories: {},
  systems: [
    {
      name: "mneno",
      status: "skipped",
      metrics: {},
      scoreLabels: {
        officialScore: null,
        diagnosticScore: null,
        retrievalDiagnostic: null,
        judgeScore: null,
      },
      traceIds: [],
      judge: {
        status: "skipped",
        model: null,
        provider: null,
        promptVersion: null,
      },
      skipReason: "LOCOMO dataset is not installed.",
      errors: [],
    },
  ],
  malformedEvidenceWarningCount: 0,
  reportPath: "results/locomo/locomo_latest.md",
  traceDirectory: "results/locomo/traces",
  rawOutputDirectory: "results/locomo/raw",
  judgePromptDirectory: "results/locomo/judge/prompts",
  judgeResponseDirectory: "results/locomo/judge/responses",
  judgeModel: null,
  judgeProvider: null,
  promptVersion: "locomo_judge_v1",
  officialScoringStatus: "not_implemented",
  officialScoringReason: "Official scoring is pending.",
};

describe("LOCOMO page", () => {
  it("shows the dataset missing state", () => {
    const html = renderToStaticMarkup(<LocomoPage run={makeRun(missing)} />);

    expect(html).toContain("Dataset missing");
    expect(html).toContain("data/locomo/raw/locomo10.json");
    expect(html).toContain("dataset_missing");
  });

  it("shows a successful run without claiming official answer scores", () => {
    const html = renderToStaticMarkup(
      <LocomoPage
        run={makeRun({
          ...missing,
          datasetStatus: "available",
          executionStatus: "completed",
          evaluationMode: "deterministic_answer",
          conversationCount: 10,
          messageCount: 3000,
          questionCount: 1986,
          categories: { factual_recall: 300, temporal_reasoning: 100 },
          systems: [
            {
              name: "keyword_baseline",
              status: "completed",
              metrics: { evidence_recall: 0.5, retrieved_dialog_count: 5 },
              scoreLabels: {
                officialScore: null,
                diagnosticScore: 1,
                retrievalDiagnostic: 0.5,
                judgeScore: null,
              },
              traceIds: [],
              judge: {
                status: "not_requested",
                model: null,
                provider: null,
                promptVersion: null,
              },
              skipReason: null,
              errors: [],
            },
            {
              name: "mneno",
              status: "skipped",
              metrics: {},
              scoreLabels: {
                officialScore: null,
                diagnosticScore: null,
                retrievalDiagnostic: null,
                judgeScore: null,
              },
              traceIds: [],
              judge: {
                status: "not_requested",
                model: null,
                provider: null,
                promptVersion: null,
              },
              skipReason: "Mneno is optional.",
              errors: [],
            },
          ],
        })}
      />,
    );

    expect(html).toContain("Latest LOCOMO run");
    expect(html).toContain("Evidence Recall");
    expect(html).toContain("50%");
    expect(html).toContain("deterministic answer");
    expect(html).toContain("1986");
  });

  it("shows llm judge skipped state", () => {
    const html = renderToStaticMarkup(
      <LocomoPage
        run={makeRun({
          ...missing,
          datasetStatus: "available",
          executionStatus: "completed",
          evaluationMode: "llm_judge",
          judgeModel: "gpt-test",
          judgeProvider: "openai",
          systems: [
            {
              ...missing.systems[0],
              name: "keyword_baseline",
              status: "completed",
              judge: {
                status: "skipped",
                model: "gpt-test",
                provider: "openai",
                promptVersion: "locomo_judge_v1",
              },
            },
          ],
        })}
      />,
    );

    expect(html).toContain("llm judge");
    expect(html).toContain("gpt-test");
    expect(html).toContain("Skipped");
  });
});
