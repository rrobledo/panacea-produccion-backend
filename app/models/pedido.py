from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.clientes import Clientes
from app.models.sucursal import Sucursal


class Pedido(Base):
    __tablename__ = "pedidos_pedido"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), default="CLIENTE")
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.idcliente"), default=None)
    cliente: Mapped[Clientes | None] = relationship(lazy="joined")
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales_sucursal.id"), default=None)
    sucursal: Mapped[Sucursal | None] = relationship(lazy="joined")
    vendedor: Mapped[str] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Historial de estados: una fecha por cada paso alcanzado, seteada en
    # transition_estado — mismo patrón informativo que Remito, aunque acá
    # estado sigue siendo una columna propia (no se deriva de estas fechas,
    # ver Decisión en specs/pedidos/spec.md).
    fecha_en_preparacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_preparado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_listo_para_entrega: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_entregado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_cancelado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)

    detalles: Mapped[list["PedidoDetalle"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan", lazy="selectin"
    )


class PedidoDetalle(Base):
    __tablename__ = "pedidos_pedido_detalle"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_pedido.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    cantidad_pedida: Mapped[int] = mapped_column(Integer)
    cantidad_entregada: Mapped[int] = mapped_column(Integer, default=0)
    # How much of cantidad_entregada has already been copied onto a
    # generated Remito — see RemitoDetalle generation in pedido_service.
    cantidad_remitida: Mapped[int] = mapped_column(Integer, default=0)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)

    pedido: Mapped[Pedido] = relationship(back_populates="detalles")
    producto = relationship("Productos", lazy="joined")
