"use client";

import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/schema";
import { useTraceSummaryQuery } from "@/lib/query/hooks";
import { computeObservationDepths } from "@/lib/trace-depth";
import { cn } from "@/lib/utils";
import { SectionCard } from "./section-card";

type TraceObservation = components["schemas"]["TraceObservation"];

const COLLAPSE_THRESHOLD = 20;

function formatSeconds(seconds: number | null): string {
  return seconds === null ? "—" : `${seconds.toFixed(2)}s`;
}

function formatCost(cost: number | null): string {
  return cost === null ? "—" : `$${cost.toFixed(4)}`;
}

function ObservationRow({ observation, depth }: { observation: TraceObservation; depth: number }) {
  return (
    <div
      className="flex items-center justify-between gap-3 border-b border-border/50 py-1.5 text-xs last:border-0"
      style={{ paddingLeft: Math.min(depth, 8) * 12 }}
    >
      <div className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-secondary-foreground">
          {observation.observation_type}
        </span>
        <span className="truncate">{observation.name ?? observation.observation_id}</span>
      </div>
      <div className="flex shrink-0 items-center gap-3 font-mono text-muted-foreground">
        <span>{formatSeconds(observation.latency_seconds)}</span>
        <span>{formatCost(observation.cost_usd)}</span>
      </div>
    </div>
  );
}

function TraceObservationList({ observations }: { observations: TraceObservation[] }) {
  const [open, setOpen] = useState(observations.length <= COLLAPSE_THRESHOLD);
  const depths = computeObservationDepths(observations);
  const sorted = [...observations].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime(),
  );

  if (observations.length <= COLLAPSE_THRESHOLD) {
    return (
      <div>
        {sorted.map((observation) => (
          <ObservationRow
            key={observation.observation_id}
            observation={observation}
            depth={depths.get(observation.observation_id) ?? 0}
          />
        ))}
      </div>
    );
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex min-h-11 w-full items-center justify-between text-xs text-muted-foreground sm:min-h-8">
        {observations.length} observations
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} aria-hidden />
      </CollapsibleTrigger>
      <CollapsibleContent>
        {sorted.map((observation) => (
          <ObservationRow
            key={observation.observation_id}
            observation={observation}
            depth={depths.get(observation.observation_id) ?? 0}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function TraceSummaryPanel({
  owner,
  repo,
  issueNumber,
  enabled,
}: {
  owner: string;
  repo: string;
  issueNumber: number;
  enabled: boolean;
}) {
  const query = useTraceSummaryQuery(owner, repo, issueNumber, { enabled });

  if (!enabled) {
    return null;
  }

  return (
    <div id="trace">
      <SectionCard
        title="Trace"
        action={
          query.data && (
            <a
              href={query.data.langfuse_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              View full trace in Langfuse
              <ExternalLink className="size-3" aria-hidden />
            </a>
          )
        }
        emptyLabel={
          query.isError ? "Trace unavailable for this run." : undefined
        }
      >
        {query.isPending && (
          <div className="space-y-1.5">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        )}
        {query.data && (
          <div className="space-y-3">
            <div className="flex gap-6 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Total latency</p>
                <p className="font-mono">{formatSeconds(query.data.total_latency_seconds)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total cost</p>
                <p className="font-mono">{formatCost(query.data.total_cost_usd)}</p>
              </div>
            </div>
            <TraceObservationList observations={query.data.observations} />
          </div>
        )}
      </SectionCard>
    </div>
  );
}
