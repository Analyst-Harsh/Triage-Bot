// @vitest-environment node
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { proxyToApi } from "./respond";
import { TriageApiError } from "./triage-client";

describe("proxyToApi", () => {
  it("returns a 200 JSON response with the resolved data", async () => {
    const response = await proxyToApi(async () => ({ ok: true }));
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it("relays a TriageApiError's status and body verbatim", async () => {
    const response = await proxyToApi(async () => {
      throw new TriageApiError(404, { detail: "no run found for this issue" });
    });
    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({ detail: "no run found for this issue" });
  });

  it("returns a 400 with the Zod issues when parsing throws inside the callback", async () => {
    const schema = z.object({ issueNumber: z.coerce.number().int().positive() });
    const response = await proxyToApi(async () => {
      const { issueNumber } = schema.parse({ issueNumber: "0" });
      return { issueNumber };
    });
    expect(response.status).toBe(400);
    const body = (await response.json()) as { detail: unknown };
    expect(Array.isArray(body.detail)).toBe(true);
  });

  it("rethrows a non-TriageApiError instead of swallowing it", async () => {
    await expect(
      proxyToApi(async () => {
        throw new Error("unexpected");
      }),
    ).rejects.toThrow("unexpected");
  });
});
