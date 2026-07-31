import type { components } from "@/lib/api/schema";
import { outcomeDistribution } from "@/lib/post-outcome-summary";
import { SectionCard } from "./section-card";

type PostResults = components["schemas"]["PostResults"];

const OUTCOME_COLOR = {
  posted: "text-success",
  failed: "text-destructive",
  queued: "text-warning",
  rejected: "text-neutral",
} as const;

/** At-a-glance summary strip -- per-action outcome detail lives inline in
 * DraftSection, next to the action it actually posted (or didn't). */
export function PostResultsSection({ postResults }: { postResults: PostResults | null }) {
  const distribution = postResults ? outcomeDistribution(postResults.action_results) : null;

  return (
    <SectionCard title="Post Results" emptyLabel={distribution ? undefined : "Nothing posted yet."}>
      {distribution && (
        <div className="flex flex-wrap gap-4 text-sm">
          {(Object.keys(distribution) as (keyof typeof distribution)[]).map((outcome) => (
            <div key={outcome} className="flex items-baseline gap-1.5">
              <span className={`font-mono text-lg font-semibold ${OUTCOME_COLOR[outcome]}`}>
                {distribution[outcome]}
              </span>
              <span className="text-xs text-muted-foreground capitalize">{outcome}</span>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
