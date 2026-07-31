"use client";

import { Header } from "@/components/layout/header";
import { StatCardsRow } from "@/components/stats/stat-cards-row";
import { RunsTableSection } from "@/components/table/runs-table-section";
import { useDashboardFilters } from "./use-dashboard-filters";

export function OverviewContent() {
  const { filters, setFilters } = useDashboardFilters();

  return (
    <div className="flex flex-1 flex-col">
      <Header period={filters.period} onPeriodChange={(period) => setFilters({ period })} />
      <main className="flex-1 space-y-6 overflow-y-auto p-6">
        <StatCardsRow period={filters.period} />
        <RunsTableSection period={filters.period} />
      </main>
    </div>
  );
}
