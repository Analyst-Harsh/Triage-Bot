import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { outcomeDistribution } from "./post-outcome-summary";

type ActionPostResult = components["schemas"]["ActionPostResult"];

function result(outcome: ActionPostResult["outcome"]): ActionPostResult {
  return { outcome, detail: null };
}

describe("outcomeDistribution", () => {
  it("counts each outcome", () => {
    expect(outcomeDistribution([result("posted"), result("posted"), result("rejected")])).toEqual(
      { posted: 2, failed: 0, queued: 0, rejected: 1 },
    );
  });

  it("returns all zeros for an empty list", () => {
    expect(outcomeDistribution([])).toEqual({ posted: 0, failed: 0, queued: 0, rejected: 0 });
  });
});
