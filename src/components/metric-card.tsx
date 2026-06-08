import { ArrowDown, ArrowUp, Minus } from "lucide-react";

import { formatMetric, metricIntent } from "../lib/metrics";
import type { MetricResult } from "../lib/schema";

export function MetricCard({ metric }: { metric: MetricResult }) {
  const DirectionIcon =
    metric.value === null ? Minus : metric.direction === "higher" ? ArrowUp : ArrowDown;

  return (
    <article className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-ink-600">{metric.label}</p>
          <p className="mt-2 font-mono text-3xl font-semibold tabular-nums text-ink-950">
            {formatMetric(metric)}
          </p>
        </div>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-canvas text-ink-600">
          <DirectionIcon aria-hidden="true" size={17} />
        </span>
      </div>
      <p className="mt-4 text-sm leading-6 text-ink-600">{metric.description}</p>
      <p className="mt-3 font-mono text-[11px] uppercase text-signal-700">
        {metricIntent(metric)}
      </p>
    </article>
  );
}
