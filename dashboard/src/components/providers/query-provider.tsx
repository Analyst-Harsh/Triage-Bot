"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { getQueryClient } from "@/lib/query/get-query-client";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // useState (not useMemo) so the client survives Strict Mode's
  // double-invoke without being recreated -- the documented TanStack Query
  // Next.js pattern.
  const [queryClient] = useState(() => getQueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
