import "server-only";

import createClient from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Thrown by every `TriageApiClient` method on a non-2xx response. `body` is
 * whatever JSON the FastAPI backend returned -- most routes wrap it as
 * `{"detail": {...}}` via `api/errors.py::to_http_exception`, but a few
 * (the bearer-token dependency's own 401/503) return a bare
 * `{"detail": "<string>"}` instead. Never assume one shape; callers that
 * need the message read `body` defensively.
 */
export class TriageApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`Triage API request failed with status ${status}`);
    this.name = "TriageApiError";
  }
}

export type Query<Path extends keyof paths> = paths[Path] extends {
  get: { parameters: { query?: infer Q } };
}
  ? Q
  : never;

/**
 * The one class every server-side call into the FastAPI operator API goes
 * through -- Server Components import this directly; Route Handlers (the
 * only thing Client Components are allowed to call) use it internally and
 * relay the result. `server-only` at the top is a build-time guard: it
 * hard-fails the build if a `'use client'` component ever imports this file
 * by mistake, since `TRIAGE_API_BEARER_TOKEN` must never reach the browser.
 */
export class TriageApiClient {
  private readonly client: ReturnType<typeof createClient<paths>>;

  constructor() {
    const baseUrl = process.env.TRIAGE_API_BASE_URL;
    const token = process.env.TRIAGE_API_BEARER_TOKEN;
    if (!baseUrl || !token) {
      throw new Error(
        "TRIAGE_API_BASE_URL and TRIAGE_API_BEARER_TOKEN must both be set (see dashboard/README.md)",
      );
    }
    this.client = createClient<paths>({
      baseUrl,
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async listRuns(query: Query<"/runs">) {
    return this.unwrap(this.client.GET("/runs", { params: { query } }));
  }

  async getSummary(query: Query<"/runs/summary">) {
    return this.unwrap(this.client.GET("/runs/summary", { params: { query } }));
  }

  async getRunDetail(owner: string, repo: string, issueNumber: number) {
    return this.unwrap(
      this.client.GET("/runs/{owner}/{repo}/{issue_number}", {
        params: { path: { owner, repo, issue_number: issueNumber } },
      }),
    );
  }

  async getTraceSummary(owner: string, repo: string, issueNumber: number) {
    return this.unwrap(
      this.client.GET("/runs/{owner}/{repo}/{issue_number}/trace", {
        params: { path: { owner, repo, issue_number: issueNumber } },
      }),
    );
  }

  async getPendingApproval(owner: string, repo: string, issueNumber: number) {
    return this.unwrap(
      this.client.GET("/runs/{owner}/{repo}/{issue_number}/resume", {
        params: { path: { owner, repo, issue_number: issueNumber } },
      }),
    );
  }

  async submitDecision(
    owner: string,
    repo: string,
    issueNumber: number,
    decision: paths["/runs/{owner}/{repo}/{issue_number}/resume"]["post"]["requestBody"]["content"]["application/json"],
  ) {
    return this.unwrap(
      this.client.POST("/runs/{owner}/{repo}/{issue_number}/resume", {
        params: { path: { owner, repo, issue_number: issueNumber } },
        body: decision,
      }),
    );
  }

  async retryRun(
    owner: string,
    repo: string,
    issueNumber: number,
    body: paths["/runs/{owner}/{repo}/{issue_number}/retry"]["post"]["requestBody"]["content"]["application/json"],
  ) {
    return this.unwrap(
      this.client.POST("/runs/{owner}/{repo}/{issue_number}/retry", {
        params: { path: { owner, repo, issue_number: issueNumber } },
        body,
      }),
    );
  }

  private async unwrap<T>(
    request: Promise<{ data?: T; error?: unknown; response: Response }>,
  ): Promise<T> {
    const { data, error, response } = await request;
    if (error !== undefined) {
      throw new TriageApiError(response.status, error);
    }
    if (data === undefined) {
      throw new TriageApiError(response.status, null);
    }
    return data;
  }
}
