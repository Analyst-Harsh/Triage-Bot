import { QueryClient, environmentManager } from "@tanstack/react-query";

/**
 * Standard TanStack Query Next.js App Router pattern: the server always
 * gets a fresh `QueryClient` per request (Server Components run in a
 * request-scoped context, so a module-level singleton would leak state
 * across requests/users); the browser gets one long-lived singleton so
 * client-side cache/polling state survives re-renders and navigations.
 */
function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

export function getQueryClient(): QueryClient {
  if (environmentManager.isServer()) {
    return makeQueryClient();
  }
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}
