import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { BenchmarkRun } from "../lib/schema";
import { MnenoSuitePage } from "./mneno-suite";

const run: BenchmarkRun = {
  id: "context-rot-1",
  suite: "Mneno Context Rot Suite v1",
  startedAt: "2026-06-07T12:00:00Z",
  status: "completed",
  systems: ["keyword_baseline", "mneno"],
  cases: 24,
  source: "synthetic",
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
  benchmarkVersion: "0.3.0",
  mnenoVersion: null,
  contextRot: {
    memoryCount: 48,
    caseCount: 24,
    failureCount: 1,
    reportPath: "results/reports/context_rot_suite_latest.md",
    traceDirectory: "results/mneno/traces",
    exportDirectory: "results/mneno/exports",
    systems: [
      {
        name: "keyword_baseline",
        status: "completed",
        contextRotScore: 0.6,
        metrics: {
          expected_memory_recall: 0.5,
          stale_memory_suppression_rate: 0.8,
          context_efficiency_score: 0.3,
        },
        categories: [
          {
            category: "contradiction",
            caseCount: 3,
            contextRotScore: 0.7,
            metrics: {},
          },
        ],
      },
      {
        name: "mneno",
        status: "skipped",
        contextRotScore: null,
        metrics: {},
        categories: [],
      },
    ],
  },
};

describe("Mneno Suite page", () => {
  it("displays category metrics and skipped Mneno status", () => {
    const html = renderToStaticMarkup(<MnenoSuitePage run={run} />);

    expect(html).toContain("Context Rot Score");
    expect(html).toContain("Contradiction");
    expect(html).toContain("Keyword");
    expect(html).toContain("Mneno");
    expect(html).toContain("skipped");
    expect(html).toContain("24 cases");
  });
});
