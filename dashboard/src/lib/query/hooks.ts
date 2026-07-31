"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { buildRunsUrl } from "./build-url";
import { fetchJson, postJson } from "./fetch-json";
import { type RunsListFilters, queryKeys } from "./keys";

type RunListResponse = components["schemas"]["RunListResponse"];
type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];
type RunDetailResponse = components["schemas"]["RunDetailResponse"];
type ApprovalRequest = components["schemas"]["ApprovalRequest"];
type TraceSummaryResponse = components["schemas"]["TraceSummaryResponse"];
type RunAcceptedResponse = components["schemas"]["RunAcceptedResponse"];
type ApprovalDecision = components["schemas"]["ApprovalDecision"];
type RetryRequest = components["schemas"]["RetryRequest"];

/** Overview page: the runs table. `period` scopes it alongside the stat
 * cards -- see keys.ts's docstring for why every filter belongs in the key. */
export function useRunsQuery(filters: RunsListFilters) {
  return useQuery({
    queryKey: queryKeys.runs(filters),
    queryFn: () =>
      fetchJson<RunListResponse>(
        buildRunsUrl("/api/runs", {
          status: filters.status,
          repo_full_name: filters.repoFullName,
          source: filters.source,
          period: filters.period,
          page: filters.page,
          page_size: filters.pageSize,
        }),
      ),
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });
}

/** Overview page: stat cards + sparklines, scoped to the selected period. */
export function useRunsSummaryQuery(period: string | undefined, repoFullName?: string) {
  return useQuery({
    queryKey: queryKeys.summary(period, repoFullName),
    queryFn: () =>
      fetchJson<RunSummaryResponse>(
        buildRunsUrl("/api/runs/summary", { period, repo_full_name: repoFullName }),
      ),
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });
}

/** Sidebar SystemHealthPanel: deliberately period-independent (all-time) --
 * see the plan's own note on why this must not share the Overview page's
 * period selector. `initialData` is threaded explicitly from the Server
 * Component's own prefetch (`page.tsx` reads it back off the same
 * `queryClient.prefetchQuery` call via `getQueryData`) rather than relying
 * solely on `HydrationBoundary`'s cross-tree hydration timing for this one
 * query -- `Sidebar` sits in a different branch of the tree than the rest
 * of the Overview content, and `initialData` is the simpler, more direct
 * guarantee that first paint has real data regardless of that boundary. */
export function useLiveHealthSummaryQuery(initialData?: RunSummaryResponse) {
  return useQuery({
    queryKey: queryKeys.liveHealthSummary(),
    queryFn: () => fetchJson<RunSummaryResponse>("/api/runs/summary"),
    initialData,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });
}

export function useRunDetailQuery(owner: string, repo: string, issueNumber: number) {
  return useQuery({
    queryKey: queryKeys.runDetail(owner, repo, issueNumber),
    queryFn: () =>
      fetchJson<RunDetailResponse>(`/api/runs/${owner}/${repo}/${issueNumber}`),
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
  });
}

export function usePendingApprovalQuery(
  owner: string,
  repo: string,
  issueNumber: number,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.pendingApproval(owner, repo, issueNumber),
    queryFn: () =>
      fetchJson<ApprovalRequest>(`/api/runs/${owner}/${repo}/${issueNumber}/resume`),
    enabled: options?.enabled ?? true,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
  });
}

/** Fetched once, not polled -- a full trace (potentially hundreds of
 * observations) is a heavier payload than the run detail it accompanies,
 * and doesn't change meaningfully once the run itself is done. The
 * Overview/Header refresh action still triggers a manual refetch. */
export function useTraceSummaryQuery(
  owner: string,
  repo: string,
  issueNumber: number,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.traceSummary(owner, repo, issueNumber),
    queryFn: () =>
      fetchJson<TraceSummaryResponse>(`/api/runs/${owner}/${repo}/${issueNumber}/trace`),
    enabled: options?.enabled ?? true,
  });
}

export function useApprovalMutation(owner: string, repo: string, issueNumber: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (decision: ApprovalDecision) =>
      postJson<RunAcceptedResponse>(
        `/api/runs/${owner}/${repo}/${issueNumber}/resume`,
        decision,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.runDetail(owner, repo, issueNumber),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.pendingApproval(owner, repo, issueNumber),
      });
    },
  });
}

export function useRetryMutation(owner: string, repo: string, issueNumber: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RetryRequest) =>
      postJson<RunAcceptedResponse>(`/api/runs/${owner}/${repo}/${issueNumber}/retry`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.runDetail(owner, repo, issueNumber),
      });
    },
  });
}
