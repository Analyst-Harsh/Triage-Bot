/**
 * Status/risk -> color/label mapping, the single source of truth
 * StatusBadge, RiskBadge, stat cards, and the sidebar health panel all read
 * from. Matches `graph/schemas/enums.py::RunStatus` (10 values) and
 * `RiskLevel` (3 values) on the backend exactly -- see
 * docs/agent/architecture-conventions.md for the backend side.
 */

export const RUN_STATUSES = [
  "received",
  "planning",
  "researching",
  "drafting",
  "risk_check",
  "auto_posted",
  "pending_approval",
  "approved_and_posted",
  "rejected",
  "failed",
] as const;

export type RunStatus = (typeof RUN_STATUSES)[number];

export type RiskLevel = "low" | "medium" | "high";

export type StatusVisual = {
  label: string;
  colorClass: string;
  dotClass: string;
  /** The five actively-processing statuses the live badge pulse animation
   * targets -- deliberately excludes `pending_approval`, a stable waiting
   * state, not "in progress". A different, narrower set than
   * `NON_TERMINAL_STATUSES` (six), which the sidebar's In-Flight Runs
   * metric uses instead. */
  pulses: boolean;
};

const STATUS_VISUALS: Record<RunStatus, StatusVisual> = {
  received: { label: "Received", colorClass: "text-active", dotClass: "bg-active", pulses: true },
  planning: { label: "Planning", colorClass: "text-active", dotClass: "bg-active", pulses: true },
  researching: {
    label: "Researching",
    colorClass: "text-active",
    dotClass: "bg-active",
    pulses: true,
  },
  drafting: { label: "Drafting", colorClass: "text-active", dotClass: "bg-active", pulses: true },
  risk_check: {
    label: "Risk Check",
    colorClass: "text-active",
    dotClass: "bg-active",
    pulses: true,
  },
  pending_approval: {
    label: "Pending Approval",
    colorClass: "text-warning",
    dotClass: "bg-warning",
    pulses: false,
  },
  auto_posted: {
    label: "Auto Posted",
    colorClass: "text-success",
    dotClass: "bg-success",
    pulses: false,
  },
  approved_and_posted: {
    label: "Approved & Posted",
    colorClass: "text-success",
    dotClass: "bg-success",
    pulses: false,
  },
  rejected: { label: "Rejected", colorClass: "text-neutral", dotClass: "bg-neutral", pulses: false },
  failed: {
    label: "Failed",
    colorClass: "text-destructive",
    dotClass: "bg-destructive",
    pulses: false,
  },
};

const FALLBACK_STATUS_VISUAL: StatusVisual = {
  label: "Unknown",
  colorClass: "text-muted-foreground",
  dotClass: "bg-muted-foreground",
  pulses: false,
};

export function getStatusVisual(status: string): StatusVisual {
  return STATUS_VISUALS[status as RunStatus] ?? FALLBACK_STATUS_VISUAL;
}

const RISK_VISUALS: Record<RiskLevel, Omit<StatusVisual, "pulses">> = {
  low: { label: "Low", colorClass: "text-success", dotClass: "bg-success" },
  medium: { label: "Medium", colorClass: "text-warning", dotClass: "bg-warning" },
  high: { label: "High", colorClass: "text-destructive", dotClass: "bg-destructive" },
};

const FALLBACK_RISK_VISUAL: Omit<StatusVisual, "pulses"> = {
  label: "Unknown",
  colorClass: "text-muted-foreground",
  dotClass: "bg-muted-foreground",
};

export function getRiskVisual(risk: string): Omit<StatusVisual, "pulses"> {
  return RISK_VISUALS[risk as RiskLevel] ?? FALLBACK_RISK_VISUAL;
}

/** `RunStatus.terminal_statuses()` on the backend is exactly these four --
 * everything else is non-terminal. */
const TERMINAL_STATUSES: readonly RunStatus[] = [
  "auto_posted",
  "approved_and_posted",
  "rejected",
  "failed",
];

/** The sidebar SystemHealthPanel's In-Flight Runs metric: all 6 non-terminal
 * statuses, deliberately including `pending_approval` -- a run stuck
 * waiting on a human is the single most important "stuck in flight" case. */
export const NON_TERMINAL_STATUSES: readonly RunStatus[] = RUN_STATUSES.filter(
  (status) => !TERMINAL_STATUSES.includes(status),
);

/** The Overview page's "Auto-Posted" stat card combines both -- either is a
 * successful outcome from the operator's perspective. */
export const SUCCESS_STATUSES: readonly RunStatus[] = ["auto_posted", "approved_and_posted"];
