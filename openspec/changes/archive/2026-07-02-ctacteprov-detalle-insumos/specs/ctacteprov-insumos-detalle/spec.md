## ADDED Requirements

### Requirement: Insumo detail lines nested under a cuenta corriente entry
The system SHALL provide `GET /ctacteprov/{id}/insumos` and
`POST /ctacteprov/{id}/insumos` for `CuentaCorrienteProveedorDetalle` rows
(`insumo` FK, `cantidad`, `subtotal`), each linked to exactly one
`CuentaCorrienteProveedor` entry (1-to-many: one entry has many detail rows).
`GET` SHALL list all detail rows for that entry, ordered by `id`. `POST`
SHALL accept either a single object or an array of objects and create one
detail row per object, all linked to `{id}`.

#### Scenario: List detail rows for an entry
- **WHEN** a client calls `GET /ctacteprov/10/insumos`
- **THEN** the response includes every `costos_cuentacorrienteproveedordetalle`
  row linked to entry 10, each with `id`, `insumo`, `cantidad`, `subtotal`

#### Scenario: Append a detail row to an existing entry
- **WHEN** a client calls `POST /ctacteprov/10/insumos` with
  `{insumo: 5, cantidad: 3, subtotal: 150}`
- **THEN** the system creates a new detail row linked to entry 10 and
  returns it with a generated `id`

#### Scenario: Append multiple detail rows in one call
- **WHEN** a client calls `POST /ctacteprov/10/insumos` with an array of two
  `{insumo, cantidad, subtotal}` objects
- **THEN** the system creates both detail rows, each linked to entry 10

#### Scenario: Reject a detail row referencing an unknown entry
- **WHEN** a client calls `POST /ctacteprov/{id}/insumos` with an `{id}` that
  does not match any existing `CuentaCorrienteProveedor` entry
- **THEN** the system responds with 404 and creates no detail row

### Requirement: Remove a single insumo detail line
The system SHALL provide `DELETE /ctacteprov/{id}/insumos/{detalle_id}` to
remove one detail row without affecting the parent entry or its other detail
rows.

#### Scenario: Delete one detail row
- **WHEN** a client calls `DELETE /ctacteprov/10/insumos/42`
- **THEN** the system removes detail row 42 and leaves entry 10 and its other
  detail rows unchanged

#### Scenario: Delete a detail row that does not belong to the given entry
- **WHEN** a client calls `DELETE /ctacteprov/10/insumos/42` but detail row 42
  is linked to a different entry
- **THEN** the system responds with 404 and does not delete the row

### Requirement: Deleting a cuenta corriente entry removes its detail rows
The system SHALL delete all `CuentaCorrienteProveedorDetalle` rows linked to
a `CuentaCorrienteProveedor` entry when that entry is deleted (`ON DELETE
CASCADE`), so no orphaned detail rows remain.

#### Scenario: Delete an entry with detail rows
- **WHEN** a client calls `DELETE /ctacteprov/10` and entry 10 has 3 detail
  rows
- **THEN** the system deletes entry 10 and all 3 linked detail rows
