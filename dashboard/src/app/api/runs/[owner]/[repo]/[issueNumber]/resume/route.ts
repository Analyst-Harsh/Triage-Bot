import "server-only";

import { runIdentityParamsSchema } from "@/lib/api/params";
import { proxyToApi } from "@/lib/api/respond";
import { TriageApiClient } from "@/lib/api/triage-client";

type RouteContext = { params: Promise<{ owner: string; repo: string; issueNumber: string }> };

export async function GET(_request: Request, { params }: RouteContext) {
  return proxyToApi(async () => {
    const { owner, repo, issueNumber } = runIdentityParamsSchema.parse(await params);
    return new TriageApiClient().getPendingApproval(owner, repo, issueNumber);
  });
}

export async function POST(request: Request, { params }: RouteContext) {
  return proxyToApi(async () => {
    const { owner, repo, issueNumber } = runIdentityParamsSchema.parse(await params);
    // The decision body itself isn't re-validated by Zod -- ApprovalDecision
    // is exactly the kind of full-body contract that's FastAPI/Pydantic's
    // job, not duplicated here (see this file's sibling params.ts docstring).
    const decision = await request.json();
    return new TriageApiClient().submitDecision(owner, repo, issueNumber, decision);
  });
}
