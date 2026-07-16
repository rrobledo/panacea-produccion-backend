## ADDED Requirements

### Requirement: Explicit remito estado transitions
The system SHALL provide `PATCH /costos/remitos/{id}/estado`, accepting a
target estado (`nuevo_estado`) and advancing the remito to that estado only
if it is the single valid next step in the sequence `PENDIENTE →
EN_PREPARACION → PREPARADO → EN CAMINO → ENTREGADO`, by setting the
corresponding timestamp field (`fecha_preparacion`, `fecha_listo`,
`fecha_despacho`, `fecha_recibido` respectively) to the current time. The
endpoint SHALL require the same API-key authentication
(`require_api_key`) already required by other write endpoints in this repo,
and SHALL return the updated remito representation on success.

#### Scenario: Valid single-step transition
- **WHEN** a remito is in estado `PENDIENTE` and a caller sends `PATCH
  .../estado` with `{"nuevo_estado": "EN_PREPARACION"}` and a valid API key
- **THEN** the remito's `fecha_preparacion` is set to the current time, its
  estado becomes `EN_PREPARACION`, and the response is 200 with the updated
  remito

#### Scenario: Skipped transition is rejected
- **WHEN** a remito is in estado `PENDIENTE` and a caller requests a
  transition to `PREPARADO` (skipping `EN_PREPARACION`)
- **THEN** the response is 422 and the remito's estado is unchanged

#### Scenario: Backward transition is rejected
- **WHEN** a remito is in estado `EN_PREPARACION` and a caller requests a
  transition back to `PENDIENTE`
- **THEN** the response is 422 and the remito's estado is unchanged

#### Scenario: Transition without a valid API key is rejected
- **WHEN** a caller sends `PATCH .../estado` without a valid `X-API-Key`
- **THEN** the response is 401 and the remito's estado is unchanged

### Requirement: Editing a remito is restricted to estado PENDIENTE
The system SHALL reject `PUT /costos/remitos/{id}` with 422 when the target
remito's estado is not `PENDIENTE`, leaving the remito unmodified. When the
remito's estado is `PENDIENTE`, the endpoint SHALL behave as before this
change (full field replace, including replacing detalle lines).

#### Scenario: Editing a PENDIENTE remito succeeds
- **WHEN** a remito is in estado `PENDIENTE` and a caller sends a valid
  `PUT` payload with a valid API key
- **THEN** the remito is updated and the response is 200

#### Scenario: Editing a non-PENDIENTE remito is rejected
- **WHEN** a remito's estado is `EN_PREPARACION` or later and a caller sends
  `PUT /costos/remitos/{id}`
- **THEN** the response is 422 and none of the remito's fields change

### Requirement: Deleting a remito is restricted to estado PENDIENTE
The system SHALL reject `DELETE /costos/remitos/{id}` with 422 when the
target remito's estado is not `PENDIENTE`, leaving the remito (and its
detalle rows) intact.

#### Scenario: Deleting a PENDIENTE remito succeeds
- **WHEN** a remito is in estado `PENDIENTE` and a caller sends `DELETE`
  with a valid API key
- **THEN** the remito and its detalle rows are deleted and the response is
  204

#### Scenario: Deleting a non-PENDIENTE remito is rejected
- **WHEN** a remito's estado is `EN_PREPARACION` or later and a caller sends
  `DELETE /costos/remitos/{id}`
- **THEN** the response is 422 and the remito still exists afterward
