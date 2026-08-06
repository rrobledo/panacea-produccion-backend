from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrmClubSocioCache(Base):
    __tablename__ = "crm_club_socio_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    contacto_id: Mapped[int] = mapped_column(ForeignKey("crm_contacto.id", ondelete="CASCADE"), unique=True)
    socio_id: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str | None] = mapped_column(String(100), default=None)
    puntos: Mapped[int | None] = mapped_column(Integer, default=None)
    fecha_alta: Mapped[date | None] = mapped_column(Date, default=None)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
