import { notFound } from "next/navigation";
import { RunDetailContent } from "@/components/run-detail/run-detail-content";
import { Sidebar } from "@/components/layout/sidebar";
import { TriageApiClient, TriageApiError } from "@/lib/api/triage-client";

type RouteParams = { owner: string; repo: string; issueNumber: string };

export default async function RunDetailPage({
  params,
}: {
  params: Promise<RouteParams>;
}) {
  const { owner, repo, issueNumber } = await params;
  const parsedIssueNumber = Number(issueNumber);
  if (!Number.isInteger(parsedIssueNumber) || parsedIssueNumber <= 0) {
    notFound();
  }

  const client = new TriageApiClient();
  let detail;
  try {
    detail = await client.getRunDetail(owner, repo, parsedIssueNumber);
  } catch (error) {
    if (error instanceof TriageApiError && error.status === 404) {
      notFound();
    }
    throw error;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <RunDetailContent
        owner={owner}
        repo={repo}
        issueNumber={parsedIssueNumber}
        initialDetail={detail}
      />
    </div>
  );
}
