import { useRef } from 'react'
import { useGSAP } from '@gsap/react'
import { Activity, Box, Gauge, History, FlaskConical, ShieldCheck } from 'lucide-react'
import { gsap } from '../lib/gsap'
import { DIFFERENTIATORS, type Differentiator } from '../data/differentiators'
import { RED_TEAM_CASES } from '../data/redTeam'
import { GlassCard } from './ui/GlassCard'

const ICONS: Record<Differentiator['icon'], typeof Gauge> = {
  gauge: Gauge,
  shieldCheck: ShieldCheck,
  activity: Activity,
  flaskConical: FlaskConical,
  history: History,
  box: Box,
}

export function Differentiators() {
  const ref = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      gsap.from('.diff-card', {
        opacity: 0,
        y: 24,
        duration: 0.5,
        stagger: 0.08,
        ease: 'power2.out',
        scrollTrigger: { trigger: ref.current, start: 'top 85%' },
      })
    },
    { scope: ref },
  )

  return (
    <section ref={ref} className="mx-auto max-w-6xl px-6 py-24">
      <h2 className="font-display mb-14 text-center text-4xl font-bold tracking-tight text-[var(--color-text)] sm:text-5xl lg:text-6xl">
        Built like production, not a demo
      </h2>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {DIFFERENTIATORS.map((item) => {
          const Icon = ICONS[item.icon]
          return (
            <GlassCard key={item.id} className="diff-card flex flex-col gap-3.5">
              <Icon size={26} className="text-[var(--color-secondary-to)]" />
              <h3 className="text-lg font-semibold text-[var(--color-text)]">{item.title}</h3>
              <p className="text-base text-[var(--color-text-muted)]">{item.description}</p>
            </GlassCard>
          )
        })}

        <GlassCard className="diff-card flex flex-col gap-5 sm:col-span-2 lg:col-span-3">
          <div className="flex items-center gap-3">
            <ShieldCheck size={26} className="text-[var(--color-risk-low)]" />
            <h3 className="text-lg font-semibold text-[var(--color-text)] sm:text-xl">
              Red-teamed against the live pipeline — every attempt resisted
            </h3>
          </div>
          <p className="text-base text-[var(--color-text-muted)]">
            Adversarial GitHub issues, each embedding a real injection payload,
            run through the live pipeline and mapped to the OWASP LLM Top 10 — now
            regression-tested as golden eval cases.
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 font-mono text-sm sm:grid-cols-3">
            {RED_TEAM_CASES.map((c) => (
              <div
                key={c.issue}
                className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-surface-border)] px-3.5 py-2.5"
              >
                <span className="text-[var(--color-text-muted)]">
                  {c.issue} · {c.technique}
                </span>
                <span className="rounded bg-[var(--color-risk-low)]/15 px-2 py-1 text-[var(--color-risk-low)]">
                  {c.owasp}
                </span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </section>
  )
}
