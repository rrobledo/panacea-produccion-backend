## Why

`panacea-produccion-backend` has no user-level authentication today — the only
access control is a static shared `X-API-Key` header (`app/deps.py`) checked
on mutating routes, plus a separate cron secret. There is no concept of a
logged-in user, no roles, and no way for a client to ask "who am I / what can
I do." `panacea-socios-backend` already solved this with a Passport.js-style
OAuth2 + local-password auth module backed by a Google Authorization Code
flow. We need the same identity/role foundation here — a dedicated `users`
table (email, password hash, role) that both local login and Google OAuth
login resolve against by email — plus a `/profile/me` endpoint so a connected
client can read back the current user's identity and role.

## What Changes

- New `users` table: `id, email (unique, indexed), password_hash (nullable),
  role (enum: admin/user, default user), email_verified (default false),
  created_at, updated_at`. Added via a new hand-written SQL migration
  (`migrations/0002_create_users.sql` + mirrored in `docker/init-db/`), since
  this repo has no Alembic.
- New `app/auth/` module, ported from `panacea-socios-backend`'s
  Passport-style strategy pattern (`passport.py`, `state.py`, `utils.py`,
  `dependencies.py`, `router.py`, `strategies/{base,jwt,local,register,google}.py`):
  - `POST /auth/register` — public self-service signup with email + password
    (role defaults to `user`).
  - `POST /auth/token` — local email/password login (OAuth2 password grant),
    issues a JWT.
  - `GET /auth/google` / `GET /auth/google/callback` — Google-only OAuth2
    Authorization Code flow (CSRF-protected via a signed `state` JWT,
    matching the socios-backend pattern). Resolves the verified Google email
    against `users.email`; unmatched emails are rejected (no auto-create) so
    only accounts that registered locally (or were provisioned) can log in
    via Google, mirroring current socios-backend Google-strategy behavior.
- JWT payload gains a `role` claim (alongside existing `sub`/`email`-style
  claims); a new `require_role(*roles)` dependency authorizes endpoints by
  role read from the token.
- New `GET /profile/me` endpoint (`app/routers/profile.py`), protected by the
  JWT strategy, returning the authenticated user's `id`, `email`, `role`, and
  `email_verified`.
- New runtime dependencies: `python-jose[cryptography]`, `passlib[bcrypt]`,
  `bcrypt`, and promoting `httpx` from test-only to a runtime dependency (for
  the Google token/userinfo exchange).
- New settings in `app/config.py`: `secret_key`, `access_token_expire_days`,
  `base_url`, `frontend_urls`, `google_client_id`, `google_client_secret`.
- The existing `require_api_key` / `require_cron_secret` machine-to-machine
  checks are untouched — this is additive user auth layered alongside the
  existing service-to-service key, not a replacement for it.

## Capabilities

### New Capabilities
- `user-identity`: the `users` table as the source of truth for credentials
  (email, password hash, role, verification status).
- `authentication`: local email/password registration + login, and Google
  OAuth2 social login, both resolving/authenticating against `users` and
  issuing a role-bearing JWT.
- `role-authorization`: role-based access control for REST endpoints via a
  `require_role(*roles)` dependency backed by the JWT's `role` claim.
- `user-profile`: the `GET /profile/me` endpoint exposing the connected
  user's identity and role.

### Modified Capabilities
(none — no existing `openspec/specs/` baseline for auth in this repo)

## Impact

- Code: new `app/models/user.py`, new `app/auth/` package (~9 files), new
  `app/routers/profile.py`, new `app/schemas/auth.py` /
  `app/schemas/profile.py`, `app/main.py` (register `auth` and `profile`
  routers), `app/config.py` (new settings), `app/deps.py` (unchanged, but
  auth deps will live alongside it).
- Database: new `migrations/0002_create_users.sql` (users table + role
  enum), applied manually like `migrations/0001_...` today; mirrored in
  `docker/init-db/*.sql` for local dev.
- Dependencies: `requirements.txt` gains `python-jose[cryptography]`,
  `passlib[bcrypt]`, `bcrypt`; `httpx` moves from `requirements-dev.txt` to
  `requirements.txt`.
- Config/env: `.env` / `.env.example` (if present) gain `SECRET_KEY`,
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `BASE_URL`, `FRONTEND_URLS`,
  `ACCESS_TOKEN_EXPIRE_DAYS`.
- Clients: `panacea-front` (or whichever client integrates this) gains new
  `/auth/*` and `/profile/me` endpoints to call; existing `X-API-Key`-gated
  endpoints are unaffected.
- Tests: new `tests/unit/test_auth.py`, `tests/unit/test_profile.py`
  following the existing `client`/`session` fixture pattern in
  `tests/conftest.py`.
