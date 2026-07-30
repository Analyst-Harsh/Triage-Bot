import { GithubIcon } from './ui/GithubIcon'

export function Nav() {
  return (
    <header className="fixed right-4 top-4 z-50">
      <a
        href="https://github.com/Analyst-Harsh/Triage-Bot"
        target="_blank"
        rel="noreferrer"
        aria-label="View Triage Bot on GitHub"
        className="flex h-10 w-10 items-center justify-center rounded-full border border-[var(--color-surface-border)] bg-[var(--color-bg)]/70 text-[var(--color-text)] backdrop-blur-lg transition-colors hover:border-[var(--color-primary)]"
      >
        <GithubIcon size={18} />
      </a>
    </header>
  )
}
