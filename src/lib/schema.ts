export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "dataset_missing";

export type FailureCategory =
  | "retrieval_failure"
  | "ranking_failure"
  | "context_budget_failure"
  | "lifecycle_filter_failure"
  | "session_continuity_failure"
  | "conflict_resolution_failure"
  | "compaction_failure"
  | "answer_generation_failure"
  | "judge_failure"
  | "dataset_issue"
  | "skipped"
  | "unknown";

export type FailureSeverity = "low" | "medium" | "high" | "critical";

export interface FailureCase {
  id: string;
  benchmark: string;
  caseId: string;
  provider: string;
  category: FailureCategory;
  severity: FailureSeverity;
  query: string;
  expectedIds: string[];
  retrievedIds: string[];
  includedIds: string[];
  excludedIds: string[];
  forbiddenIds: string[];
  traceIds: string[];
  reason: string;
  evidence: string[];
  suggestedAction: string;
  expectedBehavior: boolean;
  interpretation: string | null;
  metadata: Record<string, unknown>;
}

export interface RootCauseSummary {
  totalFailures: number;
  byCategory: Record<string, number>;
  byProvider: Record<string, number>;
  bySeverity: Record<string, number>;
  topSuggestedActions: string[];
}

export interface FailureReport {
  id: string;
  benchmark: string;
  runId: string;
  createdAt: string;
  failures: FailureCase[];
  summary: RootCauseSummary;
  byProvider: Record<string, RootCauseSummary>;
  mnenoOnly: RootCauseSummary;
  baselineOnly: RootCauseSummary;
  metadata: Record<string, unknown>;
}

export type RetrievalRootCause =
  | "evidence_not_indexed"
  | "candidate_generation_failure"
  | "query_normalization_failure"
  | "lexical_mismatch"
  | "semantic_retrieval_failure"
  | "ranking_failure"
  | "budget_exclusion"
  | "session_bias_failure"
  | "lifecycle_filter_failure"
  | "unknown";

export interface CountPercentage {
  count: number;
  percentage: number;
}

export interface DeepDiveEvidenceMemory {
  evidenceId: string;
  text: string | null;
  sessionId: string | null;
  coreMemoryId: string | null;
}

export interface DeepDiveCandidate {
  id: string;
  coreMemoryId: string;
  text: string | null;
  score: number | null;
  rank: number | null;
  selected: boolean;
  reasons: string[];
}

export interface RetrievalFailureInspection {
  id: string;
  caseId: string;
  provider: string;
  conversationId: string;
  questionType: string;
  category: string;
  sessions: string[];
  question: string;
  normalizedQuestion: string;
  expectedEvidence: DeepDiveEvidenceMemory[];
  retrievedCandidates: DeepDiveCandidate[];
  includedIds: string[];
  excludedExpectedIds: string[];
  traceIds: string[];
  rootCause: RetrievalRootCause;
  explanation: string;
  classificationEvidence: string[];
}

export interface RetrievalStatistics {
  sampleSize: number;
  expectedEvidenceCount: number;
  retrievedExpectedCount: number;
  candidateExpectedCount: number;
  retrievalRecall: number | null;
  candidateCoverage: number | null;
  failuresByRootCause: Record<string, CountPercentage>;
  failuresByConversation: Record<string, CountPercentage>;
  failuresByQuestionType: Record<string, CountPercentage>;
  failuresBySession: Record<string, CountPercentage>;
  failuresByCategory: Record<string, CountPercentage>;
}

export interface ImprovementOpportunity {
  title: string;
  evidence: string[];
  expectedImpact: string;
  confidence: string;
  suggestedCoreArea: string;
}

export interface RetrievalDeepDive {
  benchmark: string;
  createdAt: string;
  provider: string;
  totalFailures: number;
  sampledFailures: RetrievalFailureInspection[];
  rootCauses: Record<string, CountPercentage>;
  statistics: RetrievalStatistics;
  recommendations: ImprovementOpportunity[];
  topFailureCases: RetrievalFailureInspection[];
  recommendedCorePriorities: string[];
  runId: string | null;
  deterministicSeed: number;
  metadata: Record<string, unknown>;
}

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
  locomo?: LocomoSummary;
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

export interface LocomoSystemSummary {
  name: string;
  status: RunStatus;
  metrics: Record<string, number | null>;
  scoreLabels: {
    officialScore: number | null;
    diagnosticScore: number | null;
    retrievalDiagnostic: number | null;
    judgeScore: number | null;
  };
  traceIds: string[];
  judge: {
    status: string;
    model: string | null;
    provider: string | null;
    promptVersion: string | null;
  };
  skipReason: string | null;
  errors: string[];
}

export interface LocomoCheckpointingSummary {
  enabled: boolean;
  resumedCases: number;
  completedCases: number;
  failedCases: number;
  checkpointDir: string;
  fingerprint: string | null;
  evaluationFingerprint: string | null;
  reuseFailedCheckpoints: boolean;
}

export interface LocomoExternalRequestsSummary {
  enabled: boolean;
  totalRequests: number;
  successes: number;
  failures: number;
  retries: number;
  rateLimited: number;
  elapsedSeconds: number | null;
}

export interface LocomoFailureAnalysisSummary {
  failureCount: number;
  topCategoriesOverall: Record<string, number>;
  topCategoriesMneno: Record<string, number>;
  topCategoriesBaselines: Record<string, number>;
  mnenoSuggestedActions: string[];
  worstCases: Array<{
    caseId: string;
    provider: string;
    category: string;
    severity: string;
  }>;
  jsonPath: string | null;
  reportPath: string | null;
}

export interface LocomoRetrievalDeepDiveSummary {
  sampledFailureCount: number;
  rootCauses: Record<string, number>;
  jsonPath: string | null;
  reportPath: string | null;
}

export interface LocomoSummary {
  datasetStatus: string;
  datasetPath?: string;
  executionStatus: RunStatus;
  evaluationMode: string;
  conversationCount: number;
  messageCount: number;
  questionCount: number;
  categories: Record<string, number>;
  systems: LocomoSystemSummary[];
  malformedEvidenceWarningCount: number;
  reportPath: string;
  reportUrl?: string;
  traceDirectory: string;
  rawOutputDirectory: string;
  judgePromptDirectory: string;
  judgeResponseDirectory: string;
  judgeModel: string | null;
  judgeProvider: string | null;
  promptVersion: string | null;
  officialScoringStatus: string;
  officialScoringReason: string;
  checkpointing?: LocomoCheckpointingSummary;
  externalRequests?: LocomoExternalRequestsSummary;
  failureAnalysis?: LocomoFailureAnalysisSummary;
  retrievalDeepDive?: LocomoRetrievalDeepDiveSummary;
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
