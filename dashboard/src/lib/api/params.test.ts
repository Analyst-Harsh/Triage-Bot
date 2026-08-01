// @vitest-environment node
import { describe, expect, it } from "vitest";
import { parseListRunsQuery, parseSummaryQuery, runIdentityParamsSchema } from "./params";

describe("parseListRunsQuery", () => {
  it("returns an all-undefined query for empty search params", () => {
    const query = parseListRunsQuery(new URLSearchParams());
    expect(query).toEqual({
      status: undefined,
      repo_full_name: undefined,
      source: undefined,
      period: undefined,
      page: undefined,
      page_size: undefined,
    });
  });

  it("collects repeated status params into an array", () => {
    const query = parseListRunsQuery(
      new URLSearchParams("status=failed&status=pending_approval"),
    );
    expect(query.status).toEqual(["failed", "pending_approval"]);
  });

  it("coerces page and page_size to numbers", () => {
    const query = parseListRunsQuery(new URLSearchParams("page=2&page_size=50"));
    expect(query.page).toBe(2);
    expect(query.page_size).toBe(50);
  });

  it("passes repo_full_name, source, and period through as strings", () => {
    const query = parseListRunsQuery(
      new URLSearchParams("repo_full_name=octo/repo&source=webhook&period=24h"),
    );
    expect(query.repo_full_name).toBe("octo/repo");
    expect(query.source).toBe("webhook");
    expect(query.period).toBe("24h");
  });
});

describe("parseSummaryQuery", () => {
  it("returns undefined fields for empty search params", () => {
    expect(parseSummaryQuery(new URLSearchParams())).toEqual({
      repo_full_name: undefined,
      period: undefined,
    });
  });

  it("passes repo_full_name and period through", () => {
    const query = parseSummaryQuery(new URLSearchParams("repo_full_name=octo/repo&period=7d"));
    expect(query).toEqual({ repo_full_name: "octo/repo", period: "7d" });
  });
});

describe("runIdentityParamsSchema", () => {
  it("coerces issueNumber from a route-param string to a number", () => {
    const result = runIdentityParamsSchema.parse({
      owner: "octo",
      repo: "repo",
      issueNumber: "42",
    });
    expect(result).toEqual({ owner: "octo", repo: "repo", issueNumber: 42 });
  });

  it("rejects a non-positive issue number", () => {
    expect(() =>
      runIdentityParamsSchema.parse({ owner: "octo", repo: "repo", issueNumber: "0" }),
    ).toThrow();
  });

  it("rejects a non-numeric issue number", () => {
    expect(() =>
      runIdentityParamsSchema.parse({ owner: "octo", repo: "repo", issueNumber: "abc" }),
    ).toThrow();
  });
});
