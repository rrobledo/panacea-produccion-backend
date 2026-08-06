## MODIFIED Requirements

### Requirement: Users table as source of identity
The system SHALL persist a `users` table that is the single source of truth
for login credentials, email, role, and verification status, independent of
any other domain table in the service.

Each `users` row SHALL have: a unique `id`; a unique, indexed `email`; a
nullable `password_hash` (null when the account has never set a local
password); a `role` constrained to a fixed enum (`admin`, `user`, `gerencia`,
`marketing`, `supervisor_comercial`, `vendedor`), defaulting to `user`; a
boolean `email_verified`, defaulting to `false`; and `created_at`/`updated_at`
timestamps. The commercial roles (`gerencia`, `marketing`,
`supervisor_comercial`, `vendedor`) exist to gate CRM endpoints and carry no
special meaning outside the CRM module.

#### Scenario: Email uniqueness is enforced
- **WHEN** an attempt is made to insert a second `users` row with an email
  that already exists (case-insensitive match)
- **THEN** the database rejects the insert with a uniqueness violation

#### Scenario: Role defaults to the lowest-privilege value
- **WHEN** a `users` row is created without an explicit role
- **THEN** its `role` is `user`

#### Scenario: Social-only accounts have no password hash
- **WHEN** a `users` row is created for an account that has never registered
  a local password
- **THEN** its `password_hash` is `NULL` and local login (email/password)
  for that account is rejected

#### Scenario: A commercial role can be assigned
- **WHEN** a `users` row is created or updated with `role="vendedor"` (or
  any of `gerencia`, `marketing`, `supervisor_comercial`)
- **THEN** the row is persisted with that role, and it is accepted
  wherever the existing `admin`/`user` roles were already accepted

### Requirement: Users table is provisioned via an additive migration
The system SHALL create the `users` table and its `role` enum via a
standalone, additive SQL migration file that does not alter or depend on any
existing table. The commercial roles added for the CRM module SHALL be
introduced via a separate, standalone additive migration
(`ALTER TYPE user_role ADD VALUE ...`) that only adds enum values and does
not read or depend on them within the same transaction.

#### Scenario: Migration applies cleanly to an existing database
- **WHEN** the new migration is applied to a database that already contains
  the service's existing costing/production tables
- **THEN** the `users` table and `role` enum are created with no changes to
  any existing table, and no existing endpoint's behavior changes

#### Scenario: Commercial-roles migration is additive and isolated
- **WHEN** the commercial-roles migration is applied to a database that
  already has the `users` table and existing `user_role` values in use
- **THEN** the new enum values are added, no existing `users` row or role
  value changes, and no existing endpoint's behavior changes
