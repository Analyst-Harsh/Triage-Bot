import { describe, expect, it } from "vitest";
import {
  type DashboardFilters,
  parseDashboardFilters,
  serializeDashboardFilters,
} from "./dashboard-filters";

describe("dashboard filters URL round-trip", () => {
  it("round-trips period, repeated status, repo, source, and page", () => {
    const filters: DashboardFilters = {
      period: "24h",
      status: ["failed", "pending_approval"],
      repoFullName: "octo/repo",
      source: "webhook",
      page: 3,
    };
    const query = serializeDashboardFilters(filters);
    const parsed = parseDashboardFilters(new URLSearchParams(query));
    expect(parsed).toEqual(filters);
  });

  it("defaults to page 1 and omits it from the serialized query", () => {
    const query = serializeDashboardFilters({ page: 1 });
    expect(query).not.toContain("page");
    expect(parseDashboardFilters(new URLSearchParams(query)).page).toBe(1);
  });

  it("parses an empty query into all-undefined filters at page 1", () => {
    expect(parseDashboardFilters(new URLSearchParams())).toEqual({
      period: undefined,
      status: undefined,
      repoFullName: undefined,
      source: undefined,
      page: 1,
    });
  });

  it("falls back to page 1 for a non-positive or non-numeric page param", () => {
    expect(parseDashboardFilters(new URLSearchParams("page=0")).page).toBe(1);
    expect(parseDashboardFilters(new URLSearchParams("page=abc")).page).toBe(1);
    expect(parseDashboardFilters(new URLSearchParams("page=-3")).page).toBe(1);
  });

  it("collects repeated status params", () => {
    const parsed = parseDashboardFilters(
      new URLSearchParams("status=failed&status=pending_approval"),
    );
    expect(parsed.status).toEqual(["failed", "pending_approval"]);
  });
});
