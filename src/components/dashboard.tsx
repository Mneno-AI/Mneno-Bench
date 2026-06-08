import { ArrowRight, Database, FlaskConical, ShieldCheck } from "lucide-react";

import { latestRun, suites } from "../lib/runs";
import type { PageKey } from "./sidebar";
import { MetricCard } from "./metric-card";

export function Dashboard({
  onNavigate,
}: {
  onNavigate: (page: PageKey) => void;
}) {
  return (
    <>
      <section className="grid gap-4 md:grid-cols-3">
        <SummaryItem
          icon={FlaskConical}
          label="Primary suite"
          value="Mneno Context Rot"
        />
        <SummaryItem icon={Database} label="Result store" value="Local JSON" />
        <SummaryItem icon={ShieldCheck} label="Credentials" value="Not required" />
      </section>

      <section className="mt-8">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase text-signal-700">
              Synthetic preview
            </p>
            <h2 className="mt-1 text-xl font-semibold">Mneno-specific metrics</h2>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("mneno-suite")}
            className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 text-sm font-semibold text-signal-700 transition-colors hover:bg-signal-100"
          >
            View suite
            <ArrowRight aria-hidden="true" size={17} />
          </button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {latestRun.metrics.map((metric) => (
            <MetricCard key={metric.name} metric={metric} />
          ))}
        </div>
      </section>

      <section className="mt-8">
        <div className="mb-4">
          <p className="font-mono text-xs uppercase text-ink-600">
            Validation sequence
          </p>
          <h2 className="mt-1 text-xl font-semibold">Available benchmark suites</h2>
        </div>
        <div className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
          {suites.map((suite) => (
            <div
              key={suite.id}
              className="flex flex-col gap-3 border-b border-ink-950/10 p-5 last:border-0 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <h3 className="font-semibold">{suite.name}</h3>
                <p className="mt-1 text-sm text-ink-600">{suite.role}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs uppercase text-ink-600">
                  {suite.difficulty}
                </span>
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                    suite.status === "available"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {suite.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function SummaryItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FlaskConical;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-4 rounded-lg border border-ink-950/10 bg-white p-4 shadow-panel">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-signal-100 text-signal-700">
        <Icon aria-hidden="true" size={19} />
      </span>
      <div className="min-w-0">
        <p className="text-xs uppercase text-ink-600">{label}</p>
        <p className="mt-1 truncate text-sm font-semibold">{value}</p>
      </div>
    </div>
  );
}
