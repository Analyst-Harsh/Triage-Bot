"use client";

import { RotateCw } from "lucide-react";
import { RiskBadge } from "@/components/table/risk-badge";
import { StatusBadge } from "@/components/table/status-badge";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";
import { useRetryMutation } from "@/lib/query/hooks";
import { highestRiskLevel } from "@/lib/risk-summary";
import { cn } from "@/lib/utils";

type RunDetailResponse = components["schemas"]["RunDetailResponse"];

export function RunHeader({
  owner,
  repo,
  issueNumber,
  detail,
}: {
  owner: string;
  repo: string;
  issueNumber: number;
  detail: RunDetailResponse;
}) {
  const retryMutation = useRetryMutation(owner, repo, issueNumber);
  const overallRisk = detail.risk_assessment
    ? highestRiskLevel(detail.risk_assessment.action_assessments)
    : null;
  const hasTrace = Boolean(detail.run_meta?.trace_id);

  return (
    <div className="border-b border-border px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">
            {detail.run.repo_full_name} #{detail.run.issue_number}
          </p>
          <h1 className="font-heading text-xl font-semibold">{detail.run.issue_title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={detail.run.status} />
          {overallRisk && <RiskBadge risk={overallRisk} />}
          {hasTrace && (
            <a
              href="#trace"
              className="flex min-h-11 items-center rounded-lg border border-border px-3 text-sm hover:bg-muted sm:min-h-8"
            >
              Trace
            </a>
          )}
          {detail.run.status === "failed" && (
            <Button
              variant="outline"
              className="min-h-11 gap-1.5 sm:min-h-8"
              disabled={retryMutation.isPending}
              onClick={() => retryMutation.mutate({})}
            >
              <RotateCw
                className={cn("size-3.5", retryMutation.isPending && "animate-spin")}
                aria-hidden
              />
              {retryMutation.isPending ? "Retrying…" : "Retry"}
            </Button>
          )}
        </div>
      </div>
      {detail.run.error_message && (
        <p className="mt-2 text-sm text-destructive">{detail.run.error_message}</p>
      )}
    </div>
  );
}
