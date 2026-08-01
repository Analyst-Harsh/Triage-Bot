"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import {
  DEFAULT_PAGE,
  type DashboardFilters,
  parseDashboardFilters,
  serializeDashboardFilters,
} from "@/lib/dashboard-filters";

export function useDashboardFilters() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const filters = useMemo(() => parseDashboardFilters(searchParams), [searchParams]);

  const setFilters = useCallback(
    (next: Partial<DashboardFilters>) => {
      const merged: DashboardFilters = {
        ...filters,
        ...next,
        // Changing a filter re-scopes the result set -- start back at page 1
        // unless the caller is explicitly setting the page itself.
        page: "page" in next ? (next.page ?? DEFAULT_PAGE) : DEFAULT_PAGE,
      };
      const query = serializeDashboardFilters(merged);
      router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [filters, pathname, router],
  );

  return { filters, setFilters };
}
