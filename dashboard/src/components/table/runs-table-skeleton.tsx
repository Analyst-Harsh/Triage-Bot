import { Skeleton } from "@/components/ui/skeleton";

export function RunsTableSkeleton() {
  return (
    <div className="space-y-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}
