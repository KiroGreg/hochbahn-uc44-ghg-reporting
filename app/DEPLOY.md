# Deploy to the UC44 VM

Target: `datadrivensolutions2.informatik.uni-hamburg.de` (134.100.14.58),
user `vmstudents`. The ops team runs an nginx + TLS reverse proxy on
the host that forwards `80` → `FRONTEND_PORT` (and `443` → same).

## 1. First-time setup on the VM

```bash
ssh vmstudents@datadrivensolutions2.informatik.uni-hamburg.de

# Clone (or pull) the repo
git clone <gitlab-url>.git uc44
cd uc44/app

# Generate a token and write the .env OVERRIDE file (DO NOT commit)
cp .env.example .env
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "UC44_AUTH_TOKEN=$TOKEN" >> .env
# .env should also set: UC44_ENV=vm and OPENAI_API_KEY
# (see local/UC44 Accounts & Access). For a real deploy, change
# POSTGRES_PASSWORD + DATABASE_URL too.

# Build + start (TLS overlay)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps         # db, backend, frontend should be healthy
```

Then share `UC44_AUTH_TOKEN` out-of-band (Slack, password manager) with
anyone who should be able to log in.

### Configuration model (committed defaults + pull-safe override)

Config is layered, so a fresh clone runs locally with zero setup while the
VM keeps its own secrets across deploys:

| File | Committed? | Loaded | Purpose |
|------|-----------|--------|---------|
| `app/.env.defaults` | **yes** | always (1st) | Safe local defaults (`UC44_ENV=local`, dev DB creds, open auth). |
| `app/.env` | **no** (git-ignored) | optional (2nd, wins) | Real secrets + `UC44_ENV=vm`. |

Because `app/.env` is git-ignored, **`git pull` never overwrites it** — the VM
keeps its own config. Anything set there overrides the committed default of the
same name. Confirm which config is live any time with `GET /api/health` →
`{"env":"vm","db":"postgresql+psycopg"}`.

## 2. Hand the public port to the ops admin

The compose file exposes the SPA on `${FRONTEND_PORT:-8080}` of the VM
(bound to all interfaces). Tell the admin:

> "Bitte Port 80/443 → `localhost:8080` weiterleiten (UC44 THG Reporting Demo)."

The backend container is **not** published to a host port — it's only
reachable on the internal docker network, so an attacker who finds the
VM IP can't bypass nginx by hitting `:8000`.

## 3. Updating

```bash
cd uc44 && git pull          # never touches the git-ignored app/.env
cd app
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## 4. Operations cheatsheet

| Action                  | Command                                |
| ----------------------- | -------------------------------------- |
| Status                  | `docker compose ps`                    |
| Tail logs               | `docker compose logs -f backend`       |
| Restart backend         | `docker compose restart backend`       |
| Rotate the auth token   | edit `.env`, `docker compose up -d`    |
| Stop everything         | `docker compose down` (keeps DB data)  |
| Verify auth from VM     | `curl -s http://localhost:8080/api/auth/status` |
| Check live env/DB       | `curl -s http://localhost:8080/api/health` |
| Back up the DB          | `docker compose exec db pg_dump -U uc44 uc44 > backup.sql` |

> **DB data lives in the `pgdata` named volume.** `docker compose down`
> keeps it; **`docker compose down -v` deletes it** (all runs, samples,
> predictions and the decision history). Back up before destructive ops.

> **Schema migrations (no Alembic).** `init_db()` runs `create_all` (creates
> only *missing tables*) plus a small **idempotent, additive-only** migration
> step (`_run_additive_migrations()` in `core/db.py`) that `ALTER … ADD COLUMN`s
> only what is missing, guarded by an inspector check. New nullable/defaulted
> columns therefore apply automatically on the next backend start and back-fill
> existing rows — **no manual ALTER and no `down -v` on the VM** (which has real
> data). Example: the `warengruppe.aktiv` soft-delete flag. Destructive or
> non-additive schema changes still need a hand-written migration.

## 5. What's protected

- `GET  /api/health` and `GET /api/auth/status` are **open** (so nginx
  and the SPA login screen can probe without a token).
- Every other route (`/api/upload/*`, `/api/plausibility/*`,
  `/api/prediction/*`, `/api/dashboard*`) requires
  `Authorization: Bearer $UC44_AUTH_TOKEN`. Missing/wrong token → 401.
- The SPA shows a login screen on first load, stores the token in
  `localStorage`, attaches it to every request via an HTTP interceptor,
  and bounces the user back to login on any 401.
- If `UC44_AUTH_TOKEN` is empty/unset, the API runs **open** — only do
  that for local development.

## 6. What's intentionally *not* in scope

- No per-user accounts, no rate limiting, no audit log.
- HTTPS termination is the ops admin's nginx — we trust it.
- The token is shared between users; rotate it when somebody leaves.
