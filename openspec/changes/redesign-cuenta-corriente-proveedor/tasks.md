## 1. Database schema

- [x] 1.1 Write `migrations/000N_compras_tesoreria_ordenes.sql` creating
      `Compra`, `CompraDetalle`, `CompraImpuesto`, `CompraAdjunto`,
      `Pago`, `PagoMedio`, `PagoAplicacion`, `MovimientoCC`,
      `OrdenCompra`, `OrdenCompraDetalle`, and extending
      `costos_proveedor` with `codigo`, `nombre_fantasia`,
      `condicion_iva`, `condicion_pago`.
- [x] 1.2 Write the generalized trigger (`trg_update_compra_saldo_pendiente`
      on `PagoAplicacion` insert/delete/update), modeled directly on
      `trg_update_importe_pendiente`, maintaining
      `Compra.saldo_pendiente`/`estado`.
- [x] 1.3 Mirror the migration into `docker/init-db/07_*.sql` for local
      dev/tests, per the existing numbered-file convention.
- [x] 1.4 Confirm the migration makes no `DROP`/`ALTER` on
      `costos_cuentacorrienteproveedor*` — legacy tables stay untouched.
- [x] 1.5 Extend the same migration (and its `docker/init-db` mirror) with
      `compras_item_gasto` and `compras_compra_detalle.tipo`/`insumo_id`/
      `item_gasto_id`, added after the rest of this migration had already
      been applied to the local test DB — applied there via a manual
      `CREATE TABLE`/`ALTER TABLE` matching the file (see `CLAUDE.md`).

## 2. Proveedor extension

- [x] 2.1 Extend `app/models/proveedor.py` with `codigo`,
      `nombre_fantasia`, `condicion_iva`, `condicion_pago`.
- [x] 2.2 Extend `app/schemas/proveedor.py` with validation for the
      `condicion_iva`/`condicion_pago` vocabularies.
- [x] 2.3 Update `app/routers/proveedores.py` for the new fields (no
      change needed — the router is already generic over the schema).
- [x] 2.4 Update `tests/unit/test_proveedores*.py`: new-field defaults,
      reject-unknown-`condicion_iva` case.

## 3. Compras capability

- [x] 3.1 `app/models/compra.py`: `Compra`, `CompraDetalle`,
      `CompraImpuesto`, `CompraAdjunto`.
- [x] 3.2 `app/schemas/compra.py`: create/update/read/detail schemas,
      `tipo_comprobante` and `CompraImpuesto.tipo` vocabularies.
- [x] 3.3 `app/services/compra_service.py`: create/update/get/list;
      compute `subtotal`/`iva`/`percepciones`/`impuestos`/`total` from
      `detalle`+`impuestos`; `condicion_pago`-driven `estado`/
      `saldo_pendiente` initialization (`CONTADO` → paid immediately,
      `CUENTA_CORRIENTE` → pending).
- [x] 3.4 `app/routers/compras.py`: `GET/POST /costos/compras`,
      `GET/PUT/PATCH/DELETE /costos/compras/{id}`,
      `POST /costos/compras/{id}/detalle`,
      `POST /costos/compras/{id}/impuestos`.
- [x] 3.5 Test: totals computed correctly from detalle+impuestos rows.
- [x] 3.6 Test: unknown `CompraImpuesto.tipo` rejected with 400.
- [x] 3.7 `app/models/item_gasto.py`/`app/schemas/item_gasto.py`/
      `app/routers/item_gasto.py`: `ItemGasto` catalog CRUD at
      `GET/POST /costos/items-gasto`, `GET/PUT/DELETE
      /costos/items-gasto/{id}` (mirrors the existing `Insumo` catalog
      router).
- [x] 3.8 Extend `CompraDetalle` with `tipo`
      (`INSUMO`/`ITEM_GASTO`/`LIBRE`), `insumo_id`, `item_gasto_id`;
      `CompraDetalleCreate` validates exactly one reference matches
      `tipo`, and `descripcion` is required only when `tipo=LIBRE` (see
      `design.md` D9).
- [x] 3.9 `compra_service.py`: 404 when the referenced `insumo_id`/
      `item_gasto_id` doesn't exist; snapshot the catalog row's `nombre`
      into `descripcion` when the client didn't provide one.
- [x] 3.10 Test: all three `tipo` values (including descripcion snapshot
      and client-provided override), the 404-on-missing-reference case,
      the LIBRE-without-descripcion 400 case, and the
      INSUMO-with-item_gasto_id-set 400 case.

