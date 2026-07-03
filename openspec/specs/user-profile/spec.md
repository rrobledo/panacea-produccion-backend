# user-profile Specification

## Purpose
TBD - defines the authenticated user's own-profile endpoint.

## Requirements

### Requirement: Current user profile endpoint
The system SHALL expose `GET /profile/me`, protected by the JWT bearer
strategy, returning the authenticated caller's own identity: `id`, `email`,
`role`, and `email_verified`. The response SHALL NOT include
`password_hash`.

#### Scenario: Authenticated caller retrieves their own profile
- **WHEN** a request with a valid bearer JWT calls `GET /profile/me`
- **THEN** the system returns 200 with the caller's `id`, `email`, `role`,
  and `email_verified`, sourced from the `users` row identified by the
  token's `sub` claim

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request with no bearer token, or an expired/invalid one, calls
  `GET /profile/me`
- **THEN** the system responds with 401 unauthorized

#### Scenario: Response excludes the password hash
- **WHEN** `GET /profile/me` returns a successful response
- **THEN** the response body contains no `password_hash` field
