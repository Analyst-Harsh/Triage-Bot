import type { ReactNode } from 'react'

export function GlassCard({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`rounded-2xl border border-[var(--color-surface-border)] bg-[var(--color-surface)]/70 p-7 backdrop-blur ${className}`}
    >
      {children}
    </div>
  )
}
