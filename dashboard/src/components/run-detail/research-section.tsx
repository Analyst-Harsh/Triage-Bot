import type { components } from "@/lib/api/schema";
import { SectionCard } from "./section-card";

type ResearchFindings = components["schemas"]["ResearchFindings"];

export function ResearchSection({ research }: { research: ResearchFindings | null }) {
  return (
    <SectionCard title="Research" emptyLabel={research ? undefined : "Not researched yet."}>
      {research && (
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">{research.summary}</p>
          {research.evidence && research.evidence.length > 0 && (
            <ul className="space-y-2">
              {research.evidence.map((item, index) => (
                <li key={index} className="rounded-lg bg-muted/40 p-2.5">
                  <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span className="font-mono">{item.reference}</span>
                    <span>{Math.round(item.relevance * 100)}% relevant</span>
                  </div>
                  <p className="mt-1 font-mono text-xs text-foreground/90">{item.snippet}</p>
                </li>
              ))}
            </ul>
          )}
          {research.gaps && research.gaps.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-warning">Gaps</p>
              <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
                {research.gaps.map((gap, index) => (
                  <li key={index}>{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}
