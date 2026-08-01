import "server-only";

import { NextResponse } from "next/server";
import { ZodError } from "zod";
import { TriageApiError } from "./triage-client";

/**
 * Every Route Handler in `src/app/api/runs/...` is a one-liner around this
 * -- the callback does both the Zod param/query parse *and* the
 * `TriageApiClient` call, so a malformed route (bad `issueNumber`, etc.)
 * gets a clean 400 here rather than an opaque uncaught 500, on the same
 * path a `TriageApiError` relays its upstream status + body verbatim.
 * Anything else (a real bug) still surfaces as an uncaught 500 rather than
 * being silently swallowed.
 */
export async function proxyToApi<T>(request: () => Promise<T>): Promise<NextResponse> {
  try {
    const data = await request();
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof TriageApiError) {
      return NextResponse.json(error.body, { status: error.status });
    }
    if (error instanceof ZodError) {
      return NextResponse.json({ detail: error.issues }, { status: 400 });
    }
    throw error;
  }
}
