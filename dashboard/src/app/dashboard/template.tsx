"use client";

import { motion } from "motion/react";
import { useReducedMotion } from "@/lib/useReducedMotion";

/**
 * Enter-only fade-in (~150ms) on new route content -- `template.tsx`
 * (unlike `layout.tsx`) remounts on every navigation within `/dashboard`,
 * which is what re-triggers this on the way in. Deliberately not a true
 * two-way crossfade: that needs the outgoing tree kept mounted during exit
 * (extra client-side pathname-keyed state beyond what `template.tsx` alone
 * gives you) -- not worth the plumbing for an internal ops tool's route
 * transitions.
 */
export default function DashboardTemplate({ children }: { children: React.ReactNode }) {
  const reducedMotion = useReducedMotion();

  return (
    <motion.div
      initial={reducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.15 }}
    >
      {children}
    </motion.div>
  );
}
