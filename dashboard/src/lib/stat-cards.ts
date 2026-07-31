import type { components } from "@/lib/api/schema";
import { SUCCESS_STATUSES } from "@/lib/status";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];
type TrendPoint = components["schemas"]["TrendPoint"];

export type StatCardKey = "pending_approval" | "auto_posted" | "failed" | "est_spend";

export type StatCardData = {
  key: StatCardKey;
  label: string;
  /** Sum across every bucket in the response, for the selected period. */
  total: number;
  /** Per-bucket value, in bucket order -- what the sparkline plots. */
  sparkline: number[];
  isCurrency: boolean;
};

function bucketStatusCount(point: TrendPoint, statuses: readonly string[]): number {
  return statuses.reduce((sum, status) => sum + (point.counts_by_status[status] ?? 0), 0);
}

/**
 * Derives the Overview page's four stat cards from one `/runs/summary`
 * response -- deliberately no fifth "Active/Researching" card here (see
 * hooks.ts's `useLiveHealthSummaryQuery` docstring and the plan history:
 * a period-bucketed sum of in-progress statuses silently under-counts
 * genuinely-live work; the sidebar's period-independent metric is the
 * correct source for that instead).
 */
export function deriveStatCards(summary: RunSummaryResponse): StatCardData[] {
  const points = summary.points;
  return [
    {
      key: "pending_approval",
      label: "Pending Approval",
      total: points.reduce((sum, p) => sum + bucketStatusCount(p, ["pending_approval"]), 0),
      sparkline: points.map((p) => bucketStatusCount(p, ["pending_approval"])),
      isCurrency: false,
    },
    {
      key: "auto_posted",
      label: "Auto-Posted",
      total: points.reduce((sum, p) => sum + bucketStatusCount(p, SUCCESS_STATUSES), 0),
      sparkline: points.map((p) => bucketStatusCount(p, SUCCESS_STATUSES)),
      isCurrency: false,
    },
    {
      key: "failed",
      label: "Failed",
      total: points.reduce((sum, p) => sum + bucketStatusCount(p, ["failed"]), 0),
      sparkline: points.map((p) => bucketStatusCount(p, ["failed"])),
      isCurrency: false,
    },
    {
      key: "est_spend",
      label: "Est. Spend",
      total: points.reduce((sum, p) => sum + p.total_cost_usd, 0),
      sparkline: points.map((p) => p.total_cost_usd),
      isCurrency: true,
    },
  ];
}
