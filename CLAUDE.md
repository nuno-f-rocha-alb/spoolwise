# Spoolwise — project instructions for Claude

## Working notes (standing instruction)
On any multi-step or multi-session task, keep a **working journal** — `MIGRATION-JOURNAL.md`
for the React SPA migration — current: append a new `§N` section **proactively** as each
milestone, decision, or fix completes, **without being asked**. Record **root causes**, not just
fixes. Keep it structured (decisions + root causes + state), not a transcript. Commit the journal
alongside the related change. A one-line pointer to it also lives in project memory.

## Dev stack (stable facts)
- **Backend:** `docker compose up -d` → MariaDB on host `:3307`, Flask on `:5000`. The gitignored
  `docker-compose.override.yml` builds local code and mounts `./app`, `./run.py`, `./scripts`.
  Flask runs without the reloader → run `docker compose restart app` after editing backend code.
- **Frontend:** `npm --prefix frontend run dev` → Vite on `:5173`, proxies `/api`, `/files`,
  `/static` → `127.0.0.1:5000` (use the IPv4 literal, not `localhost`).
- **Seed dev data:** `docker compose exec -T app sh -c 'cd /code && PYTHONPATH=/code python scripts/seed_dev.py'`
- **Code-review gate (WSL):** `wsl -d Debian -- bash -c 'cd /mnt/c/Users/nunob/Repositorios/printing_app && ~/.local/bin/coderabbit review --agent'`
- Migration work is on branch `feature/react-spa-migration`. The old Jinja app must keep working
  until the SPA reaches full parity; `main` stays shippable.
- Public `/api/orders/pending` (CORS, no auth) is consumed by an external dashboard — do not break it.
