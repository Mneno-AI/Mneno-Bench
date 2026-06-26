import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  filterFailuresByProvider,
  summaryForProvider,
} from "../lib/failure-filters";
import type { FailureReport } from "../lib/schema";
import { FailuresPage } from "./failures";

const report: FailureReport = {
  id: "run-failures",
  benchmark: "mneno_context_rot_suite_v1",
  runId: "run-1",
  createdAt: "2026-06-09T00:00:00Z",
  failures: [
    {
      id: "suite:case:mneno:retrieval_failure",
      benchmark: "mneno_context_rot_suite_v1",
      caseId: "case-budget",
      provider: "mneno",
      category: "retrieval_failure",
      severity: "high",
      query: "What changed?",
      expectedIds: ["expected"],
      retrievedIds: [],
      includedIds: [],
      excludedIds: [],
      forbiddenIds: [],
      traceIds: ["trace-1"],
      reason: "Expected evidence was missing.",
      evidence: ["missing_expected_ids=expected"],
      suggestedAction: "Inspect retrieval recall.",
      expectedBehavior: false,
      interpretation: "This failure should be investigated in Mneno Core.",
      metadata: {},
    },
  ],
  summary: {
    totalFailures: 1,
    byCategory: { retrieval_failure: 1 },
    byProvider: { mneno: 1 },
    bySeverity: { high: 1 },
    topSuggestedActions: ["Inspect retrieval recall."],
  },
  byProvider: {
    mneno: {
      totalFailures: 1,
      byCategory: { retrieval_failure: 1 },
      byProvider: { mneno: 1 },
      bySeverity: { high: 1 },
      topSuggestedActions: ["Inspect retrieval recall."],
    },
  },
  mnenoOnly: {
    totalFailures: 1,
    byCategory: { retrieval_failure: 1 },
    byProvider: { mneno: 1 },
    bySeverity: { high: 1 },
    topSuggestedActions: ["Inspect retrieval recall."],
  },
  baselineOnly: {
    totalFailures: 0,
    byCategory: {},
    byProvider: {},
    bySeverity: {},
    topSuggestedActions: [],
  },
  metadata: {},
};

describe("Failures page", () => {
  it("renders failure summary, category breakdown, table, and detail", () => {
    const html = renderToStaticMarkup(<FailuresPage reports={[report]} />);

    expect(html).toContain("Total failures");
    expect(html).toContain("Failure category breakdown");
    expect(html).toContain("Retrieval Failure");
    expect(html).toContain("case-budget");
    expect(html).toContain("trace-1");
    expect(html).toContain("Inspect retrieval recall");
    expect(html).toContain("Full Context");
    expect(html).toContain("Random");
    expect(html).toContain("This view combines Mneno and baseline comparison evidence");
  });

  it("handles an empty failure report", () => {
    const html = renderToStaticMarkup(
      <FailuresPage
        reports={[
          {
            ...report,
            failures: [],
            summary: {
              totalFailures: 0,
              byCategory: {},
              byProvider: {},
              bySeverity: {},
              topSuggestedActions: [],
            },
            byProvider: {},
            mnenoOnly: {
              totalFailures: 0,
              byCategory: {},
              byProvider: {},
              bySeverity: {},
              topSuggestedActions: [],
            },
            baselineOnly: {
              totalFailures: 0,
              byCategory: {},
              byProvider: {},
              bySeverity: {},
              topSuggestedActions: [],
            },
          },
        ]}
      />,
    );

    expect(html).toContain("No failure categories were recorded");
    expect(html).toContain("No failures match the selected provider");
  });

  it("handles no local report", () => {
    const html = renderToStaticMarkup(<FailuresPage reports={[]} />);
    expect(html).toContain("No failure report found");
  });

  it("filters failures and summaries by provider", () => {
    const baselineFailure = {
      ...report.failures[0],
      id: "suite:case:full_context_baseline:conflict_resolution_failure",
      provider: "full_context_baseline",
      category: "conflict_resolution_failure" as const,
      expectedBehavior: true,
    };
    const providerAware = {
      ...report,
      failures: [...report.failures, baselineFailure],
      byProvider: {
        ...report.byProvider,
        full_context_baseline: {
          totalFailures: 1,
          byCategory: { conflict_resolution_failure: 1 },
          byProvider: { full_context_baseline: 1 },
          bySeverity: { high: 1 },
          topSuggestedActions: ["Comparison evidence."],
        },
      },
    };

    expect(filterFailuresByProvider(providerAware.failures, "mneno")).toHaveLength(1);
    expect(
      filterFailuresByProvider(providerAware.failures, "full_context_baseline")[0]?.provider,
    ).toBe("full_context_baseline");
    expect(summaryForProvider(providerAware, "mneno").byCategory).toEqual({
      retrieval_failure: 1,
    });
    expect(summaryForProvider(providerAware, "full_context_baseline").byCategory).toEqual({
      conflict_resolution_failure: 1,
    });
  });
});
