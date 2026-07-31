import { z } from "zod";

/**
 * Zod here validates only *shapes* at the Route Handler boundary (numeric
 * strings coerced to numbers, arrays vs. scalars) -- not full enum-value
 * correctness. FastAPI's own Pydantic layer already owns that boundary and
 * rejects an invalid value with its own 422; duplicating full runtime
 * validation on both sides of an internal proxy hop is dead weight, not
 * defense in depth.
 */

export const runIdentityParamsSchema = z.object({
  owner: z.string().min(1),
  repo: z.string().min(1),
  issueNumber: z.coerce.number().int().positive(),
});

export type RunIdentityParams = z.infer<typeof runIdentityParamsSchema>;

export const listRunsQuerySchema = z.object({
  status: z.array(z.string()).optional(),
  repo_full_name: z.string().optional(),
  source: z.string().optional(),
  period: z.string().optional(),
  page: z.coerce.number().int().positive().optional(),
  page_size: z.coerce.number().int().positive().optional(),
});

export const summaryQuerySchema = z.object({
  repo_full_name: z.string().optional(),
  period: z.string().optional(),
});

/** `URLSearchParams` collapses a repeated key into one value unless read via
 * `.getAll` -- `status` is the one param `GET /runs` accepts repeated
 * (`?status=failed&status=pending_approval`), so it needs `getAll`, every
 * other key just `.get`. */
export function parseListRunsQuery(searchParams: URLSearchParams) {
  return listRunsQuerySchema.parse({
    status: searchParams.getAll("status").length > 0 ? searchParams.getAll("status") : undefined,
    repo_full_name: searchParams.get("repo_full_name") ?? undefined,
    source: searchParams.get("source") ?? undefined,
    period: searchParams.get("period") ?? undefined,
    page: searchParams.get("page") ?? undefined,
    page_size: searchParams.get("page_size") ?? undefined,
  });
}

export function parseSummaryQuery(searchParams: URLSearchParams) {
  return summaryQuerySchema.parse({
    repo_full_name: searchParams.get("repo_full_name") ?? undefined,
    period: searchParams.get("period") ?? undefined,
  });
}
