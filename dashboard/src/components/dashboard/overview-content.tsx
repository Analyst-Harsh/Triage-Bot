"use client";

import { Header } from "@/components/layout/header";
import { StatCardsRow } from "@/components/stats/stat-cards-row";
import { StatusDistributionBar } from "@/components/stats/status-distribution-bar";
import { RunsTableSection } from "@/components/table/runs-table-section";
import type { components } from "@/lib/api/schema";
import { useDashboardFilters } from "./use-dashboard-filters";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

export function OverviewContent({
  initialSummary,
}: {
  initialSummary?: RunSummaryResponse;
}) {
  const { filters, setFilters } = useDashboardFilters();

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <Header period={filters.period} onPeriodChange={(period) => setFilters({ period })} />
      <main className="flex-1 space-y-6 overflow-x-hidden overflow-y-auto p-6">
        <StatCardsRow period={filters.period} initialSummary={initialSummary} />
        <StatusDistributionBar period={filters.period} initialSummary={initialSummary} />
        <RunsTableSection period={filters.period} />
      </main>
    </div>
  );
}
