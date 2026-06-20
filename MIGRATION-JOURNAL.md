# Migration journal — Jinja/Bootstrap → React SPA

Working log for the UI migration. Append a new `§N` section as each milestone/decision/fix
completes. Structured record (decisions + root causes + state), not a transcript.

## Context / goal
Migrate the Spoolwise (3D-print manager) UI from server-rendered Jinja/Bootstrap templates to a
React SPA (Vite + TS + Tailwind + shadcn/ui) consuming the existing Flask backend as a JSON API.
The old Jinja app must stay fully functional until the SPA reaches parity; `main` stays shippable.
All work on branch `feature/react-spa-migration`, page by page, each shown + verified before moving on.

## Standing decisions (the why)
- **Pacing:** pause after each page; show a screenshot before continuing. **Commits:** per page/batch,
  each gated by CodeRabbit. **Deploy:** serve the built SPA from Flask static (single container, same-origin).
- **Auth:** keep Flask-Login sessions; SPA calls same-origin with credentials. New JSON endpoints live in
  `app/api.py` (`/api/*`), additive — the Jinja routes and the public `/api/orders/pending` are untouched.
- **Dev verification:** real Flask + MariaDB in Docker with seeded data (not mocks), so the API wiring is
  exercised end-to-end. Verify in light + dark before committing.
- **Design system:** brand blue `#0d6efd` (spool) + orange `#fd7e14` (filament), Inter, light/dark via a
  `.dark` class. Quality bar: `:focus-visible`, `prefers-reduced-motion`, ≥44px targets, SVG icons, 150–300ms.
- **Filter/sort done client-side** for list pages (per-user data sets are small) — simpler, instant UX,
  functionality preserved.

## Architecture
- `frontend/` — Vite + React + TS + Tailwind v4 + shadcn/ui; TanStack Query (data), React Hook Form + Zod,
  lucide-react, Recharts, React Router. `@/` → `src/`. Theme via `.dark` + `localStorage("spoolwise-theme")`.
- API client `src/lib/api.ts` (`credentials: "include"`, `api.upload()` for multipart). Hooks per entity
  with query-key invalidation (`["orders"]`, `["order", id]`, `["filaments"]`, `["dashboard"]`, `["settings"]`).
- Backend `app/api.py` blueprint at `/api`, reuses Jinja route helpers (`_fetch_og`, `_parse_bambu_3mf`,
  `_snapshot_price_factory`, plate/file ownership guards) to stay in lockstep with the original logic.

## Milestones

### §1 — Code-review gate (commit `ac3d181`)
Ran CodeRabbit over the whole codebase before any UI work. Triaged 17 findings; fixed all backend/non-UI
Critical + relevant ones (open-redirect on login `next`, SSO first-login race, Flask-Cors CVE bump, CORS
empty-origins fallback, malformed `bambu_colors.json` tolerance, XSS escape in a delete confirm, `lang`
a11y, `FLASK_DEBUG` default-off so the Werkzeug debugger never ships in prod, doc port/env fixes). Deferred
per-template nitpicks into the migration. Skipped adding auth to `/api/orders/pending` (intentional public
contract). **Root cause of the prod-debug risk:** `run.py` hardcoded `debug=True` and ignored `FLASK_DEBUG`,
which the compose file already set to `0`.

### §2 — Audit
Mapped every template/route/entity (9 entities, 24 routes, 13 templates). Recorded the data each page needs
and the cross-cutting features to preserve (retail mode, internal orders, currency, Bambu colour lookup,
low/zero-stock states, multi-plate, file uploads + 3MF, OG links, weighted-average pricing, VAT snapshots).

### §3 — Scaffold + auth API + Login (commit `9c036d5`)
Vite/React/TS/Tailwind/shadcn foundation + design system. Backend `/api/auth/me|login|logout` reusing
Flask-Login. Login page (RHF + Zod), auth context, protected-route guard, theme provider. Verified light+dark.

