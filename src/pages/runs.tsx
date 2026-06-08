import { ResultDetail } from "../components/result-detail";
import { RunsTable } from "../components/runs-table";
import { TraceSummary } from "../components/trace-summary";
import { latestRun, sampleRuns } from "../lib/runs";
import { PageHeader } from "./dashboard";

export function RunsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Local result store"
        title="Benchmark runs"
        description="Runs are loaded from local JSON in the results directory. Mneno benchmark and trace exports remain available in each normalized run."
      />
      <RunsTable runs={sampleRuns} />
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <ResultDetail run={latestRun} />
        <TraceSummary trace={latestRun.trace} />
      </div>
    </>
  );
}
