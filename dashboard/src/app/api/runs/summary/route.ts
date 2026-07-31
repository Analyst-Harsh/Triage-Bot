import "server-only";

import type { NextRequest } from "next/server";
import { parseSummaryQuery } from "@/lib/api/params";
import { proxyToApi } from "@/lib/api/respond";
import { TriageApiClient } from "@/lib/api/triage-client";
import type { Query } from "@/lib/api/triage-client";

export async function GET(request: NextRequest) {
  return proxyToApi(() => {
    const query = parseSummaryQuery(request.nextUrl.searchParams);
    return new TriageApiClient().getSummary(query as Query<"/runs/summary">);
  });
}
