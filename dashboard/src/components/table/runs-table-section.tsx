"use client";

import { useDashboardFilters } from "@/components/dashboard/use-dashboard-filters";
import { useRunsQuery } from "@/lib/query/hooks";
import { RunsFilterBar } from "./runs-filter-bar";
import { RunsTable } from "./runs-table";
import { RunsTablePagination } from "./runs-table-pagination";
import { RunsTableSkeleton } from "./runs-table-skeleton";

/**
 * `period` scopes the whole Overview page, not just the stat cards -- it's
 * passed to this query too, so the table only ever shows runs consistent
 * with what the stat cards above it are summarizing.
 */
export function RunsTableSection({ period }: { period: string | undefined }) {
  const { filters, setFilters } = useDashboardFilters();
  const runsQuery = useRunsQuery({
    status: filters.status,
    repoFullName: filters.repoFullName,
    source: filters.source,
    period,
    page: filters.page,
    pageSize: 20,
  });

  const animationKey = JSON.stringify({
    status: filters.status,
    repoFullName: filters.repoFullName,
    source: filters.source,
    period,
    page: filters.page,
  });

  return (
    <section className="space-y-4">
      <RunsFilterBar
        value={{
          status: filters.status,
          repoFullName: filters.repoFullName,
          source: filters.source,
        }}
        onChange={(next) => setFilters(next)}
      />

      {runsQuery.isPending && <RunsTableSkeleton />}

      {runsQuery.isError && (
        <p className="rounded-xl bg-card p-4 text-sm text-destructive ring-1 ring-foreground/10">
          Couldn&apos;t load runs.
        </p>
      )}

      {runsQuery.data && (
        <>
          <RunsTable runs={runsQuery.data.items} animationKey={animationKey} />
          <RunsTablePagination
            page={runsQuery.data.page}
            totalPages={runsQuery.data.total_pages}
            onPageChange={(page) => setFilters({ page })}
          />
        </>
      )}
    </section>
  );
}
