/**
 * The one fetch helper every client-side hook in this directory uses to
 * call this app's own same-origin Route Handlers (`src/app/api/runs/...`)
 * -- never `TriageApiClient` directly, which is server-only and holds the
 * bearer token. Throws with the response body attached so a caller (or
 * TanStack Query's own error state) can inspect what the Route Handler
 * relayed from the backend.
 */
export class FetchJsonError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`Request failed with status ${status}`);
    this.name = "FetchJsonError";
  }
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new FetchJsonError(response.status, body);
  }
  return response.json() as Promise<T>;
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  return fetchJson<T>(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
