from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrmAuditoria(Base):
    __tablename__ = "crm_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(50))
    entidad_id: Mapped[int] = mapped_column(Integer)
    campo: Mapped[str | None] = mapped_column(String(100), default=None)
    valor_anterior: Mapped[str | None] = mapped_column(Text, default=None)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, default=None)
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
