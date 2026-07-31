import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { deriveStatCards } from "./stat-cards";

type TrendPoint = components["schemas"]["TrendPoint"];
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

function point(overrides: Partial<TrendPoint> & { counts?: Record<string, number> }): TrendPoint {
  const { counts, ...rest } = overrides;
  return {
    bucket_start: null,
    counts_by_status: { ...zeroCounts(), ...counts },
    run_count: 0,
    total_cost_usd: 0,
    ...rest,
  };
}

function summary(points: TrendPoint[]): RunSummaryResponse {
  return { period: null, interval: null, points };
}

describe("deriveStatCards", () => {
  it("sums pending_approval, combines auto_posted+approved_and_posted, and sums failed/cost across all buckets", () => {
    const cards = deriveStatCards(
      summary([
        point({ counts: { pending_approval: 2, auto_posted: 1 }, total_cost_usd: 0.5 }),
        point({ counts: { approved_and_posted: 3, failed: 1 }, total_cost_usd: 0.25 }),
      ]),
    );

    const byKey = Object.fromEntries(cards.map((c) => [c.key, c]));
    expect(byKey.pending_approval.total).toBe(2);
    expect(byKey.auto_posted.total).toBe(4); // 1 auto_posted + 3 approved_and_posted
    expect(byKey.failed.total).toBe(1);
    expect(byKey.est_spend.total).toBe(0.75);
  });

  it("builds a per-bucket sparkline series in bucket order", () => {
    const cards = deriveStatCards(
      summary([
        point({ counts: { failed: 1 } }),
        point({ counts: { failed: 0 } }),
        point({ counts: { failed: 3 } }),
      ]),
    );
    const failedCard = cards.find((c) => c.key === "failed");
    expect(failedCard?.sparkline).toEqual([1, 0, 3]);
  });

  it("does not produce a fifth 'active/researching' card", () => {
    const cards = deriveStatCards(summary([point({})]));
    expect(cards.map((c) => c.key)).toEqual(["pending_approval", "auto_posted", "failed", "est_spend"]);
  });

  it("handles the degenerate single all-time bucket (period omitted)", () => {
    const cards = deriveStatCards(
      summary([point({ counts: { auto_posted: 5 }, run_count: 5, total_cost_usd: 1.5 })]),
    );
    expect(cards.find((c) => c.key === "auto_posted")?.total).toBe(5);
    expect(cards.find((c) => c.key === "est_spend")?.total).toBe(1.5);
  });
});
