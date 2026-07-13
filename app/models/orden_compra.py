from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.proveedor import Proveedor


class OrdenCompra(Base):
    __tablename__ = "compras_orden_compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("costos_proveedor.id"))
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    fecha: Mapped[date] = mapped_column(Date)
    fecha_entrega_estimada: Mapped[date | None] = mapped_column(Date, default=None)
    observaciones: Mapped[str | None] = mapped_column(String(500), default=None)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    detalle: Mapped[list["OrdenCompraDetalle"]] = relationship(
        back_populates="orden_compra", cascade="all, delete-orphan"
    )

    @property
    def proveedor_nombre(self) -> str:
        return self.proveedor.nombre


class OrdenCompraDetalle(Base):
    __tablename__ = "compras_orden_compra_detalle"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_compra_id: Mapped[int] = mapped_column(ForeignKey("compras_orden_compra.id", ondelete="CASCADE"))
    descripcion: Mapped[str | None] = mapped_column(String(500), default=None)
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("costos_insumos.id"), default=None)
    cantidad_pedida: Mapped[float] = mapped_column(Float)
    cantidad_recibida: Mapped[float] = mapped_column(Float, default=0)
    precio_unitario_estimado: Mapped[float | None] = mapped_column(Float, default=None)

    orden_compra: Mapped[OrdenCompra] = relationship(back_populates="detalle")