## 4. Adjuntos (object storage)

- [x] 4.1 Add a storage client wrapper for Vercel Blob
      (`app/services/storage_service.py`); document the new required env
      var in `README.md`/`.env.example`.
- [x] 4.2 `POST /costos/compras/{id}/adjuntos`: upload file, store in
      Blob, create `CompraAdjunto` row with the resulting URL; a failed
      upload must not roll back the parent `Compra`.
- [x] 4.3 Include `adjuntos` in the `GET /costos/compras/{id}` response.
- [x] 4.4 Test: a failed upload leaves the `Compra` intact and the
      attachment retryable.

## 5. Tesorería / Pagos capability

- [x] 5.1 `app/models/pago.py`: `Pago`, `PagoMedio`, `PagoAplicacion`.
- [x] 5.2 `app/schemas/pago.py`: validate `medios` sum equals `importe`;
      require `banco`/`numero`/`fecha_acreditacion` when
      `tipo in {CHEQUE, ECHEQ}`.
- [x] 5.3 `app/services/pago_service.py`: create pago + medios; create
      `PagoAplicacion` rows (do not replicate the trigger's
      `saldo_pendiente` arithmetic in application code).
- [x] 5.4 `app/routers/pagos.py`: `GET/POST /costos/pagos`,
      `GET/PUT/PATCH/DELETE /costos/pagos/{id}`,
      `POST /costos/pagos/{id}/aplicaciones`,
      `GET /costos/compras/{id}/pagos`.
- [x] 5.5 Integration test (real DB, not mocked — mirrors the existing
      `test_cuenta_corriente_service.py` trigger-test pattern): insert a
      `PagoAplicacion` row for real, assert the trigger updates
      `Compra.saldo_pendiente`/`estado` on both sides.
- [x] 5.6 Test: mismatched `medios` total rejected with 400.
- [x] 5.7 Test: `CHEQUE` medio missing banking fields rejected with 400.

## 6. Cuenta Corriente ledger + resumen

- [x] 6.1 `app/services/movimiento_cc_service.py`: append `MovimientoCC`
      rows at `Compra`/`Pago` creation time, in the same transaction,
      with `documento` label and `tipo`.
- [x] 6.2 `GET /costos/proveedores/{id}/cuenta-corriente`: windowed
      cumulative `saldo` computed at query time from `MovimientoCC`, with
      `fecha_desde`/`fecha_hasta` filters.
- [x] 6.3 `GET /costos/cuenta-corriente/resumen`: `total_facturas_pendientes`
      (sum of `saldo_pendiente` for `CUENTA_CORRIENTE` compras) +
      `total_gastos`, replacing `ctacteprovresumen`.
- [x] 6.4 Test: creating a `Compra` and applying a `Pago` produces
      matching `MovimientoCC` rows and the correct running `saldo`.
