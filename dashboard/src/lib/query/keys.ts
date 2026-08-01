/**
 * The single source of truth for every TanStack Query key this app uses.
 * Every filter/param that affects a request's result belongs in its key --
 * Task 8/9's stagger animation replays exactly when one of these keys
 * changes (a real filter/page/id change), never on a same-key background
 * refetch, so an incomplete key here would either miss real refetches or
 * cause the animation to replay on every poll tick.
 */

export type RunsListFilters = {
  status?: string[];
  repoFullName?: string;
  source?: string;
  period?: string;
  page?: number;
  pageSize?: number;
};

export const queryKeys = {
  runs: (filters: RunsListFilters) => ["runs", filters] as const,
  /** Prefix of every `runs(filters)` key, regardless of filters -- pass to
   * `invalidateQueries` (which matches by key prefix) to refresh the
   * Overview table after a mutation without needing to know its current
   * filters/page. */
  allRuns: () => ["runs"] as const,
  summary: (period: string | undefined, repoFullName: string | undefined) =>
    ["runs-summary", period, repoFullName] as const,
  liveHealthSummary: () => ["runs-summary", "all-time"] as const,
  /** Prefix shared by both `summary(...)` and `liveHealthSummary()` -- one
   * `invalidateQueries` call refreshes the stat cards and the sidebar
   * health panel together. */
  allSummaries: () => ["runs-summary"] as const,
  runDetail: (owner: string, repo: string, issueNumber: number) =>
    ["run-detail", owner, repo, issueNumber] as const,
  pendingApproval: (owner: string, repo: string, issueNumber: number) =>
    ["pending-approval", owner, repo, issueNumber] as const,
  traceSummary: (owner: string, repo: string, issueNumber: number) =>
    ["trace-summary", owner, repo, issueNumber] as const,
};
