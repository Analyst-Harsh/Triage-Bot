import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { highestRiskLevel, riskDistribution } from "./risk-summary";

type ActionRiskAssessment = components["schemas"]["ActionRiskAssessment"];

function assessment(level: ActionRiskAssessment["level"]): ActionRiskAssessment {
  return { level, risk_factors: [], reasoning: "r" };
}

describe("highestRiskLevel", () => {
  it("returns the single level when there is one assessment", () => {
    expect(highestRiskLevel([assessment("medium")])).toBe("medium");
  });

  it("returns the highest level across several assessments, regardless of order", () => {
    expect(highestRiskLevel([assessment("low"), assessment("high"), assessment("medium")])).toBe(
      "high",
    );
  });

  it("returns null for an empty list", () => {
    expect(highestRiskLevel([])).toBeNull();
  });
});

describe("riskDistribution", () => {
  it("counts each level", () => {
    expect(
      riskDistribution([assessment("low"), assessment("low"), assessment("high")]),
    ).toEqual({ low: 2, medium: 0, high: 1 });
  });

  it("returns all zeros for an empty list", () => {
    expect(riskDistribution([])).toEqual({ low: 0, medium: 0, high: 0 });
  });
});
