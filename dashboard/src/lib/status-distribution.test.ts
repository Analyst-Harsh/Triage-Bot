import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { deriveStatusDistribution } from "./status-distribution";

type TrendPoint = components["schemas"]["TrendPoint"];
type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

function point(counts: Record<string, number>): TrendPoint {
  return { bucket_start: null, counts_by_status: counts, run_count: 0, total_cost_usd: 0 };
}

function summary(points: TrendPoint[]): RunSummaryResponse {
  return { period: null, interval: null, points };
}

describe("deriveStatusDistribution", () => {
  it("sums counts across buckets and computes percentages of the grand total", () => {
    const segments = deriveStatusDistribution(
      summary([point({ auto_posted: 3, failed: 1 }), point({ auto_posted: 1 })]),
    );

    const byStatus = Object.fromEntries(segments.map((s) => [s.status, s]));
    expect(byStatus.auto_posted).toEqual({ status: "auto_posted", count: 4, percent: 80 });
    expect(byStatus.failed).toEqual({ status: "failed", count: 1, percent: 20 });
  });

  it("drops zero-count statuses and preserves RUN_STATUSES order", () => {
    const segments = deriveStatusDistribution(summary([point({ failed: 1, auto_posted: 2 })]));
    expect(segments.map((s) => s.status)).toEqual(["auto_posted", "failed"]);
  });

  it("returns an empty array when every bucket is empty", () => {
    expect(deriveStatusDistribution(summary([point({})]))).toEqual([]);
    expect(deriveStatusDistribution(summary([]))).toEqual([]);
  });
});
