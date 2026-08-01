"use client";

import { motion } from "motion/react";
import { Card } from "@/components/ui/card";
import type { components } from "@/lib/api/schema";
import { useRunsSummaryQuery } from "@/lib/query/hooks";
import { getStatusVisual } from "@/lib/status";
import { deriveStatusDistribution } from "@/lib/status-distribution";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { cn } from "@/lib/utils";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

/**
 * Turns the same `/runs/summary` data `StatCardsRow` already fetches (same
 * query key, so this never issues a second network request) into a single
 * proportional strip -- the four stat cards show absolute counts, this
 * shows the *shape* of the period's run mix at a glance. Segment widths are
 * the primary signal, but every status also gets a visible text label +
 * count underneath, per the "don't rely on color alone" chart guidance.
 */
export function StatusDistributionBar({
  period,
  initialSummary,
}: {
  period: string | undefined;
  initialSummary?: RunSummaryResponse;
}) {
  const summaryQuery = useRunsSummaryQuery(period, undefined, initialSummary);
  const reducedMotion = useReducedMotion();

  if (!summaryQuery.data) {
    return null;
  }

  const segments = deriveStatusDistribution(summaryQuery.data);
  if (segments.length === 0) {
    return null;
  }

  return (
    <Card className="gap-3 p-4 sm:p-5">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Status Mix</p>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {segments.map((segment) => {
          const visual = getStatusVisual(segment.status);
          return (
            <motion.div
              key={segment.status}
              className={cn("h-full", visual.dotClass)}
              initial={reducedMotion ? false : { width: 0 }}
              animate={{ width: `${segment.percent}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {segments.map((segment) => {
          const visual = getStatusVisual(segment.status);
          return (
            <div key={segment.status} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={cn("size-1.5 shrink-0 rounded-full", visual.dotClass)} aria-hidden />
              {visual.label}
              <span className="font-mono tabular-nums text-foreground/80">{segment.count}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
