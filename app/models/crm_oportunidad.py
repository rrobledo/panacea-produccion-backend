from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CrmEtapaVenta(Base):
    __tablename__ = "crm_etapa_venta"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    orden: Mapped[int] = mapped_column(Integer, unique=True)


class CrmOportunidad(Base):
    __tablename__ = "crm_oportunidad"

    id: Mapped[int] = mapped_column(primary_key=True)
    contacto_id: Mapped[int] = mapped_column(ForeignKey("crm_contacto.id"))
    visita_id: Mapped[int | None] = mapped_column(ForeignKey("crm_visita.id"), default=None)
    etapa_id: Mapped[int] = mapped_column(ForeignKey("crm_etapa_venta.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    etapa: Mapped[CrmEtapaVenta] = relationship(lazy="joined")

    @property
    def etapa_nombre(self) -> str:
        return self.etapa.nombre


class CrmActividad(Base):
    __tablename__ = "crm_actividad"

    id: Mapped[int] = mapped_column(primary_key=True)
    oportunidad_id: Mapped[int] = mapped_column(ForeignKey("crm_oportunidad.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(50))
    fecha: Mapped[date] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
