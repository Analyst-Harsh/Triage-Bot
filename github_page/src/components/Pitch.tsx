import { useRef } from 'react'
import { useGSAP } from '@gsap/react'
import { FileSearch, SearchCode, Wrench, UserCheck, MoveRight } from 'lucide-react'
import { gsap } from '../lib/gsap'

const STEPS = [
  { icon: FileSearch, label: 'Read the issue' },
  { icon: SearchCode, label: 'Investigate the code' },
  { icon: Wrench, label: 'Draft a verified fix' },
  { icon: UserCheck, label: 'Know when to ask' },
]

export function Pitch() {
  const ref = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      gsap.from('.pitch-line', {
        opacity: 0,
        y: 24,
        duration: 0.6,
        stagger: 0.12,
        ease: 'power2.out',
        scrollTrigger: { trigger: ref.current, start: 'top 80%' },
      })
      gsap.from('.pitch-step', {
        opacity: 0,
        y: 16,
        scale: 0.85,
        duration: 0.5,
        stagger: 0.12,
        ease: 'back.out(1.7)',
        scrollTrigger: { trigger: ref.current, start: 'top 70%' },
      })
      gsap.from('.pitch-arrow', {
        opacity: 0,
        duration: 0.4,
        stagger: 0.12,
        delay: 0.2,
        scrollTrigger: { trigger: ref.current, start: 'top 70%' },
      })
      gsap.fromTo(
        '.pitch-ring',
        { boxShadow: '0 0 0 0 rgba(124,58,237,0.55)', opacity: 1 },
        {
          boxShadow: '0 0 0 14px rgba(124,58,237,0)',
          opacity: 0,
          duration: 0.9,
          stagger: 0.12,
          delay: 0.35,
          ease: 'power2.out',
          scrollTrigger: { trigger: ref.current, start: 'top 70%' },
        },
      )
    },
    { scope: ref },
  )

  return (
    <section
      ref={ref}
      className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-6 py-32 text-center"
    >
      <p className="pitch-line font-display text-3xl font-semibold tracking-tight text-[var(--color-text)] sm:text-4xl">
        Most issue triage is judgment work, not busywork.
      </p>
      <p className="pitch-line max-w-2xl text-xl text-[var(--color-text-muted)]">
        Triage Bot reads the issue, investigates the codebase, drafts a verified
        fix — and knows exactly which of those steps still need a human.
      </p>

      <div className="mt-12 flex flex-wrap items-center justify-center gap-3 sm:gap-4">
        {STEPS.map((step, i) => (
          <div key={step.label} className="flex items-center gap-3 sm:gap-4">
            <div className="pitch-step flex flex-col items-center gap-3">
              <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-[var(--color-surface-border)] bg-[var(--color-surface)]">
                <span className="pitch-ring pointer-events-none absolute inset-0 rounded-full" />
                <step.icon size={30} className="text-[var(--color-secondary-to)]" />
              </div>
              <span className="font-display max-w-[8rem] text-base text-[var(--color-text-muted)]">
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <MoveRight
                size={22}
                className="stage-visual-motion pitch-arrow mb-7 shrink-0 text-[var(--color-secondary-to)]"
                style={{ animation: `arrow-color-cycle 2.4s ease-in-out ${i * 0.3}s infinite` }}
              />
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
