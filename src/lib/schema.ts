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
  mnenoExecution?: MnenoExecutionSummary;
  rawExport?: unknown;
}

export interface MnenoCapabilityReport {
  available: boolean;
  version: string | null;
  capabilities: Record<string, boolean>;
  missing: string[];
  partial: boolean;
}

export interface MnenoCaseDecisionSummary {
  caseId: string;
  category: string;
  includedIds: string[];
  excludedIds: string[];
  traceIds: string[];
  reasonCount: number;
}

export interface MnenoExecutionSummary {
  memoriesLoaded: number;
  sessionsCreated: number;
  conflictsDetected: number;
  hierarchyEvaluated: boolean;
  hierarchyTransitions: Record<string, number>;
  compactionPreviewed: boolean;
  compactionStats: Record<string, number>;
  tracesExported: number;
  capabilityErrors: Record<string, string>;
  capabilityReport: MnenoCapabilityReport;
  decisions: MnenoCaseDecisionSummary[];
}

export interface ContextRotCategorySummary {
  category: string;
  caseCount: number;
  contextRotScore: number | null;
  metrics: Record<string, number | null>;
}

export interface ContextRotSystemSummary {
  name: string;
  status: RunStatus;
  contextRotScore: number | null;
  metrics: Record<string, number | null>;
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
