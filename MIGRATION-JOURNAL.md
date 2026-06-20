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

### §9 — Settings page
`GET /api/settings` (added in §8) + `PUT /api/settings` (ports the Jinja settings POST). Settings page:
electricity/printer, business defaults (profit %, currency), retail mode + default VAT. `useUpdateSettings`
invalidates `["settings"]`, `["auth","me"]`, dashboard/orders/filaments (currency + retail mode are shown
app-wide). Verified live: load → prefill → edit → save → persist, light + dark.
**Note:** a manual `curl` reset with a `€` in the JSON body mis-encoded earlier numeric fields in the shell
(set electricity/watts to 0) — a *test-harness* issue, not a code bug; the UI save path is correct. Lesson:
reset seed state via the UI or a file-based `--data @`, not inline shell JSON containing non-ASCII.

### §10 — Order-form polish (swatches + duplicate plate)
User feedback: the colour swatch belongs on the *order-create* per-plate colour dropdown (it had been
added to the new-filament form in §5). Added `FilamentSwatch` to each option there. Also added a
**Duplicate plate** button (deep-copies a plate's time + filament rows, inserts it right after) — handy for
multi-copy orders. Verified live: swatches render in the cascade; Duplicate produces an exact Plate 2 copy.
Adopted the **ponytail** minimalism ladder as the default coding lens from here on (write only what the task
needs; reuse stdlib/native/installed/one-liners; never cut validation/security/a11y).

### §11 — Quote pages: single + combined
Ported the two customer-facing print views (`quote.html` / `quote_combined.html`).
- **Backend:** the single quote needs **no new endpoint** — `serialize_order_detail` already
  carries every field it shows (name/customer/links/plates/qty/VAT/prices), so `/quote/:id` reuses
  `GET /api/orders/:id`. Added one endpoint `GET /api/quote/combined?ids=` (faithful port of
  `order_quote_combined`): user-scoped, `created_at asc`, 404 on no match, 400 on empty ids;
  aggregates `subtotal/vat_total/total/has_any_vat/vat_rates` over **billable (non-internal)** orders
  only. New `serialize_quote_item` (money fields only — the customer view never sees cost/profit).
- **Frontend:** `Quote.tsx` (reuses `useOrderDetail`) + `QuoteCombined.tsx` (`useCombinedQuote`).
  Shared `QuoteFrame` (standalone print-friendly wrapper: eyebrow/meta header, `window.print()` +
  back link hidden via `print:hidden`, logo footer) and `PriceBox` (brand blue→indigo gradient).
  Added `formatDate` (`%d %b %Y` parity) and quote types.
- **Routing decision (deliberate):** mounted both quote routes as **direct children of
  `ProtectedRoute`, OUTSIDE `AppLayout`** — these are standalone customer documents, so no app nav
  shell. `/quote/combined` is registered **before** `/quote/:id` so "combined" isn't captured as the
  `:id` param.
- **Verified live (light + dark):** single quote no-VAT (1,30 €) and VAT branch (line-item table +
  Subtotal/VAT 23%/Total 1,60 €); combined excludes the personal-use order ("1 personal-use order
  excluded", total 8,08 €) and aggregates VAT (8,38 €) with the per-item VAT tag. No console errors.
  Seeded orders carry no VAT (retail mode off), so the VAT branches were exercised by temporarily
  enabling retail + tagging order 1, screenshotting, then **reverting to the seed baseline**
  (order 1 sell back to 1.299415, retail off).

### §12 — Statistics (Recharts)
Ported the business-analytics page (`stats.html` + its Chart.js scripts).
- **Backend:** added `GET /api/stats` — a faithful port of the `stats` route's aggregation. Same
  rule: only **delivered commercial** orders feed revenue/profit; personal-use orders are tracked as
  real cost; monthly buckets keyed by `delivered_at` (last 24). Returns `totals`, `counts`,
  `monthly[]`, `top_filaments[]` (top 10 by cost), and in-stock `stock[]` (value-desc). Charts derive
  their inputs from `monthly`/`stock` client-side, so no separate `chart_*` payloads (vs. the Jinja
  route which pre-baked `chart_monthly`/`chart_stock` for Chart.js). Renamed the Jinja leftover
  `(removido)` → `(removed)` to match the SPA's existing convention.
- **Frontend:** `Statistics.tsx` with **Recharts** (`ComposedChart`: revenue/cost bars + profit line;
  horizontal `BarChart` with per-filament `Cell` colors for stock value). Recharts reads the design
  tokens directly (`fill="var(--success)"` etc.) so the charts **auto-adapt to dark mode** — no
  theme-watching JS like the Jinja Chart.js block needed. KPI cards, retail/VAT row (conditional on
  retail mode), print-time/personal/inventory panels, monthly + top-filament + inventory tables,
  order-status panel. `maxBarSize={64}` so a single-month bucket doesn't stretch into slabs.
- **Verified live (light + dark):** marked orders 1+2 delivered to populate revenue (8,08 €), profit
  (+1,87 €, margin 23.1%), the monthly chart, and top-filaments; enabled retail to confirm the VAT
  KPI row renders; the stock chart shows real per-filament colors. Then **reverted to the seed
  baseline** (retail off, all 3 orders back to pending, 0 delivered). No console warnings.

### §13 — Admin: manage users (final page)
Ported the admin user-management UI (`admin/users.html` + the `admin_bp` routes, which live in
`auth.py`, not `routes.py` — there was never a `/admin/users` route in `routes.py`).
- **Backend:** 5 JSON endpoints under `/api/admin/users*` (list/create/toggle-active/reset-password/
  delete), reusing `admin_required` + `hash_password` from `auth.py`. Faithful guards: password
  required unless proxy-auth, duplicate→409, can't deactivate/delete self, can't delete the last
  admin, can't delete a user who still owns filaments/orders→409.
- **Bug found + fixed (not pure parity):** deleting a freshly-created user 500'd — `settings.user_id`
  has no DB cascade and `ensure_defaults` always seeds Setting rows, so the FK blocked the delete.
  The Jinja `users_delete` has the **same latent bug** (identical unguarded `delete(user)`). Fixed by
  cascade-deleting the user's own Setting rows first (they're their config, unlike orders/filaments
  which the guard protects). Same precedent as the §5 filament raw-500→friendly-error fix.
- **Frontend:** `Users.tsx` — table + create/reset dialogs built on the **installed** radix
  `alert-dialog` as the modal shell (no new `@radix-ui/react-dialog` dep), plain `useState`/`FormData`
  forms (no RHF/Zod for 5 fields — backend validates). Self-row Deactivate/Delete disabled.
  **Deleted dead `ComingSoon.tsx`** — every route is now real.
- **Verified live (light + dark):** created `testuser` through the UI dialog (list refreshed),
  exercised every guard via the API (self 400s, duplicate 409, empty-password 400, toggle off/on,
  reset ok), confirmed the delete dialog + delete after the FK fix; cleaned up to the seed baseline
  (only `admin`). No console errors.

### §14 — Production build + SPA cutover (serve same-origin from Flask)
Wired the built SPA into the container and flipped the UI from Jinja to React.
- **Multi-stage Dockerfile:** `node:20` stage runs `npm ci && npm run build`; the Python stage
  `COPY --from=spa /spa/dist ./app/spa`. `.gitignore` + `.dockerignore` ignore `app/spa` (built in-image).
- **Flask now serves the SPA:** `_register_spa` adds a catch-all (`/`, `/<path:path>`) that serves real
  built assets from `app/spa` and otherwise returns `index.html` (client-side routing → deep links +
  refresh work). `/api`, `/files`, `/static` have more-specific routes and win; undefined `/api/*`/
  `/files/*` paths are guarded to 404 rather than leaking `index.html`.
- **Jinja retired:** the three server-rendered blueprints (`main_bp`, and auth `bp` + `admin_bp`) are no
  longer registered. The 5 non-HTML endpoints the SPA still needs (`/api/orders/pending`, `/api/parse-3mf`,
  `/files/<id>` + `/stl` + `/plate/<n>/stl`) are re-registered from the routes module via `add_url_rule`.
  The app-level `_sso_hook` `before_request` stays, so hybrid auth (local + Authelia) is unaffected. The
  Jinja route code + templates remain in the tree as dead code (helper functions in `routes.py` are still
  imported by `api.py`); scrubbing them is a separate cleanup.
- **Root cause — anon 500:** with the auth blueprint gone, `login_manager.login_view = "auth.login"` made
  `login_required` redirect to a dead endpoint → `url_for` 500 on every protected route for anonymous
  requests. Fixed by `login_view = None` → clean **401** (the SPA's `/api/auth/me` drives the client-side
  redirect to `/login`). Verified anon `/files/x`, `/api/dashboard` → 401, not 500.
- **Root cause — vacuous typechecks:** my earlier `npx tsc --noEmit` passes were checking nothing — the
  frontend uses a **composite/references** tsconfig, so the real typecheck is `tsc -b` (what `npm run build`
  runs). The prod build surfaced 3 genuine type errors in already-committed code (two Recharts `Tooltip`
  formatter signatures, one `password?:` optionality in the user-create dialog). Fixed all three.
  **Lesson:** verify the frontend with `npm run build`, never bare `tsc --noEmit`.
- **CI:** `docker.yml` `paths:` now includes `frontend/**` (else a frontend-only change wouldn't rebuild).
  `docker-compose.yml` needs no change — same image/port/env; hybrid-auth env vars already wired.
- **Verified:** curl matrix on `:5000` (SPA routes 200, API JSON 401/200, public pending 200, undefined
  api 404, anon protected 401); browser login through the Flask-served build → dashboard with live data
  (same-origin, no proxy); the multi-stage image builds and contains `app/spa`.

### §15 — Promotion to `main` + image published
Cutover shipped.
- **Backup:** old Jinja `main` (`e4e98bd`) preserved as branch `backup/jinja-main` (pushed to origin)
  before touching `main`.
- **Promotion:** `main` had not diverged, so `feature/react-spa-migration` → `main` was a clean
  **fast-forward** (no history rewrite). `main` now at `bf18786`. Feature branch also pushed.
- **CI:** the push to `main` triggered `docker.yml`; the multi-stage build succeeded (~48s) and pushed
  `nunobifes/spoolwise:latest`. User recreates the container in Portainer.
- **Deploy safety:** no schema change → existing DB volume untouched; `docker-compose.yml` unchanged;
  hybrid-auth env vars already wired. First boot runs the additive migrations (idempotent).
- **Rollback caveat (root cause):** CI tags only `:latest`, so this push **overwrote** the previous
  Jinja image at that tag — rollback means redeploying from `backup/jinja-main` (re-run CI or build
  locally). Adding SHA/version tags to the workflow would make rollbacks cleaner (deferred — would
  need a workflow change + the user's call on a tagging scheme).
- Minor CI annotation: the GitHub Actions (`checkout@v4`, `build-push-action@v5`, `login-action@v3`)
  are on the Node-20 deprecation list — a version bump someday, non-blocking.

### §16 — STLViewer THREE.js disposal (post-migration cleanup)
Fixed the pre-existing GPU-memory leak flagged in §14's CodeRabbit pass: the 3D viewer's `GridHelper`
was never released, so each open/close of the viewer leaked its geometry + material. Hoisted `grid` to
the effect scope and added `scene.remove(grid)` + `grid.geometry.dispose()` + `grid.material.dispose()`
to the cleanup (alongside the existing mesh/controls/renderer disposal; also added the missing
`scene.remove(mesh)`). The lights hold no GPU resources, so they need no disposal. Verified with
`npm run build`.

### §17 — Post-migration cleanup: CI hardening + Jinja scrub
Knocked out the deferred follow-ups.
- **CI (`docker.yml`):** bumped the Node-20-deprecated actions (`checkout@v4→v7`, `login-action@v3→v4`,
  `build-push-action@v5→v7`); added an immutable `:${{ github.sha }}` tag alongside `:latest` (so any
  build can be pinned/rolled back to); added `workflow_dispatch` so any branch can be rebuilt on demand
  (e.g. to republish a rollback image from `backup/jinja-main`). Workflow-only changes don't match the
  `paths` filter, so they're verified on the next code-triggered build.
- **Jinja scrub:** removed all now-dead server-rendered code. `routes.py` 1877→784 (kept the helper
  functions `api.py` imports + the 5 non-HTML routes `main_bp` still serves: public `/api/orders/pending`,
  `/api/parse-3mf`, `/files/*`). `auth.py` 397→217 (dropped the `/login`,`/logout` + admin-users Jinja
  handlers and their blueprints; kept the login manager, password/SSO helpers, `admin_required`,
  `_trusted_header_login`). Deleted `app/templates/` (13 files). Dropped 3 unused deps — `Bootstrap-Flask`,
  `WTForms`, `Flask-WTF` (the Jinja forms were plain HTML, no `FlaskForm`) — plus the `Bootstrap5` wiring,
  the `duration` template filter, and the `inject_currency`/auth-flags context processors. `main_bp` now
  holds only the 5 kept routes, so `__init__` registers it directly again (dropped the §14 `add_url_rule`
  workaround). Trimmed every newly-unused import.
  **Method/root cause:** the keep/drop functions were interleaved across a 1877-line file, so I sliced by
  verified line-range (preserving kept code byte-for-byte) rather than hand-editing — far less risk of
  nicking a live helper. Boundaries + unused imports were confirmed by grep, then the whole thing by
  runtime checks.
- **Verified:** `create_app()` boots (38 url rules); full endpoint matrix on `:5000` green (SPA root +
  deep-link serve, public pending, authed me/dashboard/stats/admin, file 404); and a **fresh image build**
  with the trimmed `requirements.txt` imports cleanly with Bootstrap-Flask/WTForms/Flask-WTF **absent**.

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
**All pages migrated and verified:** Login, Dashboard, Filaments, Orders (list/detail/form),
Settings, both Quote pages, Statistics, and Admin/users. The SPA is at feature parity with the Jinja
app; every route is real (no `ComingSoon` left).
**Migration complete and shipped (§15).** All pages migrated, the production build is wired (§14), and
`main` is now the SPA version (`bf18786`) with `nunobifes/spoolwise:latest` rebuilt and pushed by CI.
The old Jinja app is preserved on `backup/jinja-main`. Awaiting the Portainer container recreate.
Post-migration cleanup done (§17): SHA image tags + manual dispatch, Node-20 action bumps, and the full
Jinja scrub (dead routes/templates/deps removed). Only the two long-standing open issues below remain,
both pre-existing and deferred by design.
