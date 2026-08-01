"use client";

import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect } from "react";
import { useReducedMotion } from "@/lib/useReducedMotion";

/**
 * Ticks toward `value` on mount and whenever it changes -- e.g. a
 * live-polled stat card. Deliberately drives a `MotionValue`, not React
 * state: `motionValue.set()`/`animate()` update the DOM text directly
 * through Motion's own render path, not a React re-render, so there's no
 * `setState`-inside-`useEffect` to trip this project's
 * `react-hooks/set-state-in-effect` lint rule. Instant (no tween) under
 * `prefers-reduced-motion`.
 */
export function AnimatedNumber({
  value,
  format,
  className,
}: {
  value: number;
  format: (value: number) => string;
  className?: string;
}) {
  const reducedMotion = useReducedMotion();
  const motionValue = useMotionValue(value);
  const display = useTransform(motionValue, (latest) => format(latest));

  useEffect(() => {
    if (reducedMotion) {
      motionValue.jump(value);
      return;
    }
    const controls = animate(motionValue, value, { duration: 0.6, ease: "easeOut" });
    return () => controls.stop();
  }, [value, reducedMotion, motionValue]);

  return <motion.span className={className}>{display}</motion.span>;
}
