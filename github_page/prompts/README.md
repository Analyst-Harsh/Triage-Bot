Assets for the Triage Bot landing page split three ways:

1. AI-generated (prompt files in this directory): favicon.md, og-image.md,
   hero-fallback-poster.md, dashboard-mock.md, hero-graphic.md,
   pipeline-background.md
2. Real, captured (never fabricated): langfuse-screenshot.md
3. Built directly in code, no image asset at all: pipeline diagram, tech-stack chips

favicon.md was revised — the first attempt rendered as a soft blurred glow
orb, which doesn't work as a favicon (illegible at 16px). The revised prompt
is explicit about flat, hard-edged, no-blur output. Regenerate from the
updated prompt rather than reusing the old favicon.png.

hero-graphic.md is new: a bold "signal core" centerpiece illustration to
layer into the hero, richer than the current procedural WebGL core+chips.
Unlike the favicon, this one should have dramatic glow/bloom — it's meant to
read as a premium 3D render, not a crisp icon.

pipeline-background.md is new: one full-bleed background image for the whole
Pipeline section (same treatment as hero-fallback-poster.md), replacing an
earlier five-illustrations-per-stage attempt that generated at the wrong
resolution (~307x504, meant to be at least 1600x1600) and was never wired
in. Per-stage visual distinction now comes from a cheap CSS color-tint
overlay in code (using each stage's existing accent color) layered on top
of this one shared image, rather than from five separate heavy assets.

dashboard-mock.md is a deliberate exception: no dashboard frontend exists yet,
so this image is an explicitly-labeled demo/concept preview (fake data) of what
the real dashboard will look like once built against the live GET /runs API —
not a claim that it's a real screenshot. Swap it for a real screenshot once the
dashboard is actually built.
