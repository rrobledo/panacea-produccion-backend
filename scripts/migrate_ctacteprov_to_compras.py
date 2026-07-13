"""One-time backfill: costos_cuentacorrienteproveedor* -> the new Compras/
Tesorería model (see openspec/changes/redesign-cuenta-corriente-proveedor/
design.md, Migration Plan step 3).

Usage:
    python -m scripts.migrate_ctacteprov_to_compras            # dry run (default)
    python -m scripts.migrate_ctacteprov_to_compras --apply    # commits for real

Dry-run by default, consistent with this codebase's existing convention for
bulk-mutation endpoints (planning/generate, programacion/generate) — the
whole migration runs inside one transaction that is rolled back unless
--apply is passed, so the printed summary is always exactly what would
happen.

What this script does NOT attempt (see design.md D5 and Non-Goals):
- It does not fabricate a per-alícuota IVA/percepción split for migrated
  rows — the original breakdown was never captured, so both amounts land
  in a single CompraImpuesto row tagged HISTORICO_SIN_DESGLOSE.
- It does not delete or modify the legacy tables — they remain as
  read-only historical archive.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, undefer

from app.config import get_settings
from app.models.compra import Compra, CompraAdjunto, CompraDetalle, CompraImpuesto
from app.models.cuenta_corriente import (
    CuentaCorrienteProveedor,
    CuentaCorrienteProveedorAfect,
)
from app.models.insumos import Insumos
from app.models.item_gasto import ItemGasto  # noqa: F401 -- registers compras_item_gasto so the ORM can resolve CompraDetalle.item_gasto_id's FK on flush
from app.models.pago import Pago, PagoAdjunto, PagoAplicacion, PagoMedio
from app.services import movimiento_cc_service

CONDICION_PAGO_MAP = {"CUENTA_CORRIENTE": "CUENTA_CORRIENTE"}
KNOWN_MEDIO_TIPOS = {"TRANSFERENCIA", "CHEQUE", "ECHEQ", "EFECTIVO", "TARJETA"}


def _condicion_pago_for(tipo_pago: str) -> str:
    return "CUENTA_CORRIENTE" if tipo_pago == "CUENTA_CORRIENTE" else "CONTADO"


def _medio_tipo_for(tipo_pago: str) -> str:
    return tipo_pago if tipo_pago in KNOWN_MEDIO_TIPOS else "TRANSFERENCIA"


async def _load_insumo_nombre_map(session: AsyncSession, insumo_ids: set[int]) -> dict[int, str]:
    if not insumo_ids:
        return {}
    stmt = select(Insumos).where(Insumos.id.in_(insumo_ids))
    rows = (await session.execute(stmt)).scalars().all()
    return {row.id: row.nombre for row in rows}


def _normalized_tipo_movimiento(legacy: CuentaCorrienteProveedor) -> str:
    return (legacy.tipo_movimiento or "").strip().upper()


def _describe_missing_id(legacy_id: int, all_ids_tipo: dict[int, str | None]) -> str:
    if legacy_id not in all_ids_tipo:
        return f"id={legacy_id} no existe en costos_cuentacorrienteproveedor (referencia huérfana)"
    return f"id={legacy_id} existe pero tipo_movimiento={all_ids_tipo[legacy_id]!r} (no FACTURA/PAGO)"


def _decode_legacy_images(legacy: CuentaCorrienteProveedor) -> list[tuple[str, bytes]]:
    """Decode the legacy row's base64 image/image2 columns, skipping either
    one that's empty or not valid base64 rather than failing the whole
    migration over a single corrupt blob.
    """
    decoded = []
    for field_name in ("image", "image2"):
        raw = getattr(legacy, field_name)
        if not raw:
            continue
        try:
            decoded.append((field_name, base64.b64decode(raw)))
        except (binascii.Error, ValueError):
            continue
    return decoded


async def migrate(
    session: AsyncSession, skip_images: bool = False, skip_ids: frozenset[int] = frozenset()
) -> dict:
    stmt = (
        select(CuentaCorrienteProveedor)
        .options(
            selectinload(CuentaCorrienteProveedor.detalle),
            undefer(CuentaCorrienteProveedor.image),
            undefer(CuentaCorrienteProveedor.image2),
            undefer(CuentaCorrienteProveedor.content_type),
        )
        # Without this, a row already present in this session's identity
        # map (e.g. one whose importe_pendiente the legacy trigger just
        # updated via an Afect insert earlier in the same session) would be
        # returned with its stale in-memory value instead of the current
        # DB state — same pitfall as cuenta_corriente_service.get_cuenta_corriente.
        .execution_options(populate_existing=True)
        .order_by(CuentaCorrienteProveedor.id)
    )
    all_legacy_rows = (await session.execute(stmt)).unique().scalars().all()
    # Full id -> tipo_movimiento map over every legacy row, including ones
    # excluded via --skip-ids — used only to explain an unresolved Afect
    # reference (below): whether the referenced id truly doesn't exist in
    # costos_cuentacorrienteproveedor at all (an orphaned/dangling
    # reference) vs. exists with some other tipo_movimiento.
    all_ids_tipo = {r.id: r.tipo_movimiento for r in all_legacy_rows}
    # Rows named in --skip-ids are left out entirely (not migrated at all)
    # rather than migrated-with-a-known-bad-value — for a legacy row whose
    # own importe_pendiente disagrees with its Afect ledger (or whose
    # importe_total itself looks corrupted), fabricating a "corrected"
    # Compra here would be a silent guess about real financial data. These
    # are meant to be reconciled by hand and migrated in a follow-up run.
    legacy_rows = [r for r in all_legacy_rows if r.id not in skip_ids]
    rows_excluded = len(all_legacy_rows) - len(legacy_rows)

    # tipo_movimiento is compared case/whitespace-insensitively so a stray
    # "Factura"/" PAGO " data-entry variant doesn't silently fall through
    # both filters below — rows_tipo_desconocido tracks whatever's left, so
    # a genuinely unrecognized value (not just a formatting quirk) is
    # reported instead of disappearing. A row excluded here gets no
    # Compra/Pago at all, so any CuentaCorrienteProveedorAfect referencing
    # its id as factura_id/pago_id will also fail to link — see
    # aplicaciones_omitidas_referencia_invalida below.
    facturas = [r for r in legacy_rows if _normalized_tipo_movimiento(r) == "FACTURA"]
    pagos = [r for r in legacy_rows if _normalized_tipo_movimiento(r) == "PAGO"]
    rows_tipo_desconocido = [
        (r.id, r.tipo_movimiento) for r in legacy_rows if _normalized_tipo_movimiento(r) not in ("FACTURA", "PAGO")
    ]

    insumo_ids = {d.insumo_id for row in facturas for d in row.detalle}
    insumo_nombres = await _load_insumo_nombre_map(session, insumo_ids)

    compra_id_map: dict[int, int] = {}
    pago_id_map: dict[int, int] = {}
    imagenes_migradas = 0

    for legacy in facturas:
        iva = legacy.iva or 0.0
        percepcion = legacy.percepcion or 0.0
        subtotal = legacy.importe_total - iva - percepcion
        condicion_pago = _condicion_pago_for(legacy.tipo_pago)

        compra = Compra(
            proveedor_id=legacy.proveedor_id,
            tipo_comprobante="GASTO",  # legacy never recorded a comprobante type — see module docstring
            numero=legacy.numero,
            fecha=legacy.fecha_emision,
            fecha_vencimiento=legacy.fecha_vencimiento,
            condicion_pago=condicion_pago,
            observaciones=(
                f"[migrado de costos_cuentacorrienteproveedor#{legacy.id}] "
                f"categoria={legacy.categoria} caja={legacy.caja} "
                f"tipo_pago_original={legacy.tipo_pago}"
                + (f" | {legacy.observaciones}" if legacy.observaciones else "")
            ),
            subtotal=subtotal,
            iva=0.0,
            percepciones=0.0,
            impuestos=iva + percepcion,
            total=legacy.importe_total,
        )
        if condicion_pago == "CONTADO":
            compra.saldo_pendiente = 0.0
            compra.estado = "PAGADO"
        else:
            compra.saldo_pendiente = compra.total
            compra.estado = "PENDIENTE"

        session.add(compra)
        await session.flush()
        compra_id_map[legacy.id] = compra.id

        if legacy.detalle:
            for item in legacy.detalle:
                nombre = insumo_nombres.get(item.insumo_id, f"Insumo #{item.insumo_id}")
                session.add(
                    CompraDetalle(
                        compra_id=compra.id,
                        descripcion=nombre,
                        cantidad=item.cantidad,
                        precio_unitario=(item.subtotal / item.cantidad) if item.cantidad else item.subtotal,
                        importe_neto=item.subtotal,
                        importe_total=item.subtotal,
                    )
                )
        else:
            session.add(
                CompraDetalle(
                    compra_id=compra.id,
                    descripcion=f"[migrado] {legacy.categoria}",
                    cantidad=1,
                    precio_unitario=subtotal,
                    importe_neto=subtotal,
                    importe_total=subtotal,
                )
            )

        if iva + percepcion > 0:
            session.add(
                CompraImpuesto(
                    compra_id=compra.id,
                    tipo="HISTORICO_SIN_DESGLOSE",
                    base_imponible=subtotal,
                    importe=iva + percepcion,
                )
            )

        await movimiento_cc_service.append_compra_movimiento(session, compra)

        if not skip_images:
            for field_name, content in _decode_legacy_images(legacy):
                session.add(
                    CompraAdjunto(
                        compra_id=compra.id,
                        nombre=f"ctacteprov-{legacy.id}-{field_name}",
                        contenido=content,
                        tipo=legacy.content_type,
                    )
                )
                imagenes_migradas += 1

    for legacy in pagos:
        medio_tipo = _medio_tipo_for(legacy.tipo_pago)
        pago = Pago(
            proveedor_id=legacy.proveedor_id,
            fecha=legacy.fecha_emision,
            importe=legacy.importe_total,
            estado="REGISTRADO",
            observaciones=(
                f"[migrado de costos_cuentacorrienteproveedor#{legacy.id}] "
                f"tipo_pago_original={legacy.tipo_pago}"
                + (f" | {legacy.observaciones}" if legacy.observaciones else "")
            ),
        )
        session.add(pago)
        await session.flush()
        pago_id_map[legacy.id] = pago.id

        session.add(PagoMedio(pago_id=pago.id, tipo=medio_tipo, importe=legacy.importe_total))
        await movimiento_cc_service.append_pago_movimiento(session, pago)

        if not skip_images:
            for field_name, content in _decode_legacy_images(legacy):
                session.add(
                    PagoAdjunto(
                        pago_id=pago.id,
                        nombre=f"ctacteprov-{legacy.id}-{field_name}",
                        contenido=content,
                        tipo=legacy.content_type,
                    )
                )
                imagenes_migradas += 1

    afect_stmt = select(CuentaCorrienteProveedorAfect).order_by(CuentaCorrienteProveedorAfect.id)
    afect_rows = (await session.execute(afect_stmt)).scalars().all()
    aplicaciones_created = 0
    aplicaciones_skipped_excluded = 0
    # Previously, an Afect row whose factura_id/pago_id didn't resolve for
    # any reason OTHER than --skip-ids was silently dropped — no counter,
    # no log line — which is exactly what produced unexplained
    # saldo_pendiente mismatches (a real payment existed in the legacy
    # Afect ledger but its PagoAplicacion link never got created because
    # one side pointed at a row this migration didn't recognize, e.g. a
    # tipo_movimiento typo). Every such row is now recorded here instead.
    aplicaciones_omitidas_referencia_invalida = []
    for afect in afect_rows:
        compra_id = compra_id_map.get(afect.factura_id)
        pago_id = pago_id_map.get(afect.pago_id)
        if compra_id is None or pago_id is None:
            # Either side references a row left out via skip_ids — the
            # other side (if migrated) still gets its Compra/Pago row, just
            # without this PagoAplicacion link; reconcile by hand once the
            # excluded row is fixed and migrated in a follow-up run.
            if afect.factura_id in skip_ids or afect.pago_id in skip_ids:
                aplicaciones_skipped_excluded += 1
            else:
                aplicaciones_omitidas_referencia_invalida.append(
                    {
                        "afect_id": afect.id,
                        "factura_id": afect.factura_id,
                        "pago_id": afect.pago_id,
                        "importe": afect.importe,
                        "factura_no_encontrada": compra_id is None,
                        "pago_no_encontrado": pago_id is None,
                        "factura_diagnostico": _describe_missing_id(afect.factura_id, all_ids_tipo)
                        if compra_id is None
                        else None,
                        "pago_diagnostico": _describe_missing_id(afect.pago_id, all_ids_tipo)
                        if pago_id is None
                        else None,
                    }
                )
            continue
        # Each insert fires trg_update_compra_saldo_pendiente, replaying the
        # legacy trigger's effect against the new Compra rows — see
        # design.md D1/D2. Do not compute saldo_pendiente by hand here.
        session.add(PagoAplicacion(pago_id=pago_id, compra_id=compra_id, importe=afect.importe))
        aplicaciones_created += 1

    await session.flush()

    # Verification (design.md Migration Plan step 4): row-count parity +
    # saldo_pendiente spot-check against the legacy importe_pendiente each
    # migrated Compra was derived from.
    mismatches = []
    for legacy in facturas:
        if legacy.tipo_pago != "CUENTA_CORRIENTE":
            continue
        compra = await session.get(Compra, compra_id_map[legacy.id])
        await session.refresh(compra)
        legacy_pendiente = legacy.importe_pendiente or 0.0
        if abs(compra.saldo_pendiente - legacy_pendiente) > 0.01:
            # Cross-reference: an unresolved Afect against this same
            # factura_id is almost always the actual cause (see comment
            # above aplicaciones_omitidas_referencia_invalida) — surfacing
            # it right next to the mismatch turns "obtenido doesn't match
            # esperado" into an actionable "this specific payment link
            # didn't migrate, here's why".
            afects_relacionados = [
                a for a in aplicaciones_omitidas_referencia_invalida if a["factura_id"] == legacy.id
            ]
            mismatches.append((legacy.id, legacy_pendiente, compra.saldo_pendiente, afects_relacionados))

    return {
        "facturas_migradas": len(facturas),
        "pagos_migrados": len(pagos),
        "aplicaciones_creadas": aplicaciones_created,
        "aplicaciones_omitidas_por_exclusion": aplicaciones_skipped_excluded,
        "aplicaciones_omitidas_referencia_invalida": aplicaciones_omitidas_referencia_invalida,
        "filas_excluidas_por_skip_ids": rows_excluded,
        "filas_tipo_movimiento_desconocido": rows_tipo_desconocido,
        "saldo_mismatches": mismatches,
        "imagenes_migradas": imagenes_migradas,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the migration (default: dry run)")
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip decoding/embedding legacy image/image2 blobs (schema/data migration only, faster)",
    )
    parser.add_argument(
        "--skip-ids",
        default="",
        help=(
            "Comma-separated costos_cuentacorrienteproveedor ids to leave out of this run entirely "
            "(e.g. rows with a known-bad importe_total or a saldo_pendiente that disagrees with their "
            "Afect ledger) — reconcile and migrate them by hand in a follow-up run."
        ),
    )
    args = parser.parse_args()
    skip_ids = frozenset(int(v) for v in args.skip_ids.split(",") if v.strip())

    settings = get_settings()
    database_url = settings.sqlalchemy_database_url
    connect_args = {} if "localhost" in database_url or "127.0.0.1" in database_url else {"ssl": "require"}
    engine = create_async_engine(database_url, connect_args=connect_args)

    async with engine.begin() as conn:
        session = AsyncSession(bind=conn)
        summary = await migrate(session, skip_images=args.skip_images, skip_ids=skip_ids)

        print("Migration summary:")
        print(f"  filas excluidas (--skip-ids): {summary['filas_excluidas_por_skip_ids']}")
        print(f"  facturas migradas:        {summary['facturas_migradas']}")
        print(f"  pagos migrados:           {summary['pagos_migrados']}")
        print(f"  aplicaciones creadas:     {summary['aplicaciones_creadas']}")
        print(f"  aplicaciones omitidas (referencian id excluido): {summary['aplicaciones_omitidas_por_exclusion']}")
        print(
            "  aplicaciones omitidas (referencia inválida, no excluida): "
            f"{len(summary['aplicaciones_omitidas_referencia_invalida'])}"
        )
        print(f"  imagenes migradas:        {summary['imagenes_migradas']}")
        print(f"  saldo mismatches:         {len(summary['saldo_mismatches'])}")

        if summary["filas_tipo_movimiento_desconocido"]:
            print(
                "  WARNING: filas con tipo_movimiento fuera de {FACTURA, PAGO} "
                "(excluidas por completo, ni Compra ni Pago creado):"
            )
            for legacy_id, tipo_movimiento in summary["filas_tipo_movimiento_desconocido"]:
                print(f"    - legacy#{legacy_id}: tipo_movimiento={tipo_movimiento!r}")

        if summary["aplicaciones_omitidas_referencia_invalida"]:
            print(
                "  WARNING: aplicaciones (Afect) cuyo factura_id o pago_id no se "
                "encontró entre las filas migradas — no son PagoAplicacion en el "
                "modelo nuevo, y son la causa más probable de los saldo mismatches "
                "de abajo:"
            )
            for a in summary["aplicaciones_omitidas_referencia_invalida"]:
                detalles = [d for d in (a["factura_diagnostico"], a["pago_diagnostico"]) if d]
                print(f"    - afect#{a['afect_id']}: importe={a['importe']}")
                for detalle in detalles:
                    print(f"        -> {detalle}")

        for legacy_id, expected, actual, afects_relacionados in summary["saldo_mismatches"]:
            print(f"    - factura legacy#{legacy_id}: esperado={expected} obtenido={actual}")
            if afects_relacionados:
                total_no_aplicado = sum(a["importe"] for a in afects_relacionados)
                print(
                    f"        -> {len(afects_relacionados)} aplicacion(es) no migrada(s) "
                    f"por referencia inválida, importe total={total_no_aplicado} "
                    "(ver WARNING arriba)"
                )
                continue
            ratio = (actual / expected) if expected else None
            if ratio and abs(round(ratio) - ratio) < 1e-6 and abs(round(ratio)) in (1000, 10000, 100000, 1000000):
                print(
                    f"        -> obtenido es ~{round(ratio):,}x esperado: probable error de punto "
                    "decimal en el dato legacy (importe_total vs importe_pendiente ya "
                    "no coinciden en la fuente) — no es un bug de este script, "
                    "reconciliar a mano y usar --skip-ids"
                )
            else:
                print(
                    "        -> sin aplicaciones Afect asociadas a esta factura ni error de "
                    "punto decimal evidente: el importe_pendiente legacy probablemente fue "
                    "editado a mano (o corregido por otra vía) sin pasar por el ledger Afect "
                    "— reconciliar a mano o usar --skip-ids"
                )

        if args.apply and not summary["saldo_mismatches"]:
            await session.commit()
            print("Applied.")
        elif args.apply:
            await session.rollback()
            print("NOT applied — saldo mismatches found, fix and re-run before --apply.")
        else:
            await session.rollback()
            print("Dry run — no changes committed. Re-run with --apply to commit.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
