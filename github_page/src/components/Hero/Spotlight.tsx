import { useEffect, useRef } from 'react'
import { useReducedMotion } from '../../lib/useReducedMotion'

export function Spotlight() {
  const ref = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    const el = ref.current
    const parent = el?.parentElement
    if (!el || !parent || reducedMotion) return

    const handleMove = (event: PointerEvent) => {
      const { left, top } = parent.getBoundingClientRect()
      el.style.setProperty('--spotlight-x', `${event.clientX - left}px`)
      el.style.setProperty('--spotlight-y', `${event.clientY - top}px`)
      el.style.opacity = '1'
    }
    const handleLeave = () => {
      el.style.opacity = '0'
    }

    parent.addEventListener('pointermove', handleMove)
    parent.addEventListener('pointerleave', handleLeave)
    return () => {
      parent.removeEventListener('pointermove', handleMove)
      parent.removeEventListener('pointerleave', handleLeave)
    }
  }, [reducedMotion])

  if (reducedMotion) return null

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300"
      style={{
        background:
          'radial-gradient(circle 380px at var(--spotlight-x, 50%) var(--spotlight-y, 50%), rgba(124,58,237,0.22), rgba(99,102,241,0.16) 22%, rgba(96,165,250,0.1) 45%, transparent 70%)',
      }}
    />
  )
}