- [x] 6.5 Test: `Compra.saldo_pendiente` (trigger-maintained) and the
      `MovimientoCC`-derived proveedor balance agree at any point in time
      (per `design.md`'s D1 risk mitigation).

## 7. Libro IVA Compras report

- [x] 7.1 `app/services/libro_iva_service.py`: pivot `CompraImpuesto`
      rows (and detalle-level `alicuota_iva`) by `tipo`, grouped per
      `periodo`.
- [x] 7.2 `app/routers/libro_iva.py`: `GET /costos/libro-iva-compras?periodo=...`.
- [x] 7.3 Test: a compra with only a `HISTORICO_SIN_DESGLOSE` impuesto
      row surfaces its amount in a separate `sin_discriminar` column, not
      fabricated into a specific alícuota column.

## 8. Órdenes de Compra

- [x] 8.1 `app/models/orden_compra.py`: `OrdenCompra`,
      `OrdenCompraDetalle`.
- [x] 8.2 `app/schemas/orden_compra.py`.
- [x] 8.3 `app/services/orden_compra_service.py`: create/list/get;
      reception logic (matched by `descripcion`) incrementing
      `cantidad_recibida` and advancing `estado` when a `Compra`
      references `orden_compra_id`.
- [x] 8.4 `app/routers/ordenes_compra.py`: `GET/POST /costos/ordenes-compra`,
      `GET/PUT/PATCH/DELETE /costos/ordenes-compra/{id}`.
- [x] 8.5 Wire `compra_service.py` (3.3) to call the reception logic when
      `orden_compra_id` is set on creation.
- [x] 8.6 Test: partial reception sets `estado=PARCIAL`; full reception
      sets `estado=RECIBIDA`.
- [x] 8.7 (Adicional, post-implementación) Drop `OrdenCompra.numero` —
      the resource is identified by its own `id`, not a client-supplied
      document number. Removed from the ORM model, `OrdenCompraBase`/
      `OrdenCompraRead` schemas, and `orden_compra_service.create_orden_compra`.
      `migrations/0004_drop_orden_compra_numero.sql` +
      `docker/init-db/08_*.sql` mirror drop the column.

## 9. Data migration (legacy → new model)

- [x] 9.1 Write a one-time backfill script
      (`scripts/migrate_ctacteprov_to_compras.py`) reading
      `costos_cuentacorrienteproveedor`,
      `costos_cuentacorrienteproveedorafect`,
      `costos_cuentacorrienteproveedordetalle`.
- [x] 9.2 Map `FACTURA` rows → `Compra` (+ `CompraDetalle` from existing
      detail rows, + one `CompraImpuesto` row per non-zero legacy
      `iva`/`percepcion`, tagged `HISTORICO_SIN_DESGLOSE`).
- [x] 9.3 Map `PAGO` rows + their `Afect` rows → `Pago` + a single
      `PagoMedio` (tipo inferred from legacy `tipo_pago`) +
      `PagoAplicacion`.
- [x] 9.4 Backfill `MovimientoCC` rows for every migrated `Compra`/`Pago`
      so the derived ledger matches history.
- [x] 9.5 Migrate `image`/`image2` base64 blobs to Vercel Blob; create
      `CompraAdjunto` rows referencing the resulting URLs (skippable via
      `--skip-images` for schema/data-only dry runs).
- [x] 9.6 Verification: row-count parity, and spot-check that
      `Compra.saldo_pendiente` matches the legacy `importe_pendiente` it
      was derived from — verified end-to-end against a real local
      Postgres (dry-run and `--apply`), including a real identity-map
      staleness bug the verification step itself caught and that got
      fixed (`populate_existing=True` on the initial legacy-row query).
- [x] 9.7 Script defaults to dry-run; require an explicit `--apply` flag
      to write, consistent with the existing `dry_run` convention on
      generation endpoints.

## 10. Legacy retirement (sequenced cutover)

- [x] 10.1 Confirm `panacea-produccion` is deployed against the new
      endpoints (tracked in that repo) before proceeding. **Confirmed by
      the user (2026-07-07)** — `panacea-produccion` is already on the new
      endpoints.
- [x] 10.2 Remove `/ctacteprov*` routes from
      `app/routers/cuenta_corriente.py`; retire the old service/schema
      code from the write path. Router, service, and schema files deleted
      (`app/routers/cuenta_corriente.py`, `app/services/cuenta_corriente_service.py`,
      `app/schemas/cuenta_corriente.py`); router registration removed from
      `app/main.py`. `app/models/cuenta_corriente.py` kept — it's the
      read-only source model for `scripts/migrate_ctacteprov_to_compras.py`.
- [x] 10.3 Confirm no remaining code path writes to
      `costos_cuentacorrienteproveedor*`/`afect*`/`detalle*`. Verified via
      grep: only remaining reference is the read-only backfill script
      (`scripts/migrate_ctacteprov_to_compras.py`).
- [x] 10.4 Update `README.md`: new endpoints and new object-storage env
      var documented. `/ctacteprov*` is now marked **retired** (was
      "deprecated, pending 10.1").

## 11. Cross-cutting

- [x] 11.1 Update `docker/init-db` and test fixtures/conftest for the new
      tables.
- [x] 11.2 Retire `tests/unit/test_cuenta_corriente_service.py`,
      `test_ctacteprov_api.py`, `test_ctacteprov_detalle_insumos.py` in
      favor of the new per-capability suites added above. Deleted now that
      10.2 has retired the `/ctacteprov*` code path they covered.
- [x] 11.3 Run `openspec validate --strict` on this change and confirm
      it's ready to archive once every task above is checked. `openspec
      validate redesign-cuenta-corriente-proveedor --type change --strict
      --json` passes; `pytest tests/unit -q` → 111 passed (after
      recreating the local test-db container, which had unrelated schema
      drift on `articulos_final` — see `CLAUDE.md`). All 58/58 tasks
      complete — ready for `/opsx:archive` (or `openspec archive`).
