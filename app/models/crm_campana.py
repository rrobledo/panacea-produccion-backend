from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrmCampana(Base):
    __tablename__ = "crm_campana"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date, default=None)
    objetivo: Mapped[str | None] = mapped_column(String(500), default=None)
    costo: Mapped[float | None] = mapped_column(Numeric, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmContactoCampana(Base):
    __tablename__ = "crm_contacto_campana"
    __table_args__ = (UniqueConstraint("contacto_id", "campana_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contacto_id: Mapped[int] = mapped_column(ForeignKey("crm_contacto.id", ondelete="CASCADE"))
    campana_id: Mapped[int] = mapped_column(ForeignKey("crm_campana.id", ondelete="CASCADE"))
    fecha_asociacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
