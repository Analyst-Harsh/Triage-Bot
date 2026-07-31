import type { components } from "@/lib/api/schema";
import { DraftActionCard } from "./draft-action-card";
import { SectionCard } from "./section-card";

type DraftOutput = components["schemas"]["DraftOutput"];
type RiskAssessment = components["schemas"]["RiskAssessment"];
type PostResults = components["schemas"]["PostResults"];

/**
 * `risk_assessment.action_assessments` and `post_results.action_results`
 * are positionally aligned against `draft.actions` (same index, per the
 * backend's own schema docstrings) -- zipped together here so each action
 * renders with its own risk/outcome inline, rather than three disconnected
 * index-aligned lists the reader has to mentally cross-reference.
 */
export function DraftSection({
  draft,
  riskAssessment,
  postResults,
}: {
  draft: DraftOutput | null;
  riskAssessment: RiskAssessment | null;
  postResults: PostResults | null;
}) {
  return (
    <SectionCard title="Draft" emptyLabel={draft ? undefined : "Not drafted yet."}>
      {draft && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{draft.overall_rationale}</p>
          <div className="space-y-2.5">
            {draft.actions.map((drafted, index) => (
              <DraftActionCard
                key={index}
                drafted={drafted}
                risk={riskAssessment?.action_assessments[index]}
                postResult={postResults?.action_results[index]}
              />
            ))}
          </div>
          {draft.unsupported_claims && draft.unsupported_claims.length > 0 && (
            <div className="rounded-lg bg-warning/10 p-2.5 text-xs text-warning">
              <p className="font-medium">Unsupported claims flagged by grounding check:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {draft.unsupported_claims.map((claim, index) => (
                  <li key={index}>{claim}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}
