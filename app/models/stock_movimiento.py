from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StockMovimiento(Base):
    __tablename__ = "stock_movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Un movimiento es de un artículo, y los artículos viven en dos tablas:
    # exactamente uno de los dos va cargado (CHECK de la migración 0029).
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("costos_insumos.id"), default=None)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("costos_productos.id"), default=None)
    # De insumo:   RESERVA/AJUSTE positivo o negativo; CONSUMO siempre negativo
    #              (baja insumos.cantidad). RESERVA no toca insumos.cantidad.
    # De producto: PRODUCCION positivo (una orden finalizada lo fabricó),
    #              CONSUMO_INTERNO negativo (otro proceso lo consumió). Estos no
    #              materializan un campo `cantidad`: el disponible de un
    #              artículo producido se deriva sumando su ledger, ver
    #              stock_service.disponible_de_articulo.
    tipo: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[float] = mapped_column(Float)
    # RESERVA y CONSUMO salen de una orden; AJUSTE no, y queda en NULL.
    # `referencia` sigue guardando el código de la orden (o el motivo, para los
    # AJUSTE) hasta que nadie la lea — ver tasks.md 8.5.
    orden_id: Mapped[int | None] = mapped_column(
        ForeignKey("ordenes_produccion.id", ondelete="CASCADE"), default=None
    )
    referencia: Mapped[str | None] = mapped_column(String(255), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    insumo = relationship("Insumos", lazy="joined")
    producto = relationship("Productos", lazy="joined")
