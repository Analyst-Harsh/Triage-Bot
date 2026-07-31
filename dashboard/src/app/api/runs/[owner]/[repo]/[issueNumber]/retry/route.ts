import "server-only";

import { runIdentityParamsSchema } from "@/lib/api/params";
import { proxyToApi } from "@/lib/api/respond";
import { TriageApiClient } from "@/lib/api/triage-client";

type RouteContext = { params: Promise<{ owner: string; repo: string; issueNumber: string }> };

export async function POST(request: Request, { params }: RouteContext) {
  return proxyToApi(async () => {
    const { owner, repo, issueNumber } = runIdentityParamsSchema.parse(await params);
    const body = await request.json().catch(() => ({}));
    return new TriageApiClient().retryRun(owner, repo, issueNumber, body);
  });
}
