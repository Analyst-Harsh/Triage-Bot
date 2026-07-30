import { GithubIcon } from './ui/GithubIcon'

export function Footer() {
  return (
    <footer className="relative mx-auto flex max-w-5xl flex-col items-center gap-6 px-6 py-24 text-center">
      <div
        className="pointer-events-none absolute inset-0 -z-10 blur-2xl"
        style={{
          background:
            'radial-gradient(circle at 50% 30%, rgba(124,58,237,0.18), rgba(99,102,241,0.1) 40%, rgba(96,165,250,0.05) 65%, transparent 80%)',
        }}
      />
      <h2 className="font-display text-4xl font-bold tracking-tight text-[var(--color-text)] sm:text-5xl lg:text-6xl">
        Read the code, or watch it triage a real issue.
      </h2>
      <a
        href="https://github.com/Analyst-Harsh/Triage-Bot"
        target="_blank"
        rel="noreferrer"
        className="flex items-center gap-2.5 rounded-full bg-[var(--color-primary)] px-7 py-3.5 text-lg font-medium text-white transition hover:brightness-110"
      >
        <GithubIcon size={22} />
        Analyst-Harsh/Triage-Bot
      </a>
      <div className="mt-16 flex w-full max-w-xs items-center gap-4 border-t border-[var(--color-surface-border)] pt-8">
        <span className="h-px flex-1 bg-[var(--color-surface-border)]" />
        <p className="font-display text-lg font-semibold tracking-wide text-[var(--color-text)] sm:text-xl">
          Built by Harshit Goyal
        </p>
        <span className="h-px flex-1 bg-[var(--color-surface-border)]" />
      </div>
    </footer>
  )
}
