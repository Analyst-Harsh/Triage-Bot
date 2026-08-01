import "server-only";

import type { NextRequest } from "next/server";
import { parseListRunsQuery } from "@/lib/api/params";
import { proxyToApi } from "@/lib/api/respond";
import { TriageApiClient } from "@/lib/api/triage-client";
import type { Query } from "@/lib/api/triage-client";

export async function GET(request: NextRequest) {
  return proxyToApi(() => {
    const query = parseListRunsQuery(request.nextUrl.searchParams);
    // Zod validated shape (array-ness, numeric coercion); FastAPI validates
    // the actual enum values and returns its own 422 on a bad one -- this
    // cast just bridges Zod's intentionally looser `string[]` to the
    // generated client's literal-union type, per this file's boundary split.
    return new TriageApiClient().listRuns(query as Query<"/runs">);
  });
}
