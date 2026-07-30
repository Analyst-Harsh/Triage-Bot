import { Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { ArrowDown } from 'lucide-react'
import { ParticleField } from './ParticleField'
import { SignalCore } from './SignalCore'
import { HeroGraphic } from './HeroGraphic'
import { Spotlight } from './Spotlight'
import { GithubIcon } from '../ui/GithubIcon'
import { useReducedMotion } from '../../lib/useReducedMotion'
import heroFallbackPoster from '../../assets/hero-fallback-poster.png'

const BADGES = ['OWASP Red-Teamed', 'Eval-Driven', 'Resume-Safe', 'Sandboxed Execution']

export function Hero() {
  const reducedMotion = useReducedMotion()

  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6">
      <div className="absolute inset-0 -z-10">
        {reducedMotion ? (
          <div
            className="h-full w-full"
            style={{
              backgroundImage: `url(${heroFallbackPoster})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
            }}
          />
        ) : (
          <>
            <div
              className="stage-visual-motion pointer-events-none absolute inset-[-20%]"
              style={{
                background:
                  'radial-gradient(circle at 50% 45%, rgba(124,58,237,0.35), rgba(99,102,241,0.2) 35%, rgba(96,165,250,0.12) 55%, transparent 70%)',
                filter: 'blur(60px)',
                animation: 'hero-glow-drift 14s ease-in-out infinite',
              }}
            />
            <Canvas
              camera={{ position: [0, 0, 6], fov: 60 }}
              gl={{ alpha: true, antialias: true }}
              dpr={[1, 1.5]}
            >
              <Suspense fallback={null}>
                <ParticleField />
                <SignalCore />
              </Suspense>
            </Canvas>
          </>
        )}
        {!reducedMotion && <HeroGraphic />}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[var(--color-bg)]" />
      </div>
      {!reducedMotion && <Spotlight />}

      <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
        <span className="mb-7 rounded-full border border-[var(--color-surface-border)] bg-[var(--color-surface)]/60 px-5 py-2 font-mono text-base font-bold tracking-wide text-[var(--color-text)] backdrop-blur">
          TRIAGE BOT
        </span>
        <h1 className="font-display text-balance text-6xl font-bold tracking-tight text-[var(--color-text)] sm:text-7xl md:text-8xl">
          Issues in. Judgment out.
        </h1>
        <p className="mt-7 max-w-2xl text-xl text-[var(--color-text-muted)] sm:text-2xl">
          An AI agent that investigates, drafts, and knows exactly when to ask a
          human.
        </p>

        <div className="mt-12 flex flex-wrap items-center justify-center gap-4">
          <a
            href="https://github.com/Analyst-Harsh/Triage-Bot"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2.5 rounded-full bg-[var(--color-primary)] px-8 py-4 text-lg font-medium text-white transition hover:brightness-110"
          >
            <GithubIcon size={22} />
            View on GitHub
          </a>
        </div>

        <div className="mt-16 flex flex-wrap items-center justify-center gap-3">
          {BADGES.map((badge) => (
            <span
              key={badge}
              className="rounded-full border border-[var(--color-surface-border)] px-4 py-2 font-mono text-base text-[var(--color-text-muted)]"
            >
              {badge}
            </span>
          ))}
        </div>
      </div>

      <div className="absolute bottom-8 flex flex-col items-center gap-2 text-[var(--color-text-muted)]">
        <ArrowDown size={22} className="animate-bounce motion-reduce:animate-none" />
      </div>
    </section>
  )
}
