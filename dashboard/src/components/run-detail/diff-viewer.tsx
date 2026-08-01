"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import { type DiffLine, parseDiff } from "@/lib/diff";
import { cn } from "@/lib/utils";

/** Past this many lines, mount only what's in the scroll viewport rather
 * than every line's DOM node up front -- `CodeFixAction.diff` is
 * deliberately uncapped on the backend, unlike the 20KB-capped preview on
 * `ApprovalRequest`. */
const VIRTUALIZE_THRESHOLD = 500;
const VIEWPORT_HEIGHT_PX = 512;
const ROW_HEIGHT_PX = 20;

function DiffLineRow({ line }: { line: DiffLine }) {
  return (
    <div
      className={cn(
        "whitespace-pre px-3 font-mono text-xs leading-5",
        line.type === "add" && "bg-success/10 text-success",
        line.type === "remove" && "bg-destructive/10 text-destructive",
        line.type === "hunk" && "text-info",
        line.type === "meta" && "text-muted-foreground",
      )}
    >
      {line.content || " "}
    </div>
  );
}

function PlainDiff({ lines }: { lines: DiffLine[] }) {
  return (
    <div
      className="overflow-x-auto overflow-y-auto rounded-lg bg-card ring-1 ring-foreground/10"
      style={{ maxHeight: VIEWPORT_HEIGHT_PX }}
    >
      {lines.map((line, index) => (
        <DiffLineRow key={index} line={line} />
      ))}
    </div>
  );
}

function VirtualizedDiff({ lines }: { lines: DiffLine[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: lines.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_PX,
    overscan: 20,
  });

  return (
    <div
      ref={parentRef}
      className="overflow-x-auto overflow-y-auto rounded-lg bg-card ring-1 ring-foreground/10"
      style={{ height: VIEWPORT_HEIGHT_PX }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
        {virtualizer.getVirtualItems().map((virtualRow) => (
          <div
            key={virtualRow.key}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            <DiffLineRow line={lines[virtualRow.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function DiffViewer({ diff }: { diff: string }) {
  const lines = parseDiff(diff);
  return lines.length > VIRTUALIZE_THRESHOLD ? (
    <VirtualizedDiff lines={lines} />
  ) : (
    <PlainDiff lines={lines} />
  );
}
