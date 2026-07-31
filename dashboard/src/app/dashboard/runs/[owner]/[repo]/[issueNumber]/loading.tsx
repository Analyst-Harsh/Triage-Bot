import { Sidebar } from "@/components/layout/sidebar";
import { Skeleton } from "@/components/ui/skeleton";

export default function RunDetailLoading() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 space-y-4 p-6">
        <Skeleton className="h-16 w-full" />
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
    </div>
  );
}
