"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RUN_STATUSES } from "@/lib/status";
import { cn } from "@/lib/utils";

const SOURCE_OPTIONS = [
  { value: "webhook", label: "Webhook" },
  { value: "replay", label: "Replay" },
];

export type RunsFilterValue = {
  status?: string[];
  repoFullName?: string;
  source?: string;
};

function toggleStatus(current: string[] | undefined, status: string): string[] | undefined {
  const set = new Set(current ?? []);
  if (set.has(status)) {
    set.delete(status);
  } else {
    set.add(status);
  }
  return set.size > 0 ? Array.from(set) : undefined;
}

export function RunsFilterBar({
  value,
  onChange,
}: {
  value: RunsFilterValue;
  onChange: (value: RunsFilterValue) => void;
}) {
  const [open, setOpen] = useState(false);
  const activeCount =
    (value.status?.length ?? 0) + (value.repoFullName ? 1 : 0) + (value.source ? 1 : 0);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        render={
          <Button variant="outline" className="min-h-11 gap-2">
            <SlidersHorizontal className="size-4" aria-hidden />
            Filters
            {activeCount > 0 && (
              <Badge variant="secondary" className="ml-0.5">
                {activeCount}
              </Badge>
            )}
            <ChevronDown
              className={cn("size-3.5 transition-transform", open && "rotate-180")}
              aria-hidden
            />
          </Button>
        }
      />
      <CollapsibleContent className="mt-3 space-y-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Status</p>
          <div className="flex flex-wrap gap-1.5">
            {RUN_STATUSES.map((status) => {
              const active = value.status?.includes(status) ?? false;
              return (
                <button
                  key={status}
                  type="button"
                  aria-pressed={active}
                  onClick={() => onChange({ ...value, status: toggleStatus(value.status, status) })}
                  className={cn(
                    "min-h-11 rounded-full border px-3 text-xs font-medium capitalize transition-colors sm:min-h-8",
                    active
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {status.replaceAll("_", " ")}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          <div className="flex-1">
            <label className="mb-2 block text-xs font-medium text-muted-foreground" htmlFor="repo-filter">
              Repository
            </label>
            <Input
              id="repo-filter"
              placeholder="owner/repo"
              value={value.repoFullName ?? ""}
              onChange={(event) =>
                onChange({ ...value, repoFullName: event.target.value || undefined })
              }
            />
          </div>
          <div className="w-full sm:w-48">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Source</p>
            <Select
              value={value.source ?? "any"}
              onValueChange={(next) => onChange({ ...value, source: next && next !== "any" ? next : undefined })}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any source</SelectItem>
                {SOURCE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
