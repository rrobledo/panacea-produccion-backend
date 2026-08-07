from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CrmVisita(Base):
    __tablename__ = "crm_visita"

    id: Mapped[int] = mapped_column(primary_key=True)
    contacto_id: Mapped[int] = mapped_column(ForeignKey("crm_contacto.id"))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey("crm_vendedor.id"))
    fecha: Mapped[date] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text, default=None)
    resultado: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    adjuntos: Mapped[list["CrmVisitaAdjunto"]] = relationship(
        back_populates="visita", cascade="all, delete-orphan"
    )


class CrmVisitaAdjunto(Base):
    __tablename__ = "crm_visita_adjunto"

    id: Mapped[int] = mapped_column(primary_key=True)
    visita_id: Mapped[int] = mapped_column(ForeignKey("crm_visita.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(255))
    # Guardado directo en Postgres en vez de un object storage externo —
    # deferred para que listar/traer una Visita nunca arrastre los bytes del
    # archivo; se trae sólo vía GET /crm/visitas/{id}/adjuntos/{adjunto_id}.
    contenido: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    tipo: Mapped[str | None] = mapped_column(String(100), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    visita: Mapped[CrmVisita] = relationship(back_populates="adjuntos")
