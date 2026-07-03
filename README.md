# panacea-produccion-backend

FastAPI port of `panacea-backend`'s costing/production domain (insumos,
productos, proveedores, cuenta corriente, planning/programacion), deployed
on Vercel against the same shared Postgres instance. See
`openspec/changes/produccion-costos-api/` for the full proposal/design/specs.

## Local setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes requirements.txt + test tools
```

Copy `.env.example` to `.env` and fill in real values (never commit `.env`):

```bash
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (pooled endpoint, e.g. Neon `-pooler` host). Accepts `postgres://` or `postgresql://`; converted internally to the `asyncpg` driver URL. |
| `API_KEYS` | Comma-separated list of accepted `X-API-Key` values for mutating (POST/PUT/PATCH/DELETE) requests. |
| `CRON_SECRET` | Separate secret required (as `Authorization: Bearer <secret>`) on the scheduled cascade endpoint. |
| `CORS_ORIGINS` | Comma-separated list of allowed browser origins. No wildcard. |
| `SECRET_KEY` | Signing key for auth JWTs and OAuth `state` tokens. No insecure default — any `/auth/*` or `/profile/*` request fails with a 500 if unset. |
| `ACCESS_TOKEN_EXPIRE_DAYS` | How long an issued login JWT stays valid, in days. Defaults to `7`. |
| `BASE_URL` | Used to build the Google OAuth2 callback `redirect_uri` (`<BASE_URL>/auth/google/callback`). Defaults to `http://localhost:8000`. |
| `FRONTEND_URLS` | Comma-separated allow-list of frontend URLs OAuth is permitted to redirect back to after login. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth2 Client credentials — see "Authentication" below. |

`DATABASE_URL` is only required for routes that hit the database — the app
boots and `/health` works without it.

## Local Postgres (Docker)

Tests and local development that touch the database use a disposable local
Postgres container — **not** the shared production instance. This mirrors
the production schema closely enough to run real queries against it,
including the `costos_cuentacorrienteproveedorafect` trigger that maintains
`importe_pendiente`/`estado` (see `design.md`'s "Schema Introspection
Findings" for why that trigger matters).

Requires Docker + Docker Compose.

```bash
docker compose up -d          # starts Postgres on localhost:55432, applies
                               # docker/init-db/*.sql (schema + trigger) on
                               # first boot
docker compose down           # stop (add -v to also wipe the data volume)
```

To point the app itself at this local DB (as opposed to running tests,
which configure this automatically — see below):

```bash
export DATABASE_URL="postgres://panacea:panacea@localhost:55432/panacea_test"
```

`docker/init-db/*.sql` only covers the tables this service actually uses
(spread across numbered files as capabilities were added: cuenta corriente
+ trigger, productos/costeo + the `articulos_final` view stand-in,
remitos/clientes, analytics) — not the full production schema. Add to it as
new tables are implemented.

## Run the server locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- Health check: `curl http://localhost:8000/health`
- Interactive docs: http://localhost:8000/docs
- Raw OpenAPI schema: http://localhost:8000/openapi.json
- Ported endpoints are mounted under `/costos` (e.g. `/costos/insumos`,
  `/costos/proveedores`, `/costos/ctacteprov`), matching
  `panacea-front`'s existing `<host>/costos/...` base path.

## Run the tests

Start the local Postgres container first (see above), then:

```bash
source .venv/bin/activate
pytest
```

Or a single file/test:

```bash
pytest tests/unit/test_health.py -v
```

Tests connect to `postgresql+asyncpg://panacea:panacea@localhost:55432/panacea_test`
by default; override with `TEST_DATABASE_URL` if your container uses
different settings. Each test truncates the relevant tables before it runs,
so tests are safe to re-run and don't need to be run in any particular
order — including after an interrupted/killed previous run.

## Deployment (Vercel)

`vercel.json` routes all requests through `api/index.py` (the ASGI
entrypoint) and registers the monthly cascade as a daily Vercel Cron job
(`0 23 * * *` UTC — the handler itself checks whether today is actually the
last day of the month before doing anything). Required env vars
(`DATABASE_URL`, `API_KEYS`, `CRON_SECRET`, `CORS_ORIGINS`) must be set in
the Vercel project settings — never committed to source.

Vercel automatically sends `Authorization: Bearer $CRON_SECRET` on cron
invocations once `CRON_SECRET` is set as a project env var — no extra
wiring needed for `/internal/cron/monthly-cascade`'s auth check.

## Authentication

Separate from the `X-API-Key` machine-to-machine check above, the service
has a `users` table (`app/models/user.py`) backing individual user login —
email/password or Google OAuth2 — and role-based authorization
(`admin`/`user`, default `user`). See
`openspec/changes/add-auth-oauth-and-custom/design.md` for the full
rationale.

- `POST /auth/register` — public self-service signup with email + password.
  Role is always `user`; there is no way to self-assign `admin`.
- `POST /auth/token` — local email/password login (OAuth2 password grant
  form: `username`, `password`), returns a bearer JWT.
- `GET /auth/google` / `GET /auth/google/callback` — Google OAuth2
  Authorization Code flow. The verified Google email must already match an
  existing `users` row (from `/auth/register` or manual provisioning) — an
  unmatched email is rejected with 404, no account is auto-created.
- `GET /profile/me` — returns the authenticated caller's `id`, `email`,
  `role`, `email_verified`. Requires `Authorization: Bearer <token>`.

**Promoting a user to `admin`** is a manual DB update in this change (no
management endpoint yet):

```sql
UPDATE users SET role = 'admin' WHERE email = 'someone@example.com';
```

The promoted user must log in again — the JWT bakes in the role at issuance
time, so an already-issued token keeps its old role until it's reissued or
expires (`ACCESS_TOKEN_EXPIRE_DAYS`).

**Setting up a Google OAuth Client** (for local dev or staging):

1. In [Google Cloud Console](https://console.cloud.google.com/) → APIs &
   Services → Credentials, create an OAuth Client ID of type
   "Web application".
2. Add `<BASE_URL>/auth/google/callback` as an authorized redirect URI
   (e.g. `http://localhost:8000/auth/google/callback` for local dev).
3. Set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env` from the
   created client's credentials.
4. Register a `users` row for the Google account you'll test with (via
   `POST /auth/register`, or a direct `INSERT`) before attempting
   `GET /auth/google` — unmatched emails are rejected, not auto-created.

## `panacea-front` integration note (BREAKING for writes)

This service requires an `X-API-Key` header on every mutating request
(`POST`/`PUT`/`PATCH`/`DELETE`) — `panacea-front` currently sends no auth
header at all against the reference Django backend. This is the one
approved contract exception in this port (see `proposal.md`): paths and
payload shapes are otherwise unchanged, but **`panacea-front` needs a
config change to send `X-API-Key: <key>` on writes** before pointing at
this service for anything beyond read-only traffic. `GET` requests remain
open, matching current behavior.
