import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { deriveHealthMetrics } from "./health-metrics";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

function zeroCounts(): Record<string, number> {
  return {
    received: 0,
    planning: 0,
    researching: 0,
    drafting: 0,
    risk_check: 0,
    auto_posted: 0,
    pending_approval: 0,
    approved_and_posted: 0,
    rejected: 0,
    failed: 0,
  };
}

function summaryWith(counts: Record<string, number>, runCount: number): RunSummaryResponse {
  return {
    period: null,
    interval: null,
    points: [
      {
        bucket_start: null,
        counts_by_status: { ...zeroCounts(), ...counts },
        run_count: runCount,
        total_cost_usd: 0,
      },
    ],
  };
}

describe("deriveHealthMetrics", () => {
  it("computes success/failure rate against total run_count", () => {
    const metrics = deriveHealthMetrics(
      summaryWith({ auto_posted: 3, approved_and_posted: 2, failed: 1, pending_approval: 4 }, 10),
    );
    expect(metrics.successRate).toBeCloseTo(0.5); // 5/10
    expect(metrics.failureRate).toBeCloseTo(0.1); // 1/10
  });

  it("counts in-flight runs as all 6 non-terminal statuses, including pending_approval", () => {
    const metrics = deriveHealthMetrics(
      summaryWith(
        {
          received: 1,
          planning: 1,
          researching: 1,
          drafting: 1,
          risk_check: 1,
          pending_approval: 5,
          auto_posted: 10,
        },
        20,
      ),
    );
    expect(metrics.inFlightRuns).toBe(10); // 5*1 + 5 pending_approval, excludes auto_posted
  });

  it("returns null rates rather than 0 when there are no runs at all", () => {
    const metrics = deriveHealthMetrics(summaryWith({}, 0));
    expect(metrics.successRate).toBeNull();
    expect(metrics.failureRate).toBeNull();
    expect(metrics.inFlightRuns).toBe(0);
  });

  it("returns a safe default when points is empty", () => {
    const metrics = deriveHealthMetrics({ period: null, interval: null, points: [] });
    expect(metrics).toEqual({ successRate: null, failureRate: null, inFlightRuns: 0 });
  });
});
