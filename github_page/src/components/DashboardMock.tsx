import { useRef } from 'react'
import { useGSAP } from '@gsap/react'
import { gsap } from '../lib/gsap'
import dashboardMock from '../assets/dashboard-mock.png'

export function DashboardMock() {
  const ref = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      gsap.from(cardRef.current, {
        opacity: 0,
        y: 40,
        scale: 0.97,
        duration: 0.7,
        ease: 'power2.out',
        scrollTrigger: { trigger: ref.current, start: 'top 80%' },
      })
      gsap.to(cardRef.current, {
        yPercent: -4,
        ease: 'none',
        scrollTrigger: { trigger: ref.current, start: 'top bottom', end: 'bottom top', scrub: 0.5 },
      })
    },
    { scope: ref },
  )

  return (
    <section ref={ref} className="mx-auto max-w-5xl px-6 py-24">
      <div className="mb-8 text-center">
        <h2 className="font-display text-4xl font-bold tracking-tight text-[var(--color-text)] sm:text-5xl lg:text-6xl">
          Every run, tracked
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-lg text-[var(--color-text-muted)]">
          Run list, status summary, per-run detail — the operator dashboard
          behind the pipeline.
        </p>
      </div>

      <div
        ref={cardRef}
        className="relative overflow-hidden rounded-2xl border border-[var(--color-surface-border)] shadow-2xl shadow-black/40"
      >
        <img
          src={dashboardMock}
          alt="Triage Bot operator dashboard: run status tiles and a table of recent triage runs"
          className="w-full"
        />
      </div>
    </section>
  )
}
