## ADDED Requirements

### Requirement: Role-based endpoint authorization
The system SHALL provide a `require_role(*roles)` dependency that, given a
valid bearer JWT, allows the request through only if the token's `role`
claim is one of the specified roles.

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
