import { useRef } from 'react'
import { useGSAP } from '@gsap/react'
import { gsap } from '../../lib/gsap'
import { STAGE_ICONS } from '../../data/stageIcons'
import { useReducedMotion } from '../../lib/useReducedMotion'

interface OrbitChip {
  id: keyof typeof STAGE_ICONS
  label: string
  top: string
  left: string
}

const CHIPS: OrbitChip[] = [
  { id: 'planner', label: 'Planner', top: '20%', left: '10%' },
  { id: 'researcher', label: 'Researcher', top: '18%', left: '86%' },
  { id: 'drafter', label: 'Drafter', top: '58%', left: '6%' },
  { id: 'risk-check', label: 'Risk check', top: '60%', left: '90%' },
  { id: 'auto-post', label: 'Approval', top: '84%', left: '50%' },
]

export function HeroGraphic() {
  const ref = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()

  useGSAP(
    () => {
      gsap.from('.orbit-chip', {
        opacity: 0,
        scale: 0.7,
        duration: 0.7,
        stagger: 0.12,
        delay: 0.3,
        ease: 'back.out(1.6)',
      })
      gsap.from('.orbit-line', {
        opacity: 0,
        duration: 1,
        delay: 0.5,
        stagger: 0.1,
      })

      if (reducedMotion) return

      gsap.utils.toArray<HTMLElement>('.orbit-chip').forEach((chip, i) => {
        gsap.to(chip, {
          y: i % 2 === 0 ? -10 : 10,
          duration: 2.4 + i * 0.3,
          repeat: -1,
          yoyo: true,
          ease: 'sine.inOut',
          delay: i * 0.2,
        })
      })
    },
    { scope: ref, dependencies: [reducedMotion] },
  )

  return (
    <div
      ref={ref}
      className="pointer-events-none absolute inset-0 hidden md:block"
      aria-hidden="true"
    >
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {CHIPS.map((chip) => (
          <line
            key={chip.id}
            className="orbit-line"
            x1="50"
            y1="50"
            x2={parseFloat(chip.left)}
            y2={parseFloat(chip.top)}
            stroke="url(#orbit-gradient)"
            strokeWidth="0.15"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <defs>
          <linearGradient id="orbit-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#7C3AED" stopOpacity="0.5" />
            <stop offset="50%" stopColor="#6366F1" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#60A5FA" stopOpacity="0.15" />
          </linearGradient>
        </defs>
      </svg>

      {CHIPS.map((chip) => {
        const Icon = STAGE_ICONS[chip.id]
        return (
          <div
            key={chip.id}
            className="orbit-chip absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-2.5 rounded-full border border-[var(--color-surface-border)] bg-[var(--color-surface)]/80 px-5 py-3 backdrop-blur-md"
            style={{ top: chip.top, left: chip.left }}
          >
            <Icon size={18} className="text-[var(--color-secondary-to)]" />
            <span className="font-mono text-base text-[var(--color-text-muted)]">
              {chip.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}
