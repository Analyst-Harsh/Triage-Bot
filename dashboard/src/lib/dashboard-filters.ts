/**
 * Pure URL <-> filter-state conversion for the Overview page, kept
 * framework-free (no `next/navigation`) so it's directly unit-testable --
 * `use-dashboard-filters.ts` is the thin `next/navigation`-coupled wrapper
 * around this. `period` + every filter-row value round-trip through here
 * together, per the plan's deep-linking requirement.
 */

export type DashboardFilters = {
  period?: string;
  status?: string[];
  repoFullName?: string;
  source?: string;
  page: number;
};

export const DEFAULT_PAGE = 1;

export function parseDashboardFilters(searchParams: URLSearchParams): DashboardFilters {
  const status = searchParams.getAll("status");
  const page = Number(searchParams.get("page"));
  return {
    period: searchParams.get("period") ?? undefined,
    status: status.length > 0 ? status : undefined,
    repoFullName: searchParams.get("repo") ?? undefined,
    source: searchParams.get("source") ?? undefined,
    page: Number.isFinite(page) && page > 0 ? page : DEFAULT_PAGE,
  };
}

export function serializeDashboardFilters(filters: DashboardFilters): string {
  const params = new URLSearchParams();
  if (filters.period) params.set("period", filters.period);
  if (filters.status) {
    for (const value of filters.status) params.append("status", value);
  }
  if (filters.repoFullName) params.set("repo", filters.repoFullName);
  if (filters.source) params.set("source", filters.source);
  if (filters.page !== DEFAULT_PAGE) params.set("page", String(filters.page));
  return params.toString();
}
