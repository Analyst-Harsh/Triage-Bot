# Triage Bot — Marketing / Portfolio Site

The public-facing landing page for [Triage Bot](../README.md), live at [analyst-harsh.github.io/Triage-Bot](https://analyst-harsh.github.io/Triage-Bot/). Tagline: *"Issues in. Judgment out."*

> **Note:** the dashboard visual on this site (`DashboardMock`) is an illustrative concept image, not a real product screenshot — no live ops-dashboard UI exists yet. See the root README's [Dashboard API](../README.md#dashboard-api) section for what's actually built and running today.

## Stack

React 19, Vite, TypeScript, Three.js / `@react-three/fiber` (hero visuals), GSAP (scroll-driven animation), Tailwind CSS v4, Oxlint.

## Run locally

```bash
npm install
npm run dev
```

## Build

```bash
npm run build   # tsc -b && vite build, outputs to dist/
```

## Deploy

Automatic — `.github/workflows/deploy-pages.yml` builds and deploys this directory to GitHub Pages on every push to `main` that touches `github_page/**`. There's no manual deploy step.

---

See the root [README.md](../README.md) for the actual agent/pipeline this site describes.
