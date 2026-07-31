// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TriageApiClient, TriageApiError } from "./triage-client";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("TriageApiClient", () => {
  beforeEach(() => {
    vi.stubEnv("TRIAGE_API_BASE_URL", "http://127.0.0.1:8000");
    vi.stubEnv("TRIAGE_API_BEARER_TOKEN", "test-token");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("throws a clear error when TRIAGE_API_BASE_URL is unset", () => {
    vi.stubEnv("TRIAGE_API_BASE_URL", "");
    expect(() => new TriageApiClient()).toThrow(/TRIAGE_API_BASE_URL/);
  });

  it("throws a clear error when TRIAGE_API_BEARER_TOKEN is unset", () => {
    vi.stubEnv("TRIAGE_API_BEARER_TOKEN", "");
    expect(() => new TriageApiClient()).toThrow(/TRIAGE_API_BEARER_TOKEN/);
  });

  it("sends the bearer token and returns parsed data on a 2xx response", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const request = input as Request;
      expect(request.url).toContain("/runs/summary");
      expect(request.headers.get("authorization")).toBe("Bearer test-token");
      return jsonResponse({ period: null, interval: null, points: [] }, 200);
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new TriageApiClient();
    const summary = await client.getSummary({});

    expect(summary).toEqual({ period: null, interval: null, points: [] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("throws TriageApiError with the upstream status and body on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "no run found for this issue" }, 404)),
    );

    const client = new TriageApiClient();

    await expect(client.getRunDetail("octo", "repo", 42)).rejects.toMatchObject({
      status: 404,
      body: { detail: "no run found for this issue" },
    });
    await expect(client.getRunDetail("octo", "repo", 42)).rejects.toBeInstanceOf(TriageApiError);
  });

  it("passes path params correctly for the trace endpoint", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      expect((input as Request).url).toContain("/runs/octo/repo/42/trace");
      return jsonResponse(
        {
          trace_id: "deadbeef",
          langfuse_url: "https://cloud.langfuse.com/trace/deadbeef",
          total_latency_seconds: null,
          total_cost_usd: null,
          observations: [],
        },
        200,
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new TriageApiClient();
    const summary = await client.getTraceSummary("octo", "repo", 42);

    expect(summary.trace_id).toBe("deadbeef");
  });
});
