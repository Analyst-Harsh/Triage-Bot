import type { components } from "@/lib/api/schema";
import { StatusBadge } from "@/components/table/status-badge";
import { SectionCard } from "./section-card";

type EpisodicMemoryHit = components["schemas"]["EpisodicMemoryHit"];

export function EpisodicMemorySection({ hits }: { hits: EpisodicMemoryHit[] }) {
  return (
    <SectionCard title="Similar Past Issues" emptyLabel={hits.length === 0 ? "None found." : undefined}>
      {hits.length > 0 && (
        <ul className="space-y-2">
          {hits.map((hit, index) => (
            <li key={index} className="rounded-lg bg-muted/40 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-muted-foreground">
                  {hit.past_repo}#{hit.past_issue_number}
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {Math.round(hit.similarity_score * 100)}% similar
                  </span>
                  <StatusBadge status={hit.outcome} />
                </div>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{hit.summary}</p>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
