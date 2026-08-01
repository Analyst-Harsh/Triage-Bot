import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRunDetailQuery, useRunsQuery } from "./hooks";
import { queryKeys } from "./keys";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("useRunsQuery", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches from the URL built for the query key's own filters", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = (input as Request).url ?? String(input);
      expect(url).toContain("/api/runs?");
      expect(url).toContain("period=24h");
      expect(url).toContain("status=failed");
      expect(url).toContain("status=pending_approval");
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient();
    const filters = { period: "24h", status: ["failed", "pending_approval"] };
    const { result } = renderHook(() => useRunsQuery(filters), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(queryClient.getQueryData(queryKeys.runs(filters))).toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 0,
    });
  });

  it("uses a different query key (and refetches) when filters change", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }),
      ),
    );
    const queryClient = new QueryClient();

    const { result, rerender } = renderHook(({ page }: { page: number }) => useRunsQuery({ page }), {
      wrapper: wrapper(queryClient),
      initialProps: { page: 1 },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(queryKeys.runs({ page: 1 }))).toBeDefined();
    expect(queryClient.getQueryData(queryKeys.runs({ page: 2 }))).toBeUndefined();

    rerender({ page: 2 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(queryKeys.runs({ page: 2 }))).toBeDefined();
  });
});

describe("useRunDetailQuery", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds the URL from owner/repo/issueNumber", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = (input as Request).url ?? String(input);
      expect(url).toContain("/api/runs/octo/repo/42");
      return jsonResponse({ run: {}, planner_output: null });
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient();
    const { result } = renderHook(() => useRunDetailQuery("octo", "repo", 42), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
