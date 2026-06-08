import type { MetricResult } from "./schema";

const lowerIsBetter = new Set([
  "latency_ms",
  "stale_memory_error_rate",
  "context_tokens",
]);

export function metricDirection(name: string): "higher" | "lower" {
  return lowerIsBetter.has(name) || name.endsWith("_error_rate")
    ? "lower"
    : "higher";
}

export function metricLabel(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatMetric(metric: MetricResult): string {
  if (metric.value === null) {
    return "Pending";
  }
  return `${Math.round(metric.value * 100)}%`;
}

export function metricIntent(metric: MetricResult): string {
  return metric.direction === "higher" ? "Higher is better" : "Lower is better";
}
