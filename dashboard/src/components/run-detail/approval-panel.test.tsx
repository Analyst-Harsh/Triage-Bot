// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApprovalPanel } from "./approval-panel";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

const APPROVAL_REQUEST = {
  run_id: "11111111-1111-1111-1111-111111111111",
  repo_full_name: "octo/repo",
  issue_number: 42,
  issue_url: "https://github.com/octo/repo/issues/42",
  requested_at: new Date().toISOString(),
  actions: [
    {
      index: 0,
      action_type: "comment",
      summary: "Post a comment",
      rationale: "r",
      risk_level: "low",
      risk_reasoning: "rr",
      diff_truncated: false,
    },
    {
      index: 1,
      action_type: "label",
      summary: "Add a label",
      rationale: "r2",
      risk_level: "medium",
      risk_reasoning: "rr2",
      diff_truncated: false,
    },
  ],
};

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApprovalPanel owner="octo" repo="repo" issueNumber={42} />
    </QueryClientProvider>,
  );
}

describe("ApprovalPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps Submit disabled until every queued action has a decision", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(APPROVAL_REQUEST)),
    );
    renderPanel();

    const submit = await screen.findByRole("button", { name: /submit decisions/i });
    expect(submit).toBeDisabled();

    const approveButtons = screen.getAllByRole("button", { name: /^approve$/i });
    fireEvent.click(approveButtons[0]);
    expect(submit).toBeDisabled(); // only 1 of 2 actions decided

    const rejectButtons = screen.getAllByRole("button", { name: /^reject$/i });
    fireEvent.click(rejectButtons[1]);
    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  it("shows a note field only for an action that has been decided", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(APPROVAL_REQUEST)),
    );
    renderPanel();

    await screen.findByRole("button", { name: /submit decisions/i });
    expect(screen.queryByLabelText(/note/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /^approve$/i })[0]);
    expect(await screen.findAllByLabelText(/note/i)).toHaveLength(1);
  });

  it("renders an empty state when nothing is pending", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "nothing pending" }), { status: 404 })),
    );
    renderPanel();

    expect(await screen.findByText(/nothing pending approval/i)).toBeInTheDocument();
  });
});
