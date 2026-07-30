import { useRef, useState } from 'react'
import { useGSAP } from '@gsap/react'
import { ScrollTrigger } from '../lib/gsap'
import { PIPELINE_STAGES } from '../data/pipeline'
import { riskColor } from '../lib/riskColors'
import { useReducedMotion } from '../lib/useReducedMotion'
import { StageVisual } from './StageVisual'
import pipelineBackground from '../assets/pipeline-background.png'

const ACCENT_COLOR: Record<string, string> = {
  primary: '#7C3AED',
  low: riskColor.low,
  medium: riskColor.medium,
  high: riskColor.high,
}

function PipelineBackdrop({ tint }: { tint?: string }) {
  return (
    <div className="absolute inset-0 -z-10">
      <div
        className="h-full w-full"
        style={{
          backgroundImage: `url(${pipelineBackground})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      />
      {tint && (
        <div
          className="absolute inset-0"
          style={{ background: `radial-gradient(circle at 60% 40%, ${tint}33, transparent 75%)` }}
        />
      )}
    </div>
  )
}

function StageNode({ label, title, description, accent }: (typeof PIPELINE_STAGES)[number]) {
  return (
    <div
      className="stage-visual-motion flex flex-col gap-3"
      style={{ animation: 'stage-text-in 0.5s ease both' }}
    >
      <span
        className="font-mono text-base font-semibold tracking-wide"
        style={{ color: ACCENT_COLOR[accent] }}
      >
        {label}
      </span>
      <h3 className="font-display text-4xl font-bold tracking-tight text-[var(--color-text)] sm:text-5xl lg:text-6xl">{title}</h3>
      <p className="max-w-lg text-xl text-[var(--color-text-muted)] sm:text-2xl">{description}</p>
    </div>
  )
}

export function Pipeline() {
  const containerRef = useRef<HTMLDivElement>(null)
  const fillRef = useRef<HTMLDivElement>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const reducedMotion = useReducedMotion()
  const stageCount = PIPELINE_STAGES.length

  useGSAP(
    () => {
      if (reducedMotion) return

      const trigger = ScrollTrigger.create({
        trigger: containerRef.current,
        start: 'top top',
        end: () => `+=${window.innerHeight * stageCount}`,
        pin: true,
        scrub: 0.5,
        invalidateOnRefresh: true,
        onUpdate: (self) => {
          const index = Math.min(stageCount - 1, Math.floor(self.progress * stageCount))
          setActiveIndex(index)
          if (fillRef.current) {
            fillRef.current.style.height = `${self.progress * 100}%`
          }
        },
      })

      return () => trigger.kill()
    },
    { scope: containerRef, dependencies: [reducedMotion] },
  )

  if (reducedMotion) {
    return (
      <section className="relative mx-auto flex max-w-3xl flex-col gap-16 px-6 py-32">
        <PipelineBackdrop />
        {PIPELINE_STAGES.map((stage) => (
          <div key={stage.id} className="flex flex-col gap-6">
            <StageVisual activeId={stage.id} />
            <StageNode {...stage} />
          </div>
        ))}
      </section>
    )
  }

  const stage = PIPELINE_STAGES[activeIndex]

  return (
    <section ref={containerRef} className="relative flex min-h-screen items-center px-6 py-24">
      <PipelineBackdrop tint={ACCENT_COLOR[stage.accent]} />
      <div className="mx-auto grid w-full max-w-7xl items-center gap-10 lg:grid-cols-[2rem_0.9fr_1.3fr] lg:gap-14">
        <div className="relative hidden justify-self-center lg:block">
          <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[var(--color-surface-border)]" />
          <div
            ref={fillRef}
            className="absolute left-1/2 top-0 w-px -translate-x-1/2 bg-gradient-to-b from-[var(--color-primary)] via-[var(--color-secondary-from)] to-[var(--color-secondary-to)]"
            style={{ height: '0%' }}
          />
          <div className="relative flex h-full flex-col justify-between py-1">
            {PIPELINE_STAGES.map((s, i) => (
              <div
                key={s.id}
                className="h-6 w-6 -translate-x-[11px] rounded-full border-2 transition-all duration-300"
                style={{
                  borderColor:
                    i <= activeIndex ? ACCENT_COLOR[s.accent] : 'var(--color-surface-border)',
                  background: i <= activeIndex ? ACCENT_COLOR[s.accent] : 'var(--color-bg)',
                  boxShadow: i === activeIndex ? `0 0 22px ${ACCENT_COLOR[s.accent]}` : 'none',
                }}
              />
            ))}
          </div>
        </div>

        <div>
          <StageNode key={stage.id} {...stage} />
          <div className="mt-8 flex gap-2 lg:hidden">
            {PIPELINE_STAGES.map((s, i) => (
              <span
                key={s.id}
                className="h-2 flex-1 rounded-full transition-colors duration-300"
                style={{
                  background:
                    i <= activeIndex ? ACCENT_COLOR[s.accent] : 'var(--color-surface-border)',
                }}
              />
            ))}
          </div>
        </div>

        <div className="relative order-first lg:order-none">
          <div
            className="stage-visual-motion pointer-events-none absolute inset-[-10%] -z-10 rounded-[2rem] blur-2xl"
            style={{
              background: `radial-gradient(circle, ${ACCENT_COLOR[stage.accent]} 0%, transparent 70%)`,
              animation: 'accent-glow-pulse 4s ease-in-out infinite',
            }}
          />
          <StageVisual activeId={stage.id} />
        </div>
      </div>
    </section>
  )
}
