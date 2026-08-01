import type { components } from "@/lib/api/schema";

type ActionRiskAssessment = components["schemas"]["ActionRiskAssessment"];
type RiskLevel = ActionRiskAssessment["level"];

const RISK_ORDER: Record<RiskLevel, number> = { low: 0, medium: 1, high: 2 };

/** RunHeader's single aggregate risk badge: the highest risk level across
 * every proposed action, since one run can carry several actions at
 * different risk levels. */
export function highestRiskLevel(assessments: ActionRiskAssessment[]): RiskLevel | null {
  if (assessments.length === 0) {
    return null;
  }
  return assessments.reduce<RiskLevel>(
    (highest, assessment) =>
      RISK_ORDER[assessment.level] > RISK_ORDER[highest] ? assessment.level : highest,
    assessments[0].level,
  );
}

export type RiskDistribution = Record<RiskLevel, number>;

/** RiskSection's at-a-glance summary strip. */
export function riskDistribution(assessments: ActionRiskAssessment[]): RiskDistribution {
  const distribution: RiskDistribution = { low: 0, medium: 0, high: 0 };
  for (const assessment of assessments) {
    distribution[assessment.level] += 1;
  }
  return distribution;
}
