from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.proveedor import Proveedor


class MovimientoCC(Base):
    """Append-only ledger. Balance is never stored here — it's computed at
    query time as a running sum ordered by (fecha, id). See design.md D1.
    """

    __tablename__ = "compras_movimiento_cc"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("costos_proveedor.id"))
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    fecha: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(20))
    documento: Mapped[str] = mapped_column(String(100))
    debe: Mapped[float] = mapped_column(Float, default=0)
    haber: Mapped[float] = mapped_column(Float, default=0)
    # Plain Integer, not ORM ForeignKey — same rationale as Compra.orden_compra_id.
    compra_id: Mapped[int | None] = mapped_column(Integer, default=None)
    pago_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
