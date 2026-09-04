from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StockMovimiento(Base):
    __tablename__ = "stock_movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("costos_insumos.id"))
    # RESERVA/AJUSTE positivo o negativo; CONSUMO siempre negativo (baja
    # insumos.cantidad). RESERVA no toca insumos.cantidad, ver stock_service.
    tipo: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[float] = mapped_column(Float)
    referencia: Mapped[str | None] = mapped_column(String(255), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    insumo = relationship("Insumos", lazy="joined")
