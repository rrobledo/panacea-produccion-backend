from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
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
    # Destino cuando tipo=SUCURSAL. El origen se completa con la única
    # sucursal FABRICA si no se informa — ver pedido_service.create_pedido.
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales_sucursal.id"), default=None)
    sucursal: Mapped[Sucursal | None] = relationship(lazy="joined", foreign_keys=[sucursal_id])
    origen_sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales_sucursal.id"), default=None)
    origen_sucursal: Mapped[Sucursal | None] = relationship(lazy="joined", foreign_keys=[origen_sucursal_id])
    # Remito cargado directamente, sin pedido previo: cantidad_pedida = 0 en
    # todas las líneas y lo despachado en cantidad_entregada. Ver
    # openspec/changes/unificar-pedidos-y-remitos/design.md D1.
    es_remito: Mapped[bool] = mapped_column(Boolean, default=False)
    vendedor: Mapped[str] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Historial de estados: una fecha por cada paso alcanzado, seteada en
    # transition_estado (y en create_pedido para un remito directo). estado
    # sigue siendo una columna propia, no se deriva de estas fechas — ver
    # Decisión en specs/pedidos/spec.md.
    fecha_en_preparacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_preparado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_listo_para_entrega: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_entregado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_cancelado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)
    # Facturación: las dos informadas o las dos nulas, ver
    # pedido_service.registrar_facturacion.
    fecha_facturado: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    factura_referencia: Mapped[str | None] = mapped_column(String(100), default=None)

    detalles: Mapped[list["PedidoDetalle"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan", lazy="selectin"
    )
    remitos_legacy: Mapped[list["PedidoRemitoLegacy"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class PedidoDetalle(Base):
    __tablename__ = "pedidos_pedido_detalle"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_pedido.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    cantidad_pedida: Mapped[int] = mapped_column(Integer)
    cantidad_entregada: Mapped[int] = mapped_column(Integer, default=0)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)
    # Distingue ítems agregados con la creación del pedido de los agregados
    # después en una edición — preservada por update_pedido, ver
    # app/services/pedido_service.py.
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pedido: Mapped[Pedido] = relationship(back_populates="detalles")
    producto = relationship("Productos", lazy="joined")


class PedidoRemitoLegacy(Base):
    """Número de un remito de remitos_remito (fuera del modelo desde la
    unificación) y el envío que lo reemplaza, para encontrar remitos impresos
    antes de la unificación. Lo completa
    scripts/migrate_remitos_to_pedidos_unificados.sql; la app solo lo lee."""

    __tablename__ = "pedidos_remito_legacy"

    remito_legacy_id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_pedido.id", ondelete="CASCADE"))
