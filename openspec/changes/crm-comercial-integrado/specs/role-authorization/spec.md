## MODIFIED Requirements

### Requirement: Role-based endpoint authorization
The system SHALL provide a `require_role(*roles)` dependency that, given a
valid bearer JWT, allows the request through only if the token's `role`
claim is one of the specified roles. This dependency is role-set agnostic:
it works unchanged for any value present in the `user_role` enum,
including the commercial roles added for the CRM module (`gerencia`,
`marketing`, `supervisor_comercial`, `vendedor`), without requiring any
code change to `require_role` itself.

#### Scenario: Matching role is allowed
- **WHEN** a request carries a valid JWT with `role="admin"` and hits an
  endpoint guarded by `require_role("admin")`
- **THEN** the request proceeds to the endpoint handler

#### Scenario: Non-matching role is forbidden
- **WHEN** a request carries a valid JWT with `role="user"` and hits an
  endpoint guarded by `require_role("admin")`
- **THEN** the system responds with 403 forbidden

#### Scenario: Missing or invalid token is unauthorized
- **WHEN** a request has no bearer token, or an expired/invalid one, and
  hits an endpoint guarded by `require_role(...)`
- **THEN** the system responds with 401 unauthorized

#### Scenario: require_role accepts multiple roles
- **WHEN** an endpoint is guarded by `require_role("admin", "user")`
- **THEN** a valid JWT with either role is allowed through

Note: the CRM routers (`app/routers/crm_*.py`) do **not** use `require_role`
— see the `require_authenticated` requirement below. `require_role` remains
available as generic infrastructure for any endpoint that does need
role-scoped access, CRM or otherwise.

### Requirement: Authentication-only endpoint access (no role check)
The system SHALL provide a `require_authenticated()` dependency that accepts
any request carrying a valid bearer JWT, regardless of the token's `role`
claim. All `/crm/*` endpoints use this dependency instead of `require_role`
— CRM access originally required one of the commercial roles (`admin`,
`gerencia`, `marketing`, `supervisor_comercial`, `vendedor`); that
role restriction was explicitly removed per a follow-up request, while
still requiring a valid logged-in session.

#### Scenario: Any authenticated role reaches a CRM endpoint
- **WHEN** a request carries a valid JWT with `role="user"` (not one of the
  former commercial roles) and hits a CRM endpoint guarded by
  `require_authenticated()`
- **THEN** the request proceeds to the endpoint handler

#### Scenario: Missing or invalid token is still unauthorized
- **WHEN** a request has no bearer token, or an expired/invalid one, and
  hits a CRM endpoint guarded by `require_authenticated()`
- **THEN** the system responds with 401 unauthorized
