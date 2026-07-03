import calendar
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_cron_secret
from app.services import programacion_service

router = APIRouter(tags=["cron"])
logger = logging.getLogger("panacea_produccion_backend.cron")


def _next_calendar_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


@router.post("/internal/cron/monthly-cascade", dependencies=[Depends(require_cron_secret)])
async def monthly_cascade(session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    if now.day != last_day:
        return {"skipped": True, "reason": "not the last day of the month"}

    next_year, next_month = _next_calendar_month(now.year, now.month)
    result = await programacion_service.generate_programacion(
        session,
        year=next_year,
        month=next_month,
        prev_year=now.year,
        prev_month=now.month,
        producto_id=None,
        dry_run=False,
    )
    logger.info(
        "monthly cascade: generated programacion for %s-%s (prev %s-%s): %s",
        next_year, next_month, now.year, now.month, result,
    )
    return result
