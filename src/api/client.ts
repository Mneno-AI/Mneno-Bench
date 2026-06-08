import { sampleRuns } from "../lib/runs";
import type { BenchmarkRun } from "../lib/schema";

export async function listRuns(): Promise<BenchmarkRun[]> {
  // The dashboard loads generated local result JSON without requiring a backend.
  return Promise.resolve(sampleRuns);
}
