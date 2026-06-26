import type { FailureCase, FailureReport, RootCauseSummary } from "./schema";

export type ProviderFilter =
  | "all"
  | "mneno"
  | "keyword_baseline"
  | "full_context_baseline"
  | "random_baseline";

export function filterFailuresByProvider(
  failures: FailureCase[],
  provider: ProviderFilter,
): FailureCase[] {
  return provider === "all"
    ? failures
    : failures.filter((failure) => failure.provider === provider);
}

export function summaryForProvider(
  report: FailureReport,
  provider: ProviderFilter,
): RootCauseSummary {
  if (provider === "all") return report.summary;
  if (provider === "mneno") return report.mnenoOnly;
  return report.byProvider[provider] ?? emptySummary();
}

export function emptySummary(): RootCauseSummary {
  return {
    totalFailures: 0,
    byCategory: {},
    byProvider: {},
    bySeverity: {},
    topSuggestedActions: [],
  };
}
