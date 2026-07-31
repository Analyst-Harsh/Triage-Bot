import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";

export function SectionCard({
  title,
  action,
  children,
  emptyLabel,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  /** Rendered instead of `children` when the corresponding `RunDetailResponse`
   * field is `null` -- every field is null in the narrow window between
   * webhook acceptance and the graph's first checkpoint superstep. */
  emptyLabel?: string;
}) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-heading text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {emptyLabel ? <p className="text-sm text-muted-foreground">{emptyLabel}</p> : children}
    </Card>
  );
}
