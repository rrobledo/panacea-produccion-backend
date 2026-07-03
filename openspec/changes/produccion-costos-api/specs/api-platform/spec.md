## ADDED Requirements

### Requirement: API-key authentication on mutating endpoints
The system SHALL require a valid `X-API-Key` header on every
POST/PUT/PATCH/DELETE request across all capabilities, validated against a
set of keys configured via environment variable, evaluated before any
route handler business logic runs. GET requests SHALL NOT require this
header. Requests missing or presenting an invalid key SHALL receive 401
before any database access occurs.

#### Scenario: Reject write without API key
- **WHEN** a client calls any mutating endpoint (e.g. `POST /productos`)
  without an `X-API-Key` header
- **THEN** the system responds with 401 and performs no database write

#### Scenario: Accept write with valid API key
- **WHEN** a client calls a mutating endpoint with a valid `X-API-Key`
  header
- **THEN** the request proceeds to normal validation and processing

#### Scenario: Reads remain open
- **WHEN** a client calls any GET endpoint without an `X-API-Key` header
- **THEN** the request is processed normally

### Requirement: Distinct cron-secret control on the scheduled cascade
The scheduled monthly cascade endpoint SHALL require a dedicated cron
secret (configured via environment variable, distinct from the general
`X-API-Key` set) and SHALL reject requests presenting only a valid general
API key without the cron secret.

#### Scenario: General API key alone is insufficient
- **WHEN** a request to the scheduled-cascade endpoint presents a valid
  `X-API-Key` but not the cron secret
- **THEN** the system responds with 401/403 and does not run the cascade

### Requirement: Environment-based secret configuration
The system SHALL read the database connection string, API key(s), and cron
secret exclusively from environment variables at process start. No
credential, connection string, or secret value SHALL be committed to
source control anywhere in this repository.

#### Scenario: No committed secrets
- **WHEN** the repository is inspected for committed configuration files
- **THEN** no file contains a literal database password, API key value, or
  cron secret value; an `.env.example` documents required variable names
  only, with placeholder values

### Requirement: CORS allow-listing
The system SHALL restrict Cross-Origin Resource Sharing to an explicit list
of allowed origins configured via environment variable, and SHALL NOT use a
wildcard allow-all-origins configuration.

#### Scenario: Reject an unlisted origin
- **WHEN** a browser request originates from an origin not present in the
  configured allow-list
- **THEN** the response does not include CORS headers permitting that
  origin

### Requirement: Auto-generated OpenAPI documentation
The system SHALL expose interactive API documentation (Swagger UI) at
`/docs` and the raw OpenAPI schema at `/openapi.json`, both automatically
derived from the route and schema definitions with no hand-maintained
documentation file to keep in sync.

#### Scenario: Documentation reflects current routes
- **WHEN** a new endpoint is added to any router with a Pydantic
  request/response schema
- **THEN** `/openapi.json` includes that endpoint without any separate
  documentation-writing step

### Requirement: Vercel deployment and scheduled job configuration
The system SHALL be deployable as a Vercel project serving the FastAPI
application via an ASGI entrypoint, with a Vercel Cron entry configured to
invoke the scheduled-cascade endpoint daily.

#### Scenario: Deployed app serves all routes
- **WHEN** the project is deployed to Vercel
- **THEN** all routers' endpoints are reachable under the deployed base URL
  and `/docs` renders successfully

#### Scenario: Cron entry present in deployment config
- **WHEN** the Vercel project configuration is inspected
- **THEN** it includes a daily cron schedule entry targeting the
  scheduled-cascade endpoint with the cron secret supplied via Vercel's
  environment/cron configuration
