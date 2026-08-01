import { Sidebar } from "@/components/layout/sidebar";
import { RunsTableSkeleton } from "@/components/table/runs-table-skeleton";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * This is what streams in immediately on every navigation, before
 * `page.tsx`'s data fetch resolves -- it used to end in one arbitrary
 * `h-96` block standing in for the status bar + table + pagination
 * combined. On a normal-sized dashboard that block is taller than the real
 * content it's replaced by, so `main`'s `overflow-y-auto` briefly needed to
 * scroll for this skeleton and then didn't once the (shorter) real content
 * swapped in -- a real, deterministic vertical-scrollbar flash on every
 * refresh. Reusing the actual `RunsTableSkeleton` (already sized to match
 * the real table) instead of a guessed block removes that mismatch.
 */
export default function DashboardLoading() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 space-y-6 p-6">
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-24 w-full" />
        <RunsTableSkeleton />
      </div>
    </div>
  );
}
