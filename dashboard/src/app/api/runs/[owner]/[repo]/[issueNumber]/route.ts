import "server-only";

import { runIdentityParamsSchema } from "@/lib/api/params";
import { proxyToApi } from "@/lib/api/respond";
import { TriageApiClient } from "@/lib/api/triage-client";

// Next.js 15+ made dynamic route `params` a Promise -- must be awaited,
// not destructured directly off the context object.
type RouteContext = { params: Promise<{ owner: string; repo: string; issueNumber: string }> };

export async function GET(_request: Request, { params }: RouteContext) {
  return proxyToApi(async () => {
    const { owner, repo, issueNumber } = runIdentityParamsSchema.parse(await params);
    return new TriageApiClient().getRunDetail(owner, repo, issueNumber);
  });
}
