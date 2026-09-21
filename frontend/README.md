# Heimdall — Frontend

React + TypeScript single-page application for the Heimdall portfolio
risk-intelligence platform.

| Document                       | Purpose                                                        |
| ------------------------------ | -------------------------------------------------------------- |
| [`DESIGN.md`](DESIGN.md)       | Visual and motion specification. Authoritative for appearance. |
| [`AGENTS.md`](AGENTS.md)       | What every screen does and which endpoints it calls.           |
| [`PROMPTS.md`](PROMPTS.md)     | Image-generation prompts for every visual asset.               |
| [`../CLAUDE.md`](../CLAUDE.md) | Product rules. Authoritative over all of the above.            |

## Running it

The frontend talks to the backend through a dev-server proxy, which keeps the
refresh cookie first-party. Start the backend first:

```bash
cd backend && uv run uvicorn app.main:app --reload
```

Then, in another terminal:

```bash
cd frontend && npm install && npm run dev
```

The application is served at <http://localhost:5173> and proxies `/api` and
`/health` to `http://127.0.0.1:8000`.

## Commands

```bash
npm run dev           # development server
npm run build         # type check, then production build
npm run typecheck     # tsc --noEmit
npm run lint          # ESLint
npm run format        # Prettier, writing changes
npm run test          # Vitest
npm run api:schema    # re-export openapi.json from the backend
npm run api:types     # regenerate src/api/schema.d.ts from openapi.json
```

## Types come from the backend

`src/api/schema.d.ts` is generated from the backend's own `/openapi.json`. It is
never hand-edited. When a backend contract changes, run both `api:` scripts and
commit the result — continuous integration fails if the committed types and the
live schema disagree, so a contract change breaks the build rather than
production.

## Layout

```text
src/
  api/        HTTP client, generated types, error envelope
  app/        application root, router, query client, error boundary
  auth/       session state, the route guard
  components/ the shared component library
  hooks/      small shared behaviours
  lib/        utilities
  pages/      one file per screen; pages/parts holds shared page furniture
  styles/     design tokens as Tailwind theme variables
  test/       Vitest setup, MSW handlers, render helper
resources/    logos, mockups and reference imagery (never shipped)
```

## Phase status

Phase 8 — foundation — is complete: build tooling, design tokens, routing, the
API client, generated types, session handling, sign-in and registration,
protected routes, the application shell, error handling and continuous
integration.

No portfolio, analytics, stress-testing, signal or report screens exist yet.
Those arrive in Phases 9 to 11, in that order. See `AGENTS.md` section 9.

## Notes for the next phase

- **The Elder Futhark wordmark is not yet self-hosted.** `--font-rune` currently
  falls back to the display serif, and the runes render from whatever the
  visitor's system provides. A licensed, subset `.woff2` in `public/fonts/` is
  needed before this is correct. See `DESIGN.md` section 3.2.
- **No generated imagery is in place.** Heroes and backdrops render as gradients.
  `PROMPTS.md` holds the prompt for each one.
- **Motion is CSS and IntersectionObserver only.** `DESIGN.md` section 7 specifies
  Lenis and GSAP for the Outer Realm; they are deliberately not yet installed, so
  Phase 8 stays small. The reveal behaviour and the reduced-motion contract are
  already in place and will not change when they land.

---

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
