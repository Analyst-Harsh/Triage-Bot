export type RiskLevel = 'low' | 'medium' | 'high'

export const riskColor: Record<RiskLevel, string> = {
  low: '#22C55E',
  medium: '#F59E0B',
  high: '#EF4444',
}

export const riskLabel: Record<RiskLevel, string> = {
  low: 'LOW',
  medium: 'MEDIUM',
  high: 'HIGH',
}
