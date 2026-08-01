"use client";

import { useSyncExternalStore } from "react";
import { formatRelativeTime } from "@/lib/format";

/**
 * `formatRelativeTime` depends on the current instant, which differs
 * between server render and client hydration -- computing it inline would
 * mismatch SSR/CSR output. `useSyncExternalStore` (same approach as
 * `useReducedMotion`) fixes the server snapshot at a stable placeholder and
 * only switches to the live value once mounted, ticking every 30s after.
 */
function subscribe(callback: () => void): () => void {
  const interval = setInterval(callback, 30_000);
  return () => clearInterval(interval);
}

function getServerSnapshot(): null {
  return null;
}

export function RelativeTime({ isoDate }: { isoDate: string }) {
  const text = useSyncExternalStore(subscribe, () => formatRelativeTime(isoDate), getServerSnapshot);

  return <span suppressHydrationWarning>{text ?? "—"}</span>;
}
