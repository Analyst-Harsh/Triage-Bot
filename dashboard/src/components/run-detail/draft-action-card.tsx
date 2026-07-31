import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/table/risk-badge";
import type { components } from "@/lib/api/schema";
import { DiffViewer } from "./diff-viewer";

type DraftedAction = components["schemas"]["DraftedAction"];
type ActionRiskAssessment = components["schemas"]["ActionRiskAssessment"];
type ActionPostResult = components["schemas"]["ActionPostResult"];

const OUTCOME_ICON = {
  posted: CheckCircle2,
  failed: XCircle,
  queued: Clock,
  rejected: XCircle,
} as const;

const OUTCOME_COLOR = {
  posted: "text-success",
  failed: "text-destructive",
  queued: "text-warning",
  rejected: "text-neutral",
} as const;

function ActionBody({ action }: { action: DraftedAction["action"] }) {
  switch (action.action_type) {
    case "comment":
      return <p className="whitespace-pre-wrap text-sm text-muted-foreground">{action.comment_body}</p>;
    case "label":
      return (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {action.labels_to_add?.map((label) => (
            <Badge key={`add-${label}`} variant="outline" className="text-success">
              +{label}
            </Badge>
          ))}
          {action.labels_to_remove?.map((label) => (
            <Badge key={`remove-${label}`} variant="outline" className="text-destructive">
              -{label}
            </Badge>
          ))}
        </div>
      );
    case "close":
      return (
        <div className="space-y-1 text-sm">
          <p className="text-muted-foreground">Reason: {action.reason}</p>
          {action.close_comment && (
            <p className="whitespace-pre-wrap text-muted-foreground">{action.close_comment}</p>
          )}
        </div>
      );
    case "code_fix":
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className={action.sandbox_result.passed ? "text-success" : "text-destructive"}>
              Sandbox {action.sandbox_result.passed ? "passed" : "failed"}
            </span>
            <span className="font-mono">{action.base_ref}@{action.base_commit_sha.slice(0, 7)}</span>
            <span>{action.target_files.length} file(s)</span>
          </div>
          <DiffViewer diff={action.diff} />
        </div>
      );
  }
}

export function DraftActionCard({
  drafted,
  risk,
  postResult,
}: {
  drafted: DraftedAction;
  risk?: ActionRiskAssessment;
  postResult?: ActionPostResult;
}) {
  const OutcomeIcon = postResult ? OUTCOME_ICON[postResult.outcome] : null;

  return (
    <div className="space-y-2.5 rounded-lg bg-muted/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="capitalize">
            {drafted.action.action_type.replaceAll("_", " ")}
          </Badge>
          {risk && <RiskBadge risk={risk.level} />}
        </div>
        {postResult && OutcomeIcon && (
          <span
            className={`flex items-center gap-1 text-xs font-medium capitalize ${OUTCOME_COLOR[postResult.outcome]}`}
          >
            <OutcomeIcon className="size-3.5" aria-hidden />
            {postResult.outcome}
            {/* `detail` is a URL only for a real `posted` outcome (comment/PR
                link) -- for failed/rejected it's an error message or reviewer
                note, plain text, never a link. */}
            {postResult.outcome === "posted" && postResult.detail && (
              <a href={postResult.detail} target="_blank" rel="noreferrer" className="underline">
                (view)
              </a>
            )}
          </span>
        )}
      </div>
      <p className="text-sm text-muted-foreground">{drafted.rationale}</p>
      <ActionBody action={drafted.action} />
      {postResult && postResult.outcome !== "posted" && postResult.detail && (
        <p className="text-xs text-muted-foreground italic">{postResult.detail}</p>
      )}
      {risk && risk.risk_factors && risk.risk_factors.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Risk factors: {risk.risk_factors.join(", ")}
        </p>
      )}
    </div>
  );
}
