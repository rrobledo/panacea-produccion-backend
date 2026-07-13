# scripts/

One-off operational scripts. Each one is run manually (`python -m
scripts.<name>`), not part of the request-serving app.

## `migrate_ctacteprov_to_compras.py`

One-time backfill from the legacy flat model
(`costos_cuentacorrienteproveedor` / `*afect` / `*detalle`) into the
normalized Compras/Tesorería model (`Compra` / `CompraDetalle` /
`CompraImpuesto` / `CompraAdjunto`, `Pago` / `PagoMedio` /
`PagoAplicacion` / `PagoAdjunto`, `MovimientoCC`). Background:
`openspec/changes/redesign-cuenta-corriente-proveedor/design.md`
("Migration Plan").

Legacy tables are never modified or dropped by this script — they stay in
place as read-only historical archive after migrating.

**Not idempotent.** The script has no notion of "already migrated" — it
reads every legacy row not excluded via `--skip-ids` and creates new-model
rows for it, every time it's run with `--apply`. Running `--apply` twice
against the same database duplicates every `Compra`/`Pago`. Run it exactly
once per target database; if you need a second pass (e.g. to pick up rows
you excluded the first time), pass `--skip-ids` for everything already
migrated.

### 1. Configure the database target

The script reads the same `DATABASE_URL` the app itself uses
(`app.config.get_settings().sqlalchemy_database_url`), via a `.env` file
in the repo root or an exported environment variable — whichever
`pydantic-settings` picks up. There is no separate flag for this; pointing
the script at a database is entirely a matter of what `DATABASE_URL`
resolves to when you run it.

Accepts `postgres://` or `postgresql://` and rewrites it to the
`asyncpg` driver URL internally. SSL is added automatically
(`connect_args={"ssl": "require"}`) unless the host is `localhost` or
`127.0.0.1`.

**Local Docker Postgres** (safe default for a first run/dry run):

```bash
docker compose up -d   # starts Postgres on localhost:55432 if not already running
export DATABASE_URL="postgres://panacea:panacea@localhost:55432/panacea_test"
```

**A real target (staging/production)**: set `DATABASE_URL` in `.env` (copy
from `.env.example` if you don't have one) to that database's pooled
connection string, or export it directly in your shell for a one-off run:

```bash
export DATABASE_URL="postgres://<user>:<password>@<host>/<db>?ssl=require"
```

Double-check `echo "$DATABASE_URL"` (or your `.env`) before running
`--apply` — this script writes real rows, and there's no `--dry-run`
confirmation prompt beyond the summary it prints.

### 2. (Optional) skip attachment migration

Legacy `FACTURA` and `PAGO` rows with an `image`/`image2` base64 blob get
that blob decoded and stored directly in Postgres — a `CompraAdjunto` row
for `FACTURA`, a `PagoAdjunto` row for `PAGO` (both store the binary
`contenido` in the database itself, no external object storage involved).

Pass `--skip-images` for a faster schema/data-only run (e.g. while
iterating on `--skip-ids`) — image decoding/embedding is skipped and the
run only creates `Compra`/`Pago`/`MovimientoCC`/etc rows.

### 3. Run it — dry run first

```bash
source .venv/bin/activate
python -m scripts.migrate_ctacteprov_to_compras            # dry run (default), nothing committed
python -m scripts.migrate_ctacteprov_to_compras --skip-images
```

Dry run and `--apply` execute the exact same code path inside one
transaction — dry run just rolls that transaction back at the end, so the
printed summary is always exactly what `--apply` would do. Review it:

```
Migration summary:
  filas excluidas (--skip-ids): 0
  facturas migradas:        42
  pagos migrados:           17
  aplicaciones creadas:     31
  aplicaciones omitidas (referencian id excluido): 0
  aplicaciones omitidas (referencia inválida, no excluida): 0
  imagenes migradas:        12
  saldo mismatches:         0
  ...
```

### 4. Resolve `saldo mismatches`, if any

For every `CUENTA_CORRIENTE` `FACTURA` row, the script checks the
migrated `Compra.saldo_pendiente` against the legacy row's
`importe_pendiente`. A mismatch means either:

1. A real payment application in the legacy `Afect` ledger didn't migrate
   into a `PagoAplicacion` because one side (`factura_id`/`pago_id`)
   didn't resolve to a row this run actually migrated — most commonly a
   `tipo_movimiento` value outside `{FACTURA, PAGO}` (comparison is
   case/whitespace-insensitive, but a genuinely different value, e.g.
   `NOTA_CREDITO`, is excluded entirely, on purpose — this script only
   migrates facturas and pagos). When this is the cause, the summary
   prints two things right above the mismatch list: a `WARNING: filas con
   tipo_movimiento fuera de {FACTURA, PAGO}` block naming the excluded
   row(s), and a `WARNING: aplicaciones (Afect) cuyo factura_id o pago_id
   no se encontró` block naming the specific `Afect` row(s) that couldn't
   link — each mismatch line is also annotated with how many such
   applications relate to it and their combined `importe`, so you don't
   have to cross-reference by hand.
2. The legacy row's own numbers disagree with its `Afect` ledger (or its
   `importe_total` looks corrupted independently of any `Afect` row) — a
   genuine legacy data-quality issue, not something this script caused or
   can safely infer a fix for. If `obtenido` is suspiciously close to
   `esperado × 10ⁿ` (e.g. a decimal point that landed in the wrong place
   when the legacy row was first entered), the mismatch line is annotated
   with a note to that effect.

Either way, the script refuses to silently guess a "corrected" value.

If the summary lists mismatches, `--apply` **will not commit** even
though you passed it — it rolls back and prints `NOT applied`. Options:

- For cause 1: either fix the legacy row's `tipo_movimiento` by hand and
  re-run, or accept that comprobante/pago was never meant to link here.
- For cause 2, or once cause 1 is ruled out: fix the underlying legacy
  data by hand, then re-run.
- Exclude the offending legacy ids for now and migrate them in a later,
  separate run: `--skip-ids 12,45` (comma-separated
  `costos_cuentacorrienteproveedor.id` values). Excluded rows are left out
  entirely — not migrated with a known-bad value — and any `Afect` link
  referencing one of them is skipped too (reported as `aplicaciones
  omitidas (referencian id excluido)`), not silently dropped.

### 5. Apply for real

Once the dry-run summary shows `saldo mismatches: 0` (after fixing or
`--skip-ids`-ing the rest):

```bash
python -m scripts.migrate_ctacteprov_to_compras --apply
# or, skipping image upload:
python -m scripts.migrate_ctacteprov_to_compras --apply --skip-images
```

Output ends with `Applied.` on success. If mismatches reappear (e.g. the
target database changed between your dry run and this call), it prints
`NOT applied — saldo mismatches found, fix and re-run before --apply.`
and nothing is committed — safe to just re-run once fixed.

### What this script deliberately does not do

- Does not fabricate a per-alícuota IVA/percepción breakdown for migrated
  rows — the original split was never captured, so both land in a single
  `CompraImpuesto` row tagged `HISTORICO_SIN_DESGLOSE`.
- Does not delete, alter, or otherwise touch the legacy tables.

### Flags reference

| Flag | Effect |
|---|---|
| `--apply` | Commit the migration. Default is dry run (always rolled back). |
| `--skip-images` | Don't decode/embed legacy `image`/`image2` blobs into `CompraAdjunto`/`PagoAdjunto`. Schema/data migration only. |
| `--skip-ids ID,ID,...` | `costos_cuentacorrienteproveedor.id` values to leave out of this run entirely. |
