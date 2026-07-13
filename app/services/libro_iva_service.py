from fastapi import HTTPException, status
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.compra import Compra

IMPUESTO_COLUMN_MAP = {
    "IVA_21": "iva_21",
    "IVA_10_5": "iva_10_5",
    "IVA_27": "iva_27",
    "PERCEPCION_IVA": "percepcion_iva",
    "PERCEPCION_IIBB": "percepcion_iibb",
}


def _parse_periodo(periodo: str) -> tuple[int, int]:
    try:
        year_str, month_str = periodo.split("-")
        year, month = int(year_str), int(month_str)
        if not 1 <= month <= 12:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="periodo must be YYYY-MM") from exc
    return year, month


async def get_libro_iva_compras(session: AsyncSession, periodo: str) -> list[dict]:
    year, month = _parse_periodo(periodo)
    stmt = (
        select(Compra)
        .options(selectinload(Compra.detalle), selectinload(Compra.impuestos_detalle))
        .where(extract("year", Compra.fecha) == year, extract("month", Compra.fecha) == month)
        .order_by(Compra.fecha, Compra.id)
    )
    compras = (await session.execute(stmt)).unique().scalars().all()

    rows = []
    for compra in compras:
        row = {
            "compra_id": compra.id,
            "proveedor_id": compra.proveedor_id,
            "numero": compra.numero,
            "fecha": compra.fecha,
            "neto": compra.subtotal,
            "iva_21": 0.0,
            "iva_10_5": 0.0,
            "iva_27": 0.0,
            # Not a distinct CompraImpuesto tipo in this model — a 0%
            # detalle line can't be told apart from "exento" here (no
            # per-line marker exists yet); bucketed under no_gravado.
            "exento": 0.0,
            "no_gravado": 0.0,
            "percepcion_iva": 0.0,
            "percepcion_iibb": 0.0,
            # Legacy migrated compras with no recoverable alícuota split
            # (see design.md D5) — never fabricated into a specific
            # alícuota column above.
            "sin_discriminar": 0.0,
            "total": compra.total,
        }
        for item in compra.detalle:
            if item.alicuota_iva == 21:
                row["iva_21"] += item.importe_iva
            elif item.alicuota_iva == 10.5:
                row["iva_10_5"] += item.importe_iva
            elif item.alicuota_iva == 27:
                row["iva_27"] += item.importe_iva
            elif item.alicuota_iva == 0:
                row["no_gravado"] += item.importe_neto
        for impuesto in compra.impuestos_detalle:
            if impuesto.tipo in IMPUESTO_COLUMN_MAP:
                row[IMPUESTO_COLUMN_MAP[impuesto.tipo]] += impuesto.importe
            elif impuesto.tipo == "HISTORICO_SIN_DESGLOSE":
                row["sin_discriminar"] += impuesto.importe
            # RETENCION_*/IMPUESTOS_INTERNOS are informational and don't
            # have a column in this report.
        rows.append(row)
    return rows
