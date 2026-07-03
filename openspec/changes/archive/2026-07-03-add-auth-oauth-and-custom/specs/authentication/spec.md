## ADDED Requirements

### Requirement: Public local registration
The system SHALL expose `POST /auth/register` allowing any caller to create
a `users` account with an email and password. The created account's `role`
SHALL always be `user`, regardless of any role value present in the request
body.

#### Scenario: Successful registration
- **WHEN** a caller submits a valid, unused email and a password meeting the
  minimum length requirement
- **THEN** the system creates a `users` row with a bcrypt-hashed password,
  `role="user"`, `email_verified=false`, and returns a bearer token for the
  new account

#### Scenario: Duplicate email is rejected
- **WHEN** a caller submits an email that already has a `users` row
- **THEN** the system responds with a 409 conflict and does not create a
  second account

#### Scenario: Role field in the request body is ignored
- **WHEN** a registration request body includes a `role` value (e.g.
  `"admin"`)
- **THEN** the created account's role is still `user`

### Requirement: Local email/password login
The system SHALL expose `POST /auth/token` implementing the OAuth2 password
grant, authenticating a caller's email and password against `users` and
issuing a bearer JWT on success.

#### Scenario: Valid credentials
- **WHEN** a caller submits an email and password matching a `users` row's
  `password_hash`
- **THEN** the system returns a JWT bearer token whose payload includes the
  user's `id` (`sub`), `email`, and `role`

#### Scenario: Invalid credentials
- **WHEN** a caller submits a password that does not match the stored hash,
  or an email with no matching `users` row, or an account whose
  `password_hash` is `NULL`
- **THEN** the system responds with 401 unauthorized and does not issue a
  token

### Requirement: Google OAuth2 login
The system SHALL expose `GET /auth/google` (initiate) and
`GET /auth/google/callback` (callback) implementing the OAuth2 Authorization
Code Flow against Google, protected by a signed, time-limited `state` value.
On a successful callback, the system SHALL resolve identity by looking up a
`users` row whose `email` matches the email returned by Google, and SHALL
NOT create a new account automatically.

#### Scenario: Initiating login generates a signed state
- **WHEN** a client calls `GET /auth/google`
- **THEN** the system redirects to Google's authorization endpoint with a
  `state` parameter that is a signed, short-lived token embedding the
  optional `redirect_uri`

#### Scenario: Callback with an existing account
- **WHEN** Google's callback returns a verified email that matches an
  existing `users` row
- **THEN** the system issues a bearer JWT for that user (payload includes
  `id`, `email`, `role`) and either returns it as JSON or redirects to the
  validated `redirect_uri` with the token attached

#### Scenario: Callback with no matching account
- **WHEN** Google's callback returns a verified email with no matching
  `users` row
- **THEN** the system responds with 404 and does not create a `users` row
  for that email

#### Scenario: Invalid or expired state is rejected
- **WHEN** the callback's `state` parameter fails signature verification or
  has expired
- **THEN** the system responds with 400 and does not proceed with token
  exchange

#### Scenario: redirect_uri must be allow-listed
- **WHEN** `GET /auth/google` is called with a `redirect_uri` query
  parameter that is not in the configured allow-list of frontend URLs
- **THEN** the system responds with 400 and does not initiate the OAuth flow

### Requirement: Issued tokens carry a role claim
Every bearer JWT issued by local login, registration, or Google login SHALL
include a `role` claim reflecting the authenticated user's current role at
the time of issuance.

#### Scenario: Role claim reflects the user's stored role
- **WHEN** a user with `role="admin"` logs in via any supported method
- **THEN** the issued JWT's decoded payload includes `role: "admin"`
