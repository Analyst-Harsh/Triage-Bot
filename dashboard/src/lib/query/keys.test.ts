import { describe, expect, it } from "vitest";
import { queryKeys } from "./keys";

describe("queryKeys", () => {
  it("reflects every runs-list filter in the key", () => {
    const key = queryKeys.runs({
      status: ["failed", "pending_approval"],
      repoFullName: "octo/repo",
      source: "webhook",
      period: "24h",
      page: 2,
      pageSize: 20,
    });
    expect(key).toEqual([
      "runs",
      {
        status: ["failed", "pending_approval"],
        repoFullName: "octo/repo",
        source: "webhook",
        period: "24h",
        page: 2,
        pageSize: 20,
      },
    ]);
  });

  it("produces different keys for different filter values", () => {
    const a = queryKeys.runs({ page: 1 });
    const b = queryKeys.runs({ page: 2 });
    expect(a).not.toEqual(b);
  });

  it("reflects period and repoFullName in the summary key", () => {
    expect(queryKeys.summary("24h", "octo/repo")).toEqual([
      "runs-summary",
      "24h",
      "octo/repo",
    ]);
    expect(queryKeys.summary(undefined, undefined)).toEqual(["runs-summary", undefined, undefined]);
  });

  it("keeps the sidebar's all-time health key distinct from a period-scoped summary key", () => {
    const health = queryKeys.liveHealthSummary();
    const scoped = queryKeys.summary(undefined, undefined);
    expect(health).not.toEqual(scoped);
  });

  it("reflects owner/repo/issueNumber in run-identity keys", () => {
    expect(queryKeys.runDetail("octo", "repo", 42)).toEqual(["run-detail", "octo", "repo", 42]);
    expect(queryKeys.pendingApproval("octo", "repo", 42)).toEqual([
      "pending-approval",
      "octo",
      "repo",
      42,
    ]);
    expect(queryKeys.traceSummary("octo", "repo", 42)).toEqual([
      "trace-summary",
      "octo",
      "repo",
      42,
    ]);
  });

  it("produces different run-identity keys for different issue numbers", () => {
    expect(queryKeys.runDetail("octo", "repo", 1)).not.toEqual(
      queryKeys.runDetail("octo", "repo", 2),
    );
  });
});
