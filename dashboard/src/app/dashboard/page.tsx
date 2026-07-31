import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { Suspense } from "react";
import { OverviewContent } from "@/components/dashboard/overview-content";
import { Sidebar } from "@/components/layout/sidebar";
import { RunsTableSkeleton } from "@/components/table/runs-table-skeleton";
import type { components } from "@/lib/api/schema";
import { TriageApiClient } from "@/lib/api/triage-client";
import type { Query } from "@/lib/api/triage-client";
import { parseDashboardFilters } from "@/lib/dashboard-filters";
import { getQueryClient } from "@/lib/query/get-query-client";
import { queryKeys } from "@/lib/query/keys";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];
type RawSearchParams = Record<string, string | string[] | undefined>;

function toURLSearchParams(raw: RawSearchParams): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(raw)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item);
    } else {
      params.append(key, value);
    }
  }
  return params;
}

/**
 * Server Component: prefetches the exact same queries (same query keys) the
 * client tree will request, so first paint has real data with zero loading
 * flash -- `dehydrate`/`HydrationBoundary` is the bridge for the Overview
 * content. The sidebar's all-time health summary is threaded separately as
 * an explicit `initialData` prop (read straight back off this same
 * `queryClient` via `getQueryData`, no second network call) rather than
 * relying solely on `HydrationBoundary` -- `Sidebar` sits in a different
 * branch of the tree than the rest of the page, and `initialData` is the
 * simpler, more direct guarantee for that one case. Reads `searchParams`
 * directly so a deep link (e.g. `?period=7d&status=failed`) is correct on
 * first paint too, not just after a client-side refetch.
 */
export default async function DashboardOverviewPage({
  searchParams,
}: {
  searchParams: Promise<RawSearchParams>;
}) {
  const filters = parseDashboardFilters(toURLSearchParams(await searchParams));
  const queryClient = getQueryClient();
  const client = new TriageApiClient();

  const runsFilters = {
    status: filters.status,
    repoFullName: filters.repoFullName,
    source: filters.source,
    period: filters.period,
    page: filters.page,
    pageSize: 20,
  };

  await Promise.all([
    queryClient.prefetchQuery({
      queryKey: queryKeys.runs(runsFilters),
      queryFn: () =>
        client.listRuns({
          status: filters.status,
          repo_full_name: filters.repoFullName,
          source: filters.source,
          period: filters.period,
          page: filters.page,
          page_size: 20,
        } as Query<"/runs">),
    }),
    queryClient.prefetchQuery({
      queryKey: queryKeys.summary(filters.period, undefined),
      queryFn: () =>
        client.getSummary({ period: filters.period } as Query<"/runs/summary">),
    }),
    queryClient.prefetchQuery({
      queryKey: queryKeys.liveHealthSummary(),
      queryFn: () => client.getSummary({}),
    }),
  ]);

  const initialHealthSummary = queryClient.getQueryData<RunSummaryResponse>(
    queryKeys.liveHealthSummary(),
  );

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <div className="flex min-h-screen">
        <Sidebar initialHealthSummary={initialHealthSummary} />
        <Suspense fallback={<RunsTableSkeleton />}>
          <OverviewContent />
        </Suspense>
      </div>
    </HydrationBoundary>
  );
}
