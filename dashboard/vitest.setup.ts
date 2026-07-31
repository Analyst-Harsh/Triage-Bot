import { vi } from "vitest";
import "@testing-library/jest-dom/vitest";

// `server-only` throws unconditionally unless resolved through Next.js's own
// bundler-set "react-server" export condition, which Vitest never sets --
// it's a build-time guard against a 'use client' component importing
// server-only code, not something a plain Node/jsdom test run is ever
// subject to. Neutralized globally here so server-side unit tests (e.g.
// src/lib/api/triage-client.ts) can run at all; the real guard still fires
// correctly under `next build`/`next dev`, the only context it protects.
vi.mock("server-only", () => ({}));
