import { describe, expect, it } from "vitest";
import { formatCost, formatDuration, formatRelativeTime } from "./format";

describe("formatRelativeTime", () => {
  const now = new Date("2026-01-01T12:00:00Z");

  it("formats a few minutes ago", () => {
    expect(formatRelativeTime("2026-01-01T11:58:00Z", now)).toBe("2 minutes ago");
  });

  it("formats a few hours ago", () => {
    expect(formatRelativeTime("2026-01-01T09:00:00Z", now)).toBe("3 hours ago");
  });

  it("formats a future time", () => {
    expect(formatRelativeTime("2026-01-01T12:05:00Z", now)).toBe("in 5 minutes");
  });
});

describe("formatDuration", () => {
  it("formats seconds as MM:SS", () => {
    expect(formatDuration(65)).toBe("01:05");
    expect(formatDuration(5)).toBe("00:05");
    expect(formatDuration(600)).toBe("10:00");
  });
});

describe("formatCost", () => {
  it("formats a numeric cost to three decimal places", () => {
    expect(formatCost(0.042)).toBe("$0.042");
  });

  it("renders a dash for null (unknown) cost", () => {
    expect(formatCost(null)).toBe("—");
  });
});
