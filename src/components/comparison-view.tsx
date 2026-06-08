import { Check, Minus } from "lucide-react";

import type { BenchmarkRun } from "../lib/schema";

export function ComparisonView({ run }: { run: BenchmarkRun }) {
  return (
    <div className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-panel">
      <div className="grid grid-cols-[minmax(150px,1fr)_1fr_1fr] border-b border-ink-950/10 bg-canvas/70 text-sm font-semibold">
        <div className="p-4">Capability</div>
        <div className="border-l border-ink-950/10 p-4">Keyword baseline</div>
        <div className="border-l border-ink-950/10 p-4">Mneno</div>
      </div>
      {[
        ["Deterministic retrieval", true, null],
        ["Lifecycle-aware suppression", false, null],
        ["Conflict resolution traces", false, null],
        ["Explainability evidence", false, null],
      ].map(([label, baseline, mneno]) => (
        <div
          key={String(label)}
          className="grid grid-cols-[minmax(150px,1fr)_1fr_1fr] border-b border-ink-950/10 text-sm last:border-0"
        >
          <div className="p-4 text-ink-600">{label}</div>
          <ComparisonCell value={baseline as boolean} />
          <div className="border-l border-ink-950/10 p-4 text-amber-900">
            {mneno === null || run.mnenoStatus === "skipped" ? "Awaiting SDK run" : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

function ComparisonCell({ value }: { value: boolean }) {
  return (
    <div className="flex items-center gap-2 border-l border-ink-950/10 p-4">
      {value ? (
        <>
          <Check aria-hidden="true" className="text-emerald-700" size={17} />
          <span>Available</span>
        </>
      ) : (
        <>
          <Minus aria-hidden="true" className="text-ink-600" size={17} />
          <span className="text-ink-600">Not modeled</span>
        </>
      )}
    </div>
  );
}
