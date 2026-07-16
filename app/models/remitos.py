from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.clientes import Clientes


class Remitos(Base):
    __tablename__ = "costos_remitos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.idcliente"), default=None)
    cliente: Mapped[Clientes | None] = relationship(lazy="joined")
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)
    vendedor: Mapped[str] = mapped_column(String(255))
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_preparacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_listo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_despacho: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_recibido: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_facturacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    detalles: Mapped[list["RemitoDetalles"]] = relationship(
        back_populates="remito", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def estado(self) -> str:
        # Matches panacea-mayorista-backend's EstadoRemito/derive_estado
        # vocabulary and precedence exactly, for API compatibility.
        if self.fecha_facturacion:
            return "facturado"
        if self.fecha_recibido:
            return "en_entrega"
        if self.fecha_despacho:
            return "listo_entregar"
        if self.fecha_listo:
            return "preparando"
        if self.fecha_preparacion:
            return "en_produccion"
        return "creado"


class RemitoDetalles(Base):
    __tablename__ = "costos_remitodetalles"

    id: Mapped[int] = mapped_column(primary_key=True)
    remito_id: Mapped[int | None] = mapped_column(ForeignKey("costos_remitos.id"), default=None)
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    cantidad: Mapped[int] = mapped_column(Integer)
    entregado: Mapped[int | None] = mapped_column(Integer, default=None)
    observaciones: Mapped[str | None] = mapped_column(String(1000), default=None)

    remito: Mapped[Remitos] = relationship(back_populates="detalles")
    producto = relationship("Productos", lazy="joined")
