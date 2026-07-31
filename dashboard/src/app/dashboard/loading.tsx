import { Sidebar } from "@/components/layout/sidebar";
import { Skeleton } from "@/components/ui/skeleton";

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
        <Skeleton className="h-96 w-full" />
      </div>
    </div>
  );
}
