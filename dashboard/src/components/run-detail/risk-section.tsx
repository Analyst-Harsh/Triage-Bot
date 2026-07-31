import type { components } from "@/lib/api/schema";
import { riskDistribution } from "@/lib/risk-summary";
import { SectionCard } from "./section-card";

type RiskAssessment = components["schemas"]["RiskAssessment"];

const LEVEL_COLOR = { low: "text-success", medium: "text-warning", high: "text-destructive" } as const;

/** At-a-glance summary strip -- per-action risk detail lives inline in
 * DraftSection, next to the action it actually assesses. */
export function RiskSection({ riskAssessment }: { riskAssessment: RiskAssessment | null }) {
  const distribution = riskAssessment ? riskDistribution(riskAssessment.action_assessments) : null;

  return (
    <SectionCard title="Risk" emptyLabel={distribution ? undefined : "Not assessed yet."}>
      {distribution && (
        <div className="flex gap-4 text-sm">
          {(Object.keys(distribution) as (keyof typeof distribution)[]).map((level) => (
            <div key={level} className="flex items-baseline gap-1.5">
              <span className={`font-mono text-lg font-semibold ${LEVEL_COLOR[level]}`}>
                {distribution[level]}
              </span>
              <span className="text-xs text-muted-foreground capitalize">{level}</span>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
