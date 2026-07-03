## Context

`panacea-produccion-backend` (FastAPI + SQLAlchemy 2.0 async, deployed on
Vercel) currently has zero user-level identity. The only access control is a
static shared `X-API-Key` header (`app/deps.py: require_api_key`) on
mutating `/costos/*` routes and a separate `require_cron_secret` for the
internal cron endpoint — both are machine-to-machine secrets, not user
authentication. There is no `users`/`socio`/`profile` table, no JWT, no
OAuth, no roles anywhere in this codebase.

`panacea-socios-backend` already built this from scratch: a Passport.js-style
strategy registry (`app/auth/`) supporting local email/password and OAuth2
Authorization Code Flow for Google/Facebook/Apple, JWT bearer tokens, and
(per its own in-flight `add-auth-oauth-and-custom` change) a plan to
introduce a dedicated `users` table with a `role` column instead of an
env-var admin allowlist. This change ports that pattern into
`panacea-produccion-backend`, scoped down per product decisions already made:
**Google is the only OAuth provider** (this is an internal staff tool, not a
consumer product — Facebook/Apple sign-in add no value here), and **local
registration is public self-service** (`POST /auth/register`, matching
socios-backend's actual shipped behavior) with role always defaulting to the
lowest-privilege value server-side.

Unlike socios-backend, this repo has **no Alembic** — schema changes are
hand-written numbered SQL files in `migrations/`, applied manually, mirrored
in `docker/init-db/*.sql` for local Postgres. There is also no existing
"person" table to attach identity to (socios-backend had `socios`); the new
`users` table is genuinely new and standalone, not a split-off of an
existing table, which avoids the backfill/FK migration complexity
socios-backend's own change has to deal with.

## Goals / Non-Goals

**Goals:**
- Introduce a `users` table (email, password hash, role, verification
  status) as the single source of identity for this service.
- Support local email/password registration and login, and Google OAuth2
  login, both resolving to the same `users` row by email.
- Give every user a `role` (`admin` | `user`, default `user`), readable from
  the issued JWT without a DB round-trip, and a `require_role(*roles)`
  dependency to gate endpoints by it.
- Add `GET /profile/me` so a connected client can read back its own
  identity/role.
- Keep the existing `X-API-Key` / cron-secret checks completely untouched —
  this is a new, additive authentication layer for individual users, not a
  replacement for the existing service-to-service key.

**Non-Goals:**
- No Facebook or Apple sign-in (Google only, per product decision).
- No retrofitting `require_role` onto existing `/costos/*` endpoints in this
  change — which endpoints (if any) should become role-gated is a product
  decision for a follow-up change, not something to guess here.
- No admin-management UI/endpoint for promoting a user to `admin`; that's a
  manual DB update in this change, same as socios-backend's approach.
- No session cookies — JWT bearer tokens only, matching socios-backend.

## Decisions

**1. New standalone `users` table, ported strategy-pattern `app/auth/`
module, scoped to Google + local (no Facebook/Apple).**
Mirroring socios-backend's `Passport` class (`app/auth/passport.py`) and
`BaseStrategy` ABC keeps the two codebases conceptually consistent for
engineers working across both, and the JWT/state/password-hashing utilities
(`utils.py`, `state.py`) can be ported near-verbatim. Facebook/Apple
strategies are dropped: this is an internal costing/production tool with no
existing consumer-facing signup flow, and adding two more OAuth app
registrations (including Apple's JWKS/private-key setup) for providers no
staff member would use is unjustified complexity. Alternative considered:
port all three strategies for future-proofing — rejected as YAGNI; the
`BaseStrategy` abstraction already makes adding a provider later cheap.

**2. `role` as a Postgres/SQLAlchemy enum with two values (`admin`, `user`),
default `user`.**
Same rationale as socios-backend: a fixed enum catches typos at the DB layer
and keeps `require_role` checks trivial. `user` (not `socio`) is the
non-admin default since this service has no membership concept — every
account is an internal user of the tool.

**3. Google OAuth resolves identity by verified email against
`users.email`; unmatched emails are rejected, not auto-created.**
This directly implements the ask ("use the user information by email in
order to identify the role"). It also matches socios-backend's *actual*
shipped `GoogleStrategy` behavior (`app/auth/strategies/google.py`: 404
"no account found for this email; register first" when no match) rather
than the auto-create behavior described in socios-backend's own aspirational
design doc. For an internal tool, requiring an account to exist first (via
`/auth/register` or manual provisioning) before Google login works is the
safer default — it means simply having a `@company` Google account is never
sufficient to obtain a `user`-role session, let alone `admin`.

**4. JWT payload gains a `role` claim; `sub`/`email` claims unchanged.**
Endpoints that only need "is this caller authenticated" (the JWT strategy)
keep working unchanged; endpoints needing authorization use `require_role`,
which reads `role` off the decoded token — no DB round-trip per request.
Trade-off: a role change (e.g. promoting a user to `admin`) doesn't take
effect until the token is reissued (re-login) within
`access_token_expire_days`. Acceptable since role assignment is manual and
infrequent.

**5. Public `POST /auth/register`, but the request body cannot set `role`
— it is always forced to `user` server-side.**
Per product decision, registration stays open (no invite-only gate) to match
socios-backend's UX, but nothing in `RegisterRequest` accepts a role field;
the `RegisterStrategy` hardcodes `role="user"`. `admin` is only ever set via
direct DB update, exactly as socios-backend's own plan describes for its
first admin.

**6. Migration is a single additive SQL file, not a phased
create/backfill/drop sequence.**
Socios-backend's design needs multiple migration steps because it's
splitting an existing `socios` table. Here there is no pre-existing
identity table to migrate away from, so `migrations/0002_create_users.sql`
(mirrored into `docker/init-db/`) can create the `users` table and role enum
in one shot with no backfill and no destructive follow-up step.

**7. `SECRET_KEY` has no insecure default; startup fails if it's unset in a
non-local environment.**
Socios-backend's `Settings.secret_key` defaults to the literal string
`"change-me-in-production"`, which is easy to forget to override. This
change instead makes `secret_key` a required setting (only `.env.example`
supplies a placeholder locally) so a misconfigured deploy fails loudly
instead of silently issuing forgeable tokens.

## Risks / Trade-offs

- **[Risk] No Alembic — the `users` migration is a manually-applied SQL
  script** → mitigate by mirroring it into `docker/init-db/*.sql` (so local
  dev and CI stay in sync) and documenting the manual-apply step in
  `tasks.md`/README, consistent with how `migrations/0001_...` is already
  handled in this repo.
- **[Risk] Public self-registration on an internal tool means anyone who
  finds the endpoint can create a `role=user` account** → mitigated by (a)
  role always forced to `user` server-side regardless of request body, and
  (b) this is a deliberate product decision (not a security gap being
  introduced blind) — GET endpoints today are already open with no auth per
  the existing README, so this doesn't newly expose data; it only adds an
  identity layer on top.
- **[Risk] Existing `/costos/*` endpoints stay unauthenticated-by-role after
  this change ships** → explicitly a non-goal here; flagged as an Open
  Question below rather than guessed at.
- **[Trade-off] Role changes require re-login to take effect** (JWT-embedded
  role, ≤ `access_token_expire_days`) → acceptable per Decision 4; document
  for ops so a promoted admin knows to log out/in.
- **[Risk] Google OAuth app must exist (Client ID/Secret, authorized
  redirect URI) before this can be smoke-tested** → tracked as an Open
  Question; not something the code change can resolve.

## Migration Plan

1. Add `migrations/0002_create_users.sql` (users table + role enum) and its
   `docker/init-db/` mirror. Purely additive — no existing table or endpoint
   is touched, so this can ship and be applied to staging/prod independently
   of the code changes below.
2. Add new runtime dependencies (`python-jose[cryptography]`,
   `passlib[bcrypt]`, `bcrypt`; promote `httpx` to `requirements.txt`) and
   new required settings in `app/config.py`.
3. Implement `app/models/user.py`, `app/auth/` (utils, state, passport,
   dependencies, strategies: base/jwt/local/register/google), `app/schemas/auth.py`,
   and the `auth` router (`/auth/register`, `/auth/token`, `/auth/google`,
   `/auth/google/callback`).
4. Implement `GET /profile/me` (`app/routers/profile.py`), registered in
   `app/main.py` without the `/costos` prefix (alongside `cron`).
5. Deploy to staging; smoke-test registration, local login, and Google login
   end-to-end with a real Google OAuth Client configured for this project's
   `BASE_URL`; confirm `require_role` grants/denies correctly for both
   roles (even though no production endpoint uses it yet).
6. Rollback: steps 1–4 are additive and independently revertible (drop the
   new table/routes); there is no destructive step in this migration, unlike
   socios-backend's split-migration plan.

## Open Questions

- Should any existing `/costos/*` mutating endpoints move from
  `require_api_key`-only to also requiring `require_role("admin")` once
  users exist, or is that deferred entirely to a follow-up change? Leaning
  deferred, since guessing which endpoints matters could misclassify
  something staff currently relies on.
- Is a Google OAuth Client (Web application type, with `BASE_URL +
  /auth/google/callback` as an authorized redirect URI) already registered
  for this project, or does one need to be created before staging
  smoke-tests (Migration Plan step 5) can run?
- Who receives the first `role="admin"` at cutover, and via what mechanism
  (direct SQL, matching socios-backend's approach)?
