A single, high-resolution (3200x1800 minimum, 16:9) static background image for the
"Pipeline" section of a technical product site. Unlike a typical hero fallback, this
is the section's only background art — there's no animated canvas layered on top of
it — so it should be treated as a primary visual, not a disposable placeholder: crisp,
premium, genuinely high-resolution, not over-compressed. The section is pinned
full-screen while the user scrolls through 5 sequential stages of an AI agent's
workflow, so it must read as calm, ambient backdrop art, not a busy focal
illustration. Same visual family as the existing hero background: deep slate-navy
(#0F172A) base with a flowing field of small glowing particles/light-trails in a
gradient from violet (#7C3AED) through indigo (#6366F1) to blue (#60A5FA) — like a
long-exposure photo of drifting light, evoking a data/signal pipeline (nodes
connected by light trails, a sense of left-to-right flow) rather than a random
particle field.

Composition: the frame is split roughly into a left-of-center zone (~0-45% of width)
where plain stage title/description text sits directly on the image with no card
behind it, and a right zone (~45-100%) where a small translucent dark UI panel sits
on top (that panel already darkens/blurs the image under it, so it can carry more
visual density). Keep the left-of-center zone calm and low-contrast — darker,
sparser, no bright particles directly behind where text would sit — and let
brighter, denser detail live on the right half and along the edges/corners.

Crop safety: this image will be shown with CSS `background-size: cover`, so it gets
cropped differently across ultra-wide desktop monitors (crops top/bottom) and tall
mobile screens (crops left/right). Keep the key light-trail motif readable within
the center 80% of the frame and avoid placing essential detail within the outer 10%
margin on any edge.

Palette discipline: keep saturation moderate (not neon-bright) since a colored tint
overlay (green/amber/red, one per pipeline stage) will be blended on top in code —
an overly saturated or high-contrast base will fight with that overlay. No text, no
logos, no literal robot/hardware imagery, no human figures.

Export: opaque JPG or WebP at the full 3200x1800, optimized but not aggressively
compressed — target roughly 600KB-1MB (this is a permanent, always-visible
background, unlike the disposable hero-fallback-poster.png, so a modest size
increase for real visual quality is acceptable). Save as pipeline-background.png (or
.webp) into assets/.
