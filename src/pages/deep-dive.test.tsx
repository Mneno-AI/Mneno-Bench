import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { RetrievalDeepDive } from "../lib/schema";
import { DeepDivePage, filterDeepDiveFailures } from "./deep-dive";

const report: RetrievalDeepDive = {
  benchmark: "locomo",
  createdAt: "2026-06-09T00:00:00Z",
  provider: "mneno",
  totalFailures: 1982,
  sampledFailures: [
    {
      id: "failure-1",
      caseId: "conv-26:qa-0001",
      provider: "mneno",
      conversationId: "conv-26",
      questionType: "temporal_reasoning",
      category: "temporal_reasoning",
      sessions: ["session_1"],
      question: "When did Caroline go?",
      normalizedQuestion: "when did caroline go",
      expectedEvidence: [
        {
          evidenceId: "D1:3",
          text: "Caroline went yesterday.",
          sessionId: "session_1",
          coreMemoryId: "core-1",
        },
      ],
      retrievedCandidates: [
        {
          id: "D9:1",
          coreMemoryId: "core-2",
          text: "Other evidence.",
          score: 0.7,
          rank: 1,
          selected: true,
          reasons: ["Matched query term: caroline"],
        },
      ],
      includedIds: ["D9:1"],
      excludedExpectedIds: ["D1:3"],
      traceIds: ["trace-1"],
      rootCause: "ranking_failure",
      explanation: "Expected evidence was scored but not selected.",
      classificationEvidence: ["candidate_ids=core-1"],
    },
  ],
  rootCauses: { ranking_failure: { count: 1, percentage: 100 } },
  statistics: {
    sampleSize: 1,
    expectedEvidenceCount: 1,
    retrievedExpectedCount: 0,
    candidateExpectedCount: 1,
    retrievalRecall: 0,
    candidateCoverage: 1,
    failuresByRootCause: { ranking_failure: { count: 1, percentage: 100 } },
    failuresByConversation: { "conv-26": { count: 1, percentage: 100 } },
    failuresByQuestionType: { temporal_reasoning: { count: 1, percentage: 100 } },
    failuresBySession: { session_1: { count: 1, percentage: 100 } },
    failuresByCategory: { temporal_reasoning: { count: 1, percentage: 100 } },
  },
  recommendations: [
    {
      title: "Candidate ranking",
      evidence: ["1/1 sampled failures"],
      expectedImpact: "Improve ordering when evidence is present.",
      confidence: "high",
      suggestedCoreArea: "Retrieval ranking",
    },
  ],
  topFailureCases: [],
  recommendedCorePriorities: ["Candidate ranking"],
  runId: "run-1",
  deterministicSeed: 8,
  metadata: {},
};

describe("Deep Dive page", () => {
  it("renders statistics, distribution, samples, and opportunities", () => {
    const html = renderToStaticMarkup(<DeepDivePage reports={[report]} />);

    expect(html).toContain("Retrieval Deep Dive");
    expect(html).toContain("Root cause distribution");
    expect(html).toContain("Ranking Failure");
    expect(html).toContain("conv-26:qa-0001");
    expect(html).toContain("D1:3");
    expect(html).toContain("Candidate ranking");
    expect(html).toContain("Candidate coverage");
  });

  it("renders the missing report state", () => {
    const html = renderToStaticMarkup(<DeepDivePage reports={[]} />);
    expect(html).toContain("No retrieval deep dive found");
  });

  it("filters by provider and root cause", () => {
    expect(
      filterDeepDiveFailures(report.sampledFailures, "mneno", "ranking_failure"),
    ).toHaveLength(1);
    expect(
      filterDeepDiveFailures(report.sampledFailures, "keyword_baseline", "all"),
    ).toHaveLength(0);
  });
});
