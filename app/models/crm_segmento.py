from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrmSegmento(Base):
    __tablename__ = "crm_segmento"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), unique=True)
    criterio: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmContactoSegmento(Base):
    __tablename__ = "crm_contacto_segmento"
    __table_args__ = (UniqueConstraint("contacto_id", "segmento_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contacto_id: Mapped[int] = mapped_column(ForeignKey("crm_contacto.id", ondelete="CASCADE"))
    segmento_id: Mapped[int] = mapped_column(ForeignKey("crm_segmento.id", ondelete="CASCADE"))
    recalculado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
