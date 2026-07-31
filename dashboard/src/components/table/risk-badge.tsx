import { Badge } from "@/components/ui/badge";
import { getRiskVisual } from "@/lib/status";
import { cn } from "@/lib/utils";

export function RiskBadge({ risk }: { risk: string }) {
  const visual = getRiskVisual(risk);

  return (
    <Badge variant="outline" className={cn("gap-1.5 border-current/20", visual.colorClass)}>
      <span className={cn("size-1.5 rounded-full", visual.dotClass)} />
      {visual.label}
    </Badge>
  );
}
