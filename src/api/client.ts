import { sampleRuns } from "../lib/runs";
import type { BenchmarkRun } from "../lib/schema";

export async function listRuns(): Promise<BenchmarkRun[]> {
  // Step 1 uses local static data. This boundary will later load result JSON files.
  return Promise.resolve(sampleRuns);
}
