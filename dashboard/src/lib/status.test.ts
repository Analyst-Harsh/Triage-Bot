import { describe, expect, it } from "vitest";
import {
  NON_TERMINAL_STATUSES,
  SUCCESS_STATUSES,
  getRiskVisual,
  getStatusVisual,
} from "./status";

describe("getStatusVisual", () => {
  it("maps the five actively-processing statuses to the active color and pulses:true", () => {
    for (const status of ["received", "planning", "researching", "drafting", "risk_check"]) {
      const visual = getStatusVisual(status);
      expect(visual.colorClass).toBe("text-active");
      expect(visual.pulses).toBe(true);
    }
  });

  it("maps pending_approval to warning and does not pulse", () => {
    const visual = getStatusVisual("pending_approval");
    expect(visual.colorClass).toBe("text-warning");
    expect(visual.pulses).toBe(false);
  });

  it("maps auto_posted and approved_and_posted to success", () => {
    expect(getStatusVisual("auto_posted").colorClass).toBe("text-success");
    expect(getStatusVisual("approved_and_posted").colorClass).toBe("text-success");
  });

  it("maps failed to destructive and rejected to neutral", () => {
    expect(getStatusVisual("failed").colorClass).toBe("text-destructive");
    expect(getStatusVisual("rejected").colorClass).toBe("text-neutral");
  });

  it("falls back gracefully for an unrecognized status", () => {
    const visual = getStatusVisual("something_new");
    expect(visual.label).toBe("Unknown");
  });
});

describe("getRiskVisual", () => {
  it("maps low/medium/high to success/warning/destructive", () => {
    expect(getRiskVisual("low").colorClass).toBe("text-success");
    expect(getRiskVisual("medium").colorClass).toBe("text-warning");
    expect(getRiskVisual("high").colorClass).toBe("text-destructive");
  });

  it("falls back gracefully for an unrecognized risk level", () => {
    expect(getRiskVisual("extreme").label).toBe("Unknown");
  });
});

describe("status groupings", () => {
  it("NON_TERMINAL_STATUSES has exactly the 6 non-terminal RunStatus values, including pending_approval", () => {
    expect(NON_TERMINAL_STATUSES).toEqual([
      "received",
      "planning",
      "researching",
      "drafting",
      "risk_check",
      "pending_approval",
    ]);
  });

  it("SUCCESS_STATUSES has exactly auto_posted and approved_and_posted", () => {
    expect(SUCCESS_STATUSES).toEqual(["auto_posted", "approved_and_posted"]);
  });
});
