import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { AnimatedNumber } from "./animated-number";
import { Sparkline } from "./sparkline";

type StatCardProps = {
  icon: LucideIcon;
  label: string;
  value: number;
  format?: (value: number) => string;
  sparkline?: number[];
  colorClass: string;
  sparklineColorVar: string;
};

export function StatCard({
  icon: Icon,
  label,
  value,
  format = (n) => String(n),
  sparkline,
  colorClass,
  sparklineColorVar,
}: StatCardProps) {
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className={cn("size-4", colorClass)} aria-hidden />
          <span className="text-sm text-muted-foreground">{label}</span>
        </div>
        {sparkline && sparkline.length >= 2 && (
          <Sparkline data={sparkline} colorVar={sparklineColorVar} />
        )}
      </div>
      <AnimatedNumber
        value={value}
        format={format}
        className={cn("mt-2 block font-mono text-3xl font-semibold tabular-nums", colorClass)}
      />
    </Card>
  );
}
