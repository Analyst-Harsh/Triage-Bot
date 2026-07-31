"use client";

import type { components } from "@/lib/api/schema";
import { useRunDetailQuery } from "@/lib/query/hooks";
import { ApprovalPanel } from "./approval-panel";
import { DraftSection } from "./draft-section";
import { EpisodicMemorySection } from "./episodic-memory-section";
import { PlannerSection } from "./planner-section";
import { PostResultsSection } from "./post-results-section";
import { ResearchSection } from "./research-section";
import { RiskSection } from "./risk-section";
import { RunHeader } from "./run-header";
import { TraceSummaryPanel } from "./trace-summary-panel";

type RunDetailResponse = components["schemas"]["RunDetailResponse"];

export function RunDetailContent({
  owner,
  repo,
  issueNumber,
  initialDetail,
}: {
  owner: string;
  repo: string;
  issueNumber: number;
  initialDetail: RunDetailResponse;
}) {
  const detailQuery = useRunDetailQuery(owner, repo, issueNumber, initialDetail);
  const detail = detailQuery.data ?? initialDetail;

  return (
    <div className="flex-1">
      <RunHeader owner={owner} repo={repo} issueNumber={issueNumber} detail={detail} />
      <main className="space-y-4 p-6">
        {detail.run.status === "pending_approval" && (
          <ApprovalPanel owner={owner} repo={repo} issueNumber={issueNumber} />
        )}
        <PlannerSection planner={detail.planner_output} />
        <ResearchSection research={detail.research_findings} />
        <DraftSection
          draft={detail.draft}
          riskAssessment={detail.risk_assessment}
          postResults={detail.post_results}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <RiskSection riskAssessment={detail.risk_assessment} />
          <PostResultsSection postResults={detail.post_results} />
        </div>
        <EpisodicMemorySection hits={detail.episodic_context} />
        <TraceSummaryPanel
          owner={owner}
          repo={repo}
          issueNumber={issueNumber}
          enabled={Boolean(detail.run_meta?.trace_id)}
        />
      </main>
    </div>
  );
}
