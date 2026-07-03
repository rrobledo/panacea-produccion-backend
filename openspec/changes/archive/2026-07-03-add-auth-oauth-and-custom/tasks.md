## 1. Users table and migration

- [x] 1.1 Add `app/models/user.py`: `User` SQLAlchemy model — `id, email
      (unique, indexed), password_hash (nullable), role (enum: admin/user,
      default user), email_verified (bool, default False), created_at,
      updated_at`
- [x] 1.2 Add `migrations/0002_create_users.sql`: creates the `role` enum
      type and the `users` table (additive only, no changes to existing
      tables)
- [x] 1.3 Mirror the migration into `docker/init-db/*.sql` so local Postgres
      (docker-compose) stays in sync
- [x] 1.4 Apply the migration to the local/dev database and confirm the
      table exists via `\d users` (or equivalent)

## 2. Dependencies and config

- [x] 2.1 Add `python-jose[cryptography]`, `passlib[bcrypt]`, `bcrypt` to
      `requirements.txt`
- [x] 2.2 Move `httpx` from `requirements-dev.txt` to `requirements.txt`
      (needed at runtime for the Google token/userinfo exchange)
- [x] 2.3 Add new settings to `app/config.py`: `secret_key` (empty default,
      matching this repo's existing settings convention — guarded at usage
      time in `app/auth/utils.py` rather than at import/startup, like
      `cron_secret`), `access_token_expire_days` (default 7), `base_url`,
      `frontend_urls` (+ `frontend_urls_set` property), `google_client_id`,
      `google_client_secret`
- [x] 2.4 Update `.env.example` with the new variables and a placeholder
      `SECRET_KEY`

## 3. Auth module scaffolding

- [x] 3.1 Add `app/auth/strategies/base.py`: `BaseStrategy` ABC with
      `as_dependency()`, ported from panacea-socios-backend
- [x] 3.2 Add `app/auth/utils.py`: `hash_password`/`verify_password`
      (passlib bcrypt), `create_token`/`decode_token` (python-jose, HS256,
      payload includes `sub`, `email`, `role`, `exp`). `signing_key()` raises
      `RuntimeError` if `SECRET_KEY` is unset (deviates from design.md's
      "required setting" framing to match this repo's existing
      empty-default-then-guard-at-use convention, e.g. `cron_secret`)
- [x] 3.3 Add `app/auth/state.py`: `generate_state`/`verify_state` — signed,
      short-lived (10 min) JWT carrying an optional `redirect_uri`, for
      OAuth CSRF protection
- [x] 3.4 Add `app/auth/passport.py`: `Passport` strategy registry
      (`use`/`authenticate`), ported from panacea-socios-backend
- [x] 3.5 Add `app/auth/dependencies.py`: `require_role(*roles)` — built on
      `passport.authenticate("jwt")`, checks `current_user.role`, 403 on
      mismatch (401 handled by the JWT strategy itself if unauthenticated)

## 4. Local authentication strategies

- [x] 4.1 Add `app/schemas/auth.py`: `RegisterRequest` (email, password —
      no `role` field), `TokenResponse` (access_token, token_type, user_id,
      role). Also pinned `email-validator` in `requirements.txt` (required
      by pydantic's `EmailStr`, not previously a direct dependency)
- [x] 4.2 Add `app/auth/strategies/jwt.py`: `JWTStrategy` — decodes bearer
      token, loads the `User` by `sub` via `AsyncSession.get` (this repo is
      async SQLAlchemy, unlike socios-backend's sync `Session`), 401 on
      expired/invalid/missing user
- [x] 4.3 Add `app/auth/strategies/local.py`: `LocalStrategy` — validates
      email + password (OAuth2 password grant form) against `users`,
      rejects if `password_hash` is `NULL` or doesn't match
- [x] 4.4 Add `app/auth/strategies/register.py`: `RegisterStrategy` —
      creates a `users` row with hashed password, `role="user"` (hardcoded,
      ignoring any role in the request), `email_verified=False`; 409 on
      duplicate email

## 5. Google OAuth2 strategy and router

- [x] 5.1 Add `app/auth/strategies/google.py`: exchanges `code` for a
      Google access token via `httpx.AsyncClient` (async, unlike
      socios-backend's sync `httpx` calls — matches this repo's fully async
      request handling), fetches userinfo, looks up a `users` row by
      returned email; 404 "no account found for this email; register
      first" if no match (no auto-create)
- [x] 5.2 Add `app/auth/router.py`: `POST /auth/register`,
      `POST /auth/token`, `GET /auth/google` (initiate — validates
      `redirect_uri` against `frontend_urls_set`, builds authorize URL with
      signed `state`), `GET /auth/google/callback` (verifies `state`,
      delegates to `GoogleStrategy`, issues JWT via shared `_finish` helper)
- [x] 5.3 Wire up `app/auth/__init__.py` instantiating the singleton
      `passport` with `jwt`, `local`, `register`, `google` strategies
      registered
- [x] 5.4 Register `auth.router` in `app/main.py` — smoke-tested: app
      imports cleanly and all four `/auth/*` routes appear in `app.routes`

## 6. Profile endpoint

- [x] 6.1 Add `app/schemas/profile.py`: `ProfileResponse` (`id`, `email`,
      `role`, `email_verified` — no `password_hash`)
- [x] 6.2 Add `app/routers/profile.py`: `GET /profile/me`, protected by
      `passport.authenticate("jwt")`, returns the current user as
      `ProfileResponse`
- [x] 6.3 Register `profile.router` in `app/main.py` (no `/costos` prefix,
      alongside `cron`) — smoke-tested: route appears in `app.routes`

## 7. Tests

- [x] 7.1 Add `tests/unit/test_auth.py`: register (success, duplicate
      email, role field ignored), local login (success, bad password, no
      password set) — 6 tests, all passing
- [x] 7.2 Add `tests/unit/test_google_oauth.py`: initiate redirects with
      signed state, callback with mocked `_exchange_code` (existing user →
      token issued; unknown email → 404; invalid state → 400) — 4 tests, all
      passing
- [x] 7.3 Add `tests/unit/test_role_authorization.py`: `require_role`
      allows matching role, 403 on mismatch, accepts multiple roles — 3
      tests calling the dependency's inner function directly, all passing
- [x] 7.4 Add `tests/unit/test_profile.py`: `GET /profile/me` returns the
      caller's identity when authenticated, 401 when not, response excludes
      `password_hash` — 2 tests, all passing

Full suite: `pytest -q` → 90 passed (75 pre-existing + 15 new), no
regressions.

## 8. Docs and cutover

- [x] 8.1 Update `README.md` with an Authentication section: `users` table,
      JWT role claim, endpoint list, and how to promote a user to `admin`
- [x] 8.2 Document how to register a Google OAuth Client (redirect URI =
      `BASE_URL + /auth/google/callback`) for local/staging use
- [ ] 8.3 Deploy to staging; smoke-test register, local login, and Google
      login end-to-end; confirm `require_role` grants/denies correctly for
      both roles — **not done in this session: requires staging deploy
      access and a real Google OAuth Client, both outside this coding
      session's reach.** Manual follow-up.
- [ ] 8.4 Manually promote one staging account to `role="admin"` via direct
      SQL to validate the full role-authorization path — **blocked on 8.3.**
      Manual follow-up.
