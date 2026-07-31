import { LayoutDashboard } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { SystemHealthPanel } from "./system-health-panel";

type RunSummaryResponse = components["schemas"]["RunSummaryResponse"];

export function Sidebar({ initialHealthSummary }: { initialHealthSummary?: RunSummaryResponse }) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/40 p-4 md:flex">
      <Link href="/dashboard" className="flex min-h-11 items-center gap-2 rounded-md px-2">
        <Image src="/logo.png" alt="" width={28} height={28} className="rounded-md" />
        <span className="font-heading text-sm font-semibold">Triage Bot</span>
      </Link>

      <nav className="mt-6 flex flex-col gap-1">
        <span className="flex min-h-11 items-center gap-2 rounded-md bg-primary/10 px-3 text-sm font-medium text-primary">
          <LayoutDashboard className="size-4" aria-hidden />
          Overview
        </span>
      </nav>

      <div className="mt-auto space-y-4">
        <SystemHealthPanel initialSummary={initialHealthSummary} />
        <div className="flex min-h-11 items-center gap-2 rounded-md px-2 text-sm text-muted-foreground">
          <div className="flex size-7 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
            OP
          </div>
          Operator
        </div>
      </div>
    </aside>
  );
}
