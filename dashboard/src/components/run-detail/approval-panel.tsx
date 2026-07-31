"use client";

import { useState } from "react";
import { RiskBadge } from "@/components/table/risk-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api/schema";
import { useApprovalMutation, usePendingApprovalQuery } from "@/lib/query/hooks";
import { cn } from "@/lib/utils";
import { DiffViewer } from "./diff-viewer";
import { SectionCard } from "./section-card";

type QueuedActionSummary = components["schemas"]["QueuedActionSummary"];

type Decision = { approved: boolean; note: string };
type DecisionState = Record<number, Decision>;

function QueuedActionRow({
  action,
  decision,
  onApprovedChange,
  onNoteChange,
}: {
  action: QueuedActionSummary;
  decision: Decision | undefined;
  onApprovedChange: (approved: boolean) => void;
  onNoteChange: (note: string) => void;
}) {
  return (
    <div className="space-y-2.5 rounded-lg bg-muted/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="capitalize">
          {action.action_type.replaceAll("_", " ")}
        </Badge>
        <RiskBadge risk={action.risk_level} />
      </div>
      <p className="text-sm">{action.summary}</p>
      <p className="text-sm text-muted-foreground">{action.rationale}</p>
      <p className="text-xs text-muted-foreground">{action.risk_reasoning}</p>
      {action.diff_preview && (
        <div className="space-y-1">
          <DiffViewer diff={action.diff_preview} />
          {action.diff_truncated && (
            <p className="text-xs text-muted-foreground">
              Preview truncated -- see the full diff once this run completes.
            </p>
          )}
        </div>
      )}
      <div className="flex min-h-11 items-center gap-2 sm:min-h-8">
        <Button
          type="button"
          size="sm"
          variant={decision?.approved === true ? "default" : "outline"}
          className={cn(
            "min-h-11 sm:min-h-7",
            decision?.approved === true && "bg-success text-white hover:bg-success/90",
          )}
          onClick={() => onApprovedChange(true)}
        >
          Approve
        </Button>
        <Button
          type="button"
          size="sm"
          variant={decision?.approved === false ? "destructive" : "outline"}
          className="min-h-11 sm:min-h-7"
          onClick={() => onApprovedChange(false)}
        >
          Reject
        </Button>
      </div>
      {decision !== undefined && (
        <div>
          <label
            className="mb-1 block text-xs font-medium text-muted-foreground"
            htmlFor={`note-${action.index}`}
          >
            Note (optional)
          </label>
          <Textarea
            id={`note-${action.index}`}
            rows={2}
            value={decision.note}
            onChange={(event) => onNoteChange(event.target.value)}
          />
        </div>
      )}
    </div>
  );
}

export function ApprovalPanel({
  owner,
  repo,
  issueNumber,
}: {
  owner: string;
  repo: string;
  issueNumber: number;
}) {
  const pendingQuery = usePendingApprovalQuery(owner, repo, issueNumber);
  const approvalMutation = useApprovalMutation(owner, repo, issueNumber);
  const [decisions, setDecisions] = useState<DecisionState>({});

  if (pendingQuery.isPending) {
    return (
      <SectionCard title="Approval">
        <Skeleton className="h-32 w-full" />
      </SectionCard>
    );
  }

  if (pendingQuery.isError || !pendingQuery.data) {
    return (
      <SectionCard title="Approval" emptyLabel="Nothing pending approval.">
        {null}
      </SectionCard>
    );
  }

  const actions = pendingQuery.data.actions;
  // Safety-critical: this posts to real GitHub -- submit stays disabled
  // until every queued index has an explicit approve/reject decision, per
  // the backend's own exact-index-set requirement (ApprovalDecision must
  // cover every queued action, no partial submissions).
  const allDecided = actions.every((action) => decisions[action.index] !== undefined);

  return (
    <SectionCard title="Approval">
      <div className="space-y-3">
        {actions.map((action) => (
          <QueuedActionRow
            key={action.index}
            action={action}
            decision={decisions[action.index]}
            onApprovedChange={(approved) =>
              setDecisions((prev) => ({
                ...prev,
                [action.index]: { approved, note: prev[action.index]?.note ?? "" },
              }))
            }
            onNoteChange={(note) =>
              setDecisions((prev) => ({
                ...prev,
                [action.index]: { approved: prev[action.index]?.approved ?? false, note },
              }))
            }
          />
        ))}

        <Button
          className="min-h-11"
          disabled={!allDecided || approvalMutation.isPending}
          onClick={() =>
            approvalMutation.mutate({
              decisions: actions.map((action) => ({
                index: action.index,
                approved: decisions[action.index]?.approved ?? false,
                note: decisions[action.index]?.note || null,
              })),
            })
          }
        >
          {approvalMutation.isPending ? "Submitting…" : "Submit decisions"}
        </Button>
        {!allDecided && (
          <p className="text-xs text-muted-foreground">
            Decide on every action above before submitting.
          </p>
        )}
      </div>
    </SectionCard>
  );
}
