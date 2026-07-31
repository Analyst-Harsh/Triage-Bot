import type { components } from "@/lib/api/schema";
import { NON_TERMINAL_STATUSES, SUCCESS_STATUSES } from "@/lib/status";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

export type HealthMetrics = {
  successRate: number | null;
  failureRate: number | null;
  inFlightRuns: number;
};

/**
 * Derives the sidebar SystemHealthPanel's three metrics from an all-time
 * (`period` omitted) `/runs/summary` response -- always exactly one bucket,
 * so `points[0]` is the whole dataset. `null` rates (not `0`) when there's
 * no data yet, so the UI can render "—" instead of a misleading "0%".
 */
export function deriveHealthMetrics(summary: RunSummaryResponse): HealthMetrics {
  const point = summary.points[0];
  if (!point) {
    return { successRate: null, failureRate: null, inFlightRuns: 0 };
  }
  const counts = point.counts_by_status;
  const total = point.run_count;
  const successCount = SUCCESS_STATUSES.reduce((sum, status) => sum + (counts[status] ?? 0), 0);
  const failedCount = counts.failed ?? 0;
  const inFlightRuns = NON_TERMINAL_STATUSES.reduce(
    (sum, status) => sum + (counts[status] ?? 0),
    0,
  );

  return {
    successRate: total > 0 ? successCount / total : null,
    failureRate: total > 0 ? failedCount / total : null,
    inFlightRuns,
  };
}
