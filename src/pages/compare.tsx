import { ComparisonView } from "../components/comparison-view";
import { sampleRun } from "../lib/runs";
import { PageHeader } from "./dashboard";

export function ComparePage() {
  return (
    <>
      <PageHeader
        eyebrow="System comparison"
        title="Baseline versus Mneno"
        description="The comparison surface separates implemented baseline behavior from capabilities that require a real Mneno SDK run and trace export."
      />
      <ComparisonView run={sampleRun} />
    </>
  );
}
