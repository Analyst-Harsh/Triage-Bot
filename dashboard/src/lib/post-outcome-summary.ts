import type { components } from "@/lib/api/schema";

type ActionPostResult = components["schemas"]["ActionPostResult"];
type PostOutcome = ActionPostResult["outcome"];

export type OutcomeDistribution = Record<PostOutcome, number>;

/** PostResultsSection's at-a-glance summary strip. */
export function outcomeDistribution(results: ActionPostResult[]): OutcomeDistribution {
  const distribution: OutcomeDistribution = { posted: 0, failed: 0, queued: 0, rejected: 0 };
  for (const result of results) {
    distribution[result.outcome] += 1;
  }
  return distribution;
}
