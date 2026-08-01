import type { components } from "@/lib/api/schema";
import { RUN_STATUSES } from "@/lib/status";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

export type StatusDistributionSegment = {
  status: string;
  count: number;
  percent: number;
};

/**
 * Aggregates every bucket's `counts_by_status` into one whole-period
 * distribution, in `RUN_STATUSES` order, dropping zero-count statuses --
 * feeds the Overview page's status mix bar.
 */
export function deriveStatusDistribution(summary: RunSummaryResponse): StatusDistributionSegment[] {
  const totals = new Map<string, number>();
  for (const point of summary.points) {
    for (const status of RUN_STATUSES) {
      totals.set(status, (totals.get(status) ?? 0) + (point.counts_by_status[status] ?? 0));
    }
  }

  const grandTotal = [...totals.values()].reduce((sum, count) => sum + count, 0);
  if (grandTotal === 0) {
    return [];
  }

  return RUN_STATUSES.filter((status) => (totals.get(status) ?? 0) > 0).map((status) => {
    const count = totals.get(status) ?? 0;
    return { status, count, percent: (count / grandTotal) * 100 };
  });
}
