"use client";

import { CheckCircle2, Clock, DollarSign, XCircle } from "lucide-react";
import { motion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { useRunsSummaryQuery } from "@/lib/query/hooks";
import type { StatCardData, StatCardKey } from "@/lib/stat-cards";
import { deriveStatCards } from "@/lib/stat-cards";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { StatCard } from "./stat-card";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

const CARD_VISUALS: Record<
  StatCardKey,
  { icon: LucideIcon; colorClass: string; sparklineColorVar: string }
> = {
  pending_approval: {
    icon: Clock,
    colorClass: "text-warning",
    sparklineColorVar: "--color-warning",
  },
  auto_posted: {
    icon: CheckCircle2,
    colorClass: "text-success",
    sparklineColorVar: "--color-success",
  },
  failed: { icon: XCircle, colorClass: "text-destructive", sparklineColorVar: "--color-destructive" },
  est_spend: { icon: DollarSign, colorClass: "text-info", sparklineColorVar: "--color-info" },
};

function formatCount(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

export function StatCardsRow({
  period,
  initialSummary,
}: {
  period: string | undefined;
  initialSummary?: RunSummaryResponse;
}) {
  const summaryQuery = useRunsSummaryQuery(period, undefined, initialSummary);
  const reducedMotion = useReducedMotion();

  if (summaryQuery.isPending) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-card ring-1 ring-foreground/10" />
        ))}
      </div>
    );
  }

  if (summaryQuery.isError) {
    return (
      <div className="rounded-xl bg-card p-4 text-sm text-destructive ring-1 ring-foreground/10">
        Couldn&apos;t load stats.
      </div>
    );
  }

  const cards: StatCardData[] = deriveStatCards(summaryQuery.data);

  return (
    <motion.div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      initial={reducedMotion ? false : "hidden"}
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.06 } },
      }}
    >
      {cards.map((card) => {
        const visual = CARD_VISUALS[card.key];
        return (
          <motion.div
            key={card.key}
            variants={{
              hidden: { opacity: 0, y: 16, scale: 0.92 },
              visible: { opacity: 1, y: 0, scale: 1 },
            }}
            transition={{ duration: 0.35, ease: [0.34, 1.56, 0.64, 1] }}
          >
            <StatCard
              icon={visual.icon}
              label={card.label}
              value={card.total}
              format={card.isCurrency ? formatCurrency : formatCount}
              sparkline={card.sparkline}
              colorClass={visual.colorClass}
              sparklineColorVar={visual.sparklineColorVar}
            />
          </motion.div>
        );
      })}
    </motion.div>
  );
}
