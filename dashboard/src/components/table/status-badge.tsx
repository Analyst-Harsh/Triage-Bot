"use client";

import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { getStatusVisual } from "@/lib/status";
import { cn } from "@/lib/utils";
import { useReducedMotion } from "@/lib/useReducedMotion";

export function StatusBadge({ status }: { status: string }) {
  const visual = getStatusVisual(status);
  const reducedMotion = useReducedMotion();
  const shouldPulse = visual.pulses && !reducedMotion;

  return (
    <Badge variant="outline" className={cn("gap-1.5 border-current/20", visual.colorClass)}>
      <motion.span
        className={cn("size-1.5 rounded-full", visual.dotClass)}
        animate={shouldPulse ? { opacity: [1, 0.4, 1] } : undefined}
        transition={shouldPulse ? { duration: 1.5, repeat: Infinity, ease: "easeInOut" } : undefined}
      />
      {visual.label}
    </Badge>
  );
}
