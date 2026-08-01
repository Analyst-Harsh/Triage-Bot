"use client";

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export function SectionCard({
  title,
  action,
  children,
  emptyLabel,
  defaultOpen = false,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  /** Rendered instead of `children` when the corresponding `RunDetailResponse`
   * field is `null` -- every field is null in the narrow window between
   * webhook acceptance and the graph's first checkpoint superstep. */
  emptyLabel?: string;
  /** Cards default to collapsed so operators can scan titles first, then
   * open only what they need -- each card tracks its own open state, so
   * any number can be expanded at once. */
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Card className="p-4 sm:p-5">
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-center justify-between gap-3">
          <CollapsibleTrigger className="group flex min-h-11 flex-1 items-center gap-2 text-left sm:min-h-8">
            <ChevronDown
              className={cn(
                "size-4 shrink-0 text-muted-foreground transition-transform group-hover:text-foreground",
                open && "rotate-180",
              )}
              aria-hidden
            />
            <h2 className="font-heading text-sm font-semibold text-foreground/90 transition-colors group-hover:text-foreground">
              {title}
            </h2>
          </CollapsibleTrigger>
          {action}
        </div>
        <CollapsibleContent className="mt-3">
          {emptyLabel ? <p className="text-sm text-muted-foreground">{emptyLabel}</p> : children}
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
