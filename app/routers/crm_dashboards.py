import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.deps import get_session
from app.models.crm_vendedor import CrmVendedor
from app.models.user import User
from app.services import crm_analytics_service

router = APIRouter(prefix="/crm/dashboards", tags=["crm-dashboards-kpis"])

EJECUTIVO_ROLES = ("admin", "gerencia")
VENDEDOR_ROLES = ("admin", "gerencia", "supervisor_comercial", "vendedor")
MARKETING_ROLES = ("admin", "gerencia", "marketing")
CONTACTO_ROLES = ("admin", "gerencia", "marketing", "supervisor_comercial", "vendedor")


def _default_range(fecha_desde: date | None, fecha_hasta: date | None) -> tuple[date, date]:
    hasta = fecha_hasta or date.today()
    desde = fecha_desde or (hasta - timedelta(days=365))
    return desde, hasta


@router.get("/ejecutivo")
async def dashboard_ejecutivo(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*EJECUTIVO_ROLES)),
):
    desde, hasta = _default_range(fecha_desde, fecha_hasta)
    return await crm_analytics_service.dashboard_ejecutivo(session, desde, hasta)


@router.get("/vendedor/{vendedor_id}")
async def dashboard_vendedor(
    vendedor_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*VENDEDOR_ROLES)),
):
    if current_user.role == "vendedor":
        own = (
            await session.execute(select(CrmVendedor).where(CrmVendedor.user_id == current_user.id))
        ).scalar_one_or_none()
        if own is None or own.id != vendedor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view another vendedor's dashboard")
    return await crm_analytics_service.dashboard_vendedor(session, vendedor_id)


@router.get("/marketing")
async def dashboard_marketing(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_role(*MARKETING_ROLES))
):
    return await crm_analytics_service.dashboard_marketing(session)


@router.get("/contacto/{contacto_id}")
async def dashboard_contacto(
    contacto_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CONTACTO_ROLES)),
):
    return await crm_analytics_service.dashboard_contacto_360(session, contacto_id)


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else []
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reportes/ventas-por-segmento")
async def reporte_ventas_por_segmento(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    formato: str = "json",
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*EJECUTIVO_ROLES, "marketing")),
):
    rows = await crm_analytics_service.ventas_por_segmento(session, fecha_desde, fecha_hasta)
    if formato == "csv":
        return _csv_response(rows, "ventas-por-segmento.csv")
    return rows


@router.get("/reportes/clientes-inactivos")
async def reporte_clientes_inactivos(
    dias: int = 60,
    formato: str = "json",
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*EJECUTIVO_ROLES, "marketing")),
):
    rows = await crm_analytics_service.clientes_inactivos(session, dias)
    if formato == "csv":
        return _csv_response(rows, "clientes-inactivos.csv")
    return rows
