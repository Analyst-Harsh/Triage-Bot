"use client";

import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useReducedMotion } from "@/lib/useReducedMotion";

const PERIOD_OPTIONS = [
  { value: "1h", label: "Last hour" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

export function Header({
  period,
  onPeriodChange,
}: {
  period: string | undefined;
  onPeriodChange: (period: string) => void;
}) {
  const queryClient = useQueryClient();
  const reducedMotion = useReducedMotion();

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-5">
      <motion.div
        initial={reducedMotion ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
      >
        <h1 className="font-heading text-2xl font-semibold">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Real-time triage runs, approvals, and cost.
        </p>
      </motion.div>
      <div className="flex items-center gap-2">
        <Select
          value={period ?? "24h"}
          onValueChange={(value) => {
            if (value) onPeriodChange(value);
          }}
        >
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIOD_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="icon"
          className="min-h-11 min-w-11"
          onClick={() => void queryClient.invalidateQueries()}
          aria-label="Refresh"
        >
          <RefreshCw className="size-4" aria-hidden />
        </Button>
      </div>
    </header>
  );
}
