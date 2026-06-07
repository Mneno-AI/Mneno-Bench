export type RunStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export interface MetricResult {
  name: string;
  label: string;
  value: number | null;
  description: string;
  direction: "higher" | "lower";
}

export interface TraceSummary {
  traceId?: string;
  operations: number;
  events: number;
  decisions: number;
  durationMs: number | null;
  retrieved: number;
  selected: number;
  suppressed: number;
  conflictsResolved: number;
  explanations: number;
}

export interface BenchmarkRun {
  id: string;
  suite: string;
  startedAt: string;
  status: RunStatus;
  systems: string[];
  cases: number;
  source: "synthetic" | "external";
  mnenoStatus: RunStatus;
  metrics: MetricResult[];
  trace: TraceSummary;
  benchmarkVersion: string;
  mnenoVersion: string | null;
  contextRot?: ContextRotSummary;
  rawExport?: unknown;
}

export interface ContextRotCategorySummary {
  category: string;
  caseCount: number;
  contextRotScore: number;
  metrics: Record<string, number>;
}

export interface ContextRotSystemSummary {
  name: string;
  status: RunStatus;
  contextRotScore: number | null;
  metrics: Record<string, number>;
  categories: ContextRotCategorySummary[];
}

export interface ContextRotSummary {
  memoryCount: number;
  caseCount: number;
  systems: ContextRotSystemSummary[];
  reportPath: string;
  reportUrl?: string;
  traceDirectory: string;
  exportDirectory: string;
  failureCount: number;
}

export interface MnenoTraceExport {
  format: "mneno.trace";
  version: 1;
  trace: Record<string, unknown>;
}

export interface MnenoBenchmarkExport {
  format: "mneno.benchmark.result";
  version: 1;
  [key: string]: unknown;
}

export interface NormalizedResult {
  provider: string;
  query?: string;
  metrics: Record<string, number | null>;
  trace_id: string | null;
  raw_result: unknown;
}

export interface BenchmarkSuite {
  id: string;
  name: string;
  role: string;
  status: "available" | "planned";
  difficulty: "first-party" | "easy" | "medium" | "hard";
}
