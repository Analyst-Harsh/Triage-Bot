"use client";

import { useSyncExternalStore } from "react";

/**
 * Same name/shape as github_page/src/lib/useReducedMotion.ts, rebuilt on
 * `useSyncExternalStore` -- React's own documented mechanism for
 * subscribing to an external, always-changing source (here, a `matchMedia`
 * query) without the "setState synchronously inside an effect" anti-pattern
 * the older `useState`+`useEffect` version hit under this project's
 * `react-hooks/set-state-in-effect` lint rule. `getServerSnapshot` returns
 * `false` (motion enabled) for the SSR pass, matching the old version's
 * progressive-enhancement default.
 */
function subscribe(callback: () => void): () => void {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

function getSnapshot(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function getServerSnapshot(): boolean {
  return false;
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
