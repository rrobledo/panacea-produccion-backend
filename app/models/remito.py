from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.clientes import Clientes
from app.models.sucursal import Sucursal


class Remito(Base):
    __tablename__ = "remitos_remito"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.idcliente"), default=None)
    cliente: Mapped[Clientes | None] = relationship(lazy="joined")
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos_pedido.id"), default=None)
    origen_sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales_sucursal.id"), default=None)
    origen_sucursal: Mapped[Sucursal | None] = relationship(lazy="joined", foreign_keys=[origen_sucursal_id])
    destino_sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales_sucursal.id"), default=None)
    destino_sucursal: Mapped[Sucursal | None] = relationship(lazy="joined", foreign_keys=[destino_sucursal_id])
    vendedor: Mapped[str | None] = mapped_column(String(255), default=None)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_listo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_despacho: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_recibido: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    detalles: Mapped[list["RemitoDetalle"]] = relationship(
        back_populates="remito", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def estado(self) -> str:
        # Timestamp-precedence pattern, same as before but one step
        # shorter: el remito nace en LISTO (fecha_listo seteada al crear),
        # ya no pasa por PENDIENTE/EN_PREPARACION.
        if self.fecha_recibido:
            return "RECIBIDO"
        if self.fecha_despacho:
            return "EN_TRANSITO"
        return "LISTO"


class RemitoDetalle(Base):
    __tablename__ = "remitos_remito_detalle"

    id: Mapped[int] = mapped_column(primary_key=True)
    remito_id: Mapped[int] = mapped_column(ForeignKey("remitos_remito.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    cantidad: Mapped[int] = mapped_column(Integer)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)

    remito: Mapped[Remito] = relationship(back_populates="detalles")
    producto = relationship("Productos", lazy="joined")
