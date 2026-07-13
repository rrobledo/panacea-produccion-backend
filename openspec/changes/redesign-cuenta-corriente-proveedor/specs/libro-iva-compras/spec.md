## ADDED Requirements

### Requirement: Libro IVA Compras report
The system SHALL provide `GET /costos/libro-iva-compras` accepting a
`periodo` (year-month) parameter and returning one row per `Compra` in
that período with `neto`, `iva_21`, `iva_10_5`, `iva_27`, `exento`,
`no_gravado`, `percepcion_iva`, `percepcion_iibb` — each derived by
pivoting that compra's `CompraImpuesto` rows by `tipo`. The report SHALL
be computed from `Compra`/`CompraImpuesto` at query time and SHALL NOT
require a separate materialized table for correctness (materialization
MAY be added later purely as a performance optimization).

#### Scenario: Fetch the report for a período
- **WHEN** a client calls `GET /costos/libro-iva-compras?periodo=2026-07`
- **THEN** the response includes one row per `Compra` with `fecha` in
  July 2026, with each tax column populated from that compra's
  `CompraImpuesto` rows of the matching `tipo`

#### Scenario: Historical compras report as undiscriminated
- **WHEN** a `Compra` migrated from the legacy schema only has a
  `CompraImpuesto` row with `tipo=HISTORICO_SIN_DESGLOSE`
- **THEN** its report row SHALL NOT populate any of the discriminated
  `iva_21`/`iva_10_5`/`iva_27`/percepción columns with a fabricated
  split; the undiscriminated amount SHALL be surfaced separately (e.g. a
  `sin_discriminar` column) rather than guessed into a specific alícuota
