import "server-only";

import { runIdentityParamsSchema } from "@/lib/api/params";
import { proxyToApi } from "@/lib/api/respond";
import { TriageApiClient } from "@/lib/api/triage-client";

type RouteContext = { params: Promise<{ owner: string; repo: string; issueNumber: string }> };

export async function GET(_request: Request, { params }: RouteContext) {
  return proxyToApi(async () => {
    const { owner, repo, issueNumber } = runIdentityParamsSchema.parse(await params);
    return new TriageApiClient().getTraceSummary(owner, repo, issueNumber);
  });
}
