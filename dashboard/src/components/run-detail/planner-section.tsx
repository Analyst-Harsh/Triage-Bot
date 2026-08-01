import type { components } from "@/lib/api/schema";
import { SectionCard } from "./section-card";

type PlannerOutput = components["schemas"]["PlannerOutput"];

export function PlannerSection({ planner }: { planner: PlannerOutput | null }) {
  return (
    <SectionCard title="Planner" emptyLabel={planner ? undefined : "Not planned yet."}>
      {planner && (
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium capitalize">
              {planner.issue_type.replaceAll("_", " ")}
            </span>
            <span className="text-xs text-muted-foreground">
              {(planner.classification_confidence * 100).toFixed(0)}% confidence
            </span>
          </div>
          <p className="text-muted-foreground">{planner.reasoning}</p>
          {planner.investigation_plan && planner.investigation_plan.length > 0 && (
            <ol className="list-decimal space-y-1 pl-4 text-muted-foreground">
              {planner.investigation_plan.map((step, index) => (
                <li key={index}>{step}</li>
              ))}
            </ol>
          )}
        </div>
      )}
    </SectionCard>
  );
}