### §4 — App shell + Dashboard (commit `7869e4b`)
`AppLayout` (nav, user menu, theme toggle, responsive). Dashboard: stat cards + inventory table (low/zero
states) + recent orders. `GET /api/dashboard`. **Parity note (kept deliberately):** the "low" stat counts
`stock_g ≤ 100` including out-of-stock, matching the Jinja `selectattr('le',100)`.

### §5 — Filaments: list + new form + purchase/adjust (commit `51f5149`)
First CRUD. `GET/POST/DELETE /api/filaments`, `/purchase`, `/adjust`. Bambu brand→material→colour cascade
with hex auto-match; weighted-average purchase; inventory-correction adjust. Replaced the native OS colour
input with a custom `ColorPicker` (rounded swatch + preset palette + hex) per user preference. Delete now
returns a friendly 409 when the filament is referenced by an order (was a raw 500). Verified full CRUD live.

### §6 — Orders list (commit `bbb16ae`)
`GET /api/orders`, `DELETE /api/orders/:id` (restores stock). Status/type filters, badges, combined-quote
multi-select (personal orders excluded). Quote routes stubbed until §9.

### §7 — Order detail + 3D viewer (commit `b0b92ff`)
`GET /api/orders/:id`, plate toggle-printed/skipped, mark printed/delivered, file upload (+3MF thumbnail
extraction)/delete. `STLViewer` (three.js) ported from the Jinja viewer; `api.upload()` multipart helper.
Verified: mark-printed flips status + plate checks, STL upload → 3D render → delete.

### §8 — Order form: new + edit (commit `db4d841`) + colour-swatch tweak (`1c75846`)
`POST /api/orders` + `PUT /api/orders/:id` (faithful port of `order_new`/`order_edit`). Multi-plate builder,
per-plate brand→material→colour cascade (selects inventory filaments), 3MF import (reuses `/api/parse-3mf`),
retail VAT/quantity. Added swatches to the filament colour dropdown options.
**Root cause of a long debug:** a controlled radix `Select` whose `value` is set during edit-prefill while
its `<SelectItem>` options aren't mounted yet fires `onValueChange("")` and wipes the value; the cascade
reset handlers then chain-clear via stale closures. **Fix:** gate the form body render until data is loaded
AND prefill is applied (`prefillDone`), so each Select mounts exactly once with a valid value whose option
already exists. Apply this pattern to any prefilled form with dependent selects.

## Open issues (not yet addressed)
- **3MF thumbnail deletion** (`file_delete`) removes *all* of an order's plate thumbnails, not just the
  deleted 3MF's — mirrors a pre-existing Jinja bug. Proper fix needs an `OrderFile.parent_file_id` column +
  migration. Rare multi-3MF-per-order case; deferred.
- **Order stock-deduct race** — no row locking on concurrent creates. Left as-is: the app uses a
  warn-but-allow stock policy (negative stock is permitted by design) and is a single-operator tool.

## Environment gotchas (root causes)
- **Vite proxy must target `127.0.0.1:5000`, not `localhost`** — on Windows Node resolves `localhost` to
  IPv6 `::1` first and the proxy 502s.
- **Docker Desktop** must be launched via the Bash tool with `dangerouslyDisableSandbox: true` (the sandbox
  kills the detached GUI process). Daemon takes ~80s. It has crashed mid-session; re-launch + `docker compose
  up -d` (seeded data persists in the volume unless `down -v`).
- **WSL clears `/tmp` on distro shutdown** between tool calls — write CodeRabbit output to a `/mnt/c/...` path.
- **MariaDB credentials** only apply on first volume init — a stale `db_data` volume causes "access denied";
  `docker compose down -v` then up.

## Current state / next step
Login, Dashboard, Filaments, and all of Orders (list/detail/form) are migrated and verified.
**In progress:** Settings — `GET /api/settings` done; `PUT /api/settings` + `useUpdateSettings` added
(uncommitted); the Settings page + verification remain.
**Remaining pages:** Settings · quote + combined quote · statistics (Recharts) · admin/users.
Then: build the SPA into Flask static and update Dockerfile/compose for prod (serve same-origin).
