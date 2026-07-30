import { useRef, type ComponentType } from 'react'
import { useGSAP } from '@gsap/react'
import { Activity, CheckCircle2, Database, Server, Sparkles, Workflow, Wrench } from 'lucide-react'
import {
  SiAnthropic,
  SiFastapi,
  SiLangchain,
  SiLanggraph,
  SiModelcontextprotocol,
  SiOpentelemetry,
  SiPostgresql,
  SiPydantic,
  SiPytest,
  SiRuff,
  SiSqlalchemy,
  SiUv,
} from '@icons-pack/react-simple-icons'
import { gsap } from '../lib/gsap'
import { TECH_STACK } from '../data/techStack'

type IconComponent = ComponentType<{ size?: number; className?: string }>

const ITEM_ICONS: Partial<Record<string, IconComponent>> = {
  LangGraph: SiLanggraph,
  LangChain: SiLangchain,
  Anthropic: SiAnthropic,
  MCP: SiModelcontextprotocol,
  FastAPI: SiFastapi,
  'Pydantic v2': SiPydantic,
  Postgres: SiPostgresql,
  SQLAlchemy: SiSqlalchemy,
  OpenTelemetry: SiOpentelemetry,
  pytest: SiPytest,
  ruff: SiRuff,
  uv: SiUv,
}

const CATEGORY_FALLBACK_ICONS: Record<string, IconComponent> = {
  'Agent framework': Workflow,
  'LLM providers': Sparkles,
  Tooling: Wrench,
  'API layer': Server,
  Database: Database,
  Observability: Activity,
  Quality: CheckCircle2,
}

export function TechStack() {
  const ref = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      gsap.from('.tech-group', {
        opacity: 0,
        y: 16,
        duration: 0.5,
        stagger: 0.06,
        ease: 'power2.out',
        scrollTrigger: { trigger: ref.current, start: 'top 85%' },
      })
    },
    { scope: ref },
  )

  return (
    <section ref={ref} className="mx-auto max-w-5xl px-6 py-24">
      <h2 className="font-display mb-12 text-center text-4xl font-bold tracking-tight text-[var(--color-text)] sm:text-5xl lg:text-6xl">
        Built with
      </h2>
      <div className="grid gap-7 sm:grid-cols-2 lg:grid-cols-3">
        {TECH_STACK.map((category) => (
          <div key={category.label} className="tech-group">
            <p className="mb-4 font-mono text-sm uppercase tracking-wide text-[var(--color-text-muted)]">
              {category.label}
            </p>
            <div className="flex flex-wrap gap-2.5">
              {category.items.map((item) => {
                const Icon = ITEM_ICONS[item] ?? CATEGORY_FALLBACK_ICONS[category.label]
                return (
                  <span
                    key={item}
                    className="flex items-center gap-2 rounded-full border border-[var(--color-surface-border)] bg-[var(--color-surface)] px-4 py-2 text-base text-[var(--color-text)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-secondary-to)]"
                  >
                    {Icon && <Icon size={16} className="text-[var(--color-text-muted)]" />}
                    {item}
                  </span>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
