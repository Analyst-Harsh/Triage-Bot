"use client";

import type { components } from "@/lib/api/schema";
import { deriveHealthMetrics } from "@/lib/health-metrics";
import { useLiveHealthSummaryQuery } from "@/lib/query/hooks";
import { cn } from "@/lib/utils";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

function formatPercent(rate: number | null): string {
  return rate === null ? "—" : `${(rate * 100).toFixed(1)}%`;
}

function MetricRow({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: string;
  colorClass: string;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("font-mono tabular-nums", colorClass)}>{value}</span>
    </div>
  );
}

/**
 * Deliberately period-independent (all-time) -- see useLiveHealthSummaryQuery's
 * docstring for why this must not share the Overview page's period selector,
 * and for why `initialSummary` is threaded explicitly rather than relying
 * solely on cross-tree hydration.
 */
export function SystemHealthPanel({
  initialSummary,
}: {
  initialSummary?: RunSummaryResponse;
}) {
  const query = useLiveHealthSummaryQuery(initialSummary);

  if (query.isPending) {
    return <div className="h-24 animate-pulse rounded-lg bg-card ring-1 ring-foreground/10" />;
  }

  if (query.isError) {
    return (
      <p className="rounded-lg bg-card p-3 text-xs text-destructive ring-1 ring-foreground/10">
        System health unavailable.
      </p>
    );
  }

  const metrics = deriveHealthMetrics(query.data);

  return (
    <div className="space-y-2.5 rounded-lg bg-card p-3 ring-1 ring-foreground/10">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        System Health
      </p>
      <MetricRow
        label="Success Rate"
        value={formatPercent(metrics.successRate)}
        colorClass="text-success"
      />
      <MetricRow
        label="Failure Rate"
        value={formatPercent(metrics.failureRate)}
        colorClass="text-destructive"
      />
      <MetricRow
        label="In-Flight Runs"
        value={String(metrics.inFlightRuns)}
        colorClass="text-active"
      />
    </div>
  );
}
