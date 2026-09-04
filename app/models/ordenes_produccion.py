from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class OrdenProduccion(Base):
    __tablename__ = "ordenes_produccion"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True)
    fecha_fabricacion: Mapped[date] = mapped_column(Date)
    responsable: Mapped[str] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(String(20), default="ASIGNADA")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_en_produccion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_finalizada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fecha_cancelada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    productos: Mapped[list["OrdenProduccionProductoLinea"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan", lazy="selectin"
    )
    insumos: Mapped[list["OrdenProduccionInsumoLinea"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan", lazy="selectin"
    )


class OrdenProduccionProductoLinea(Base):
    __tablename__ = "ordenes_produccion_producto_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_produccion.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    cantidad_planeada: Mapped[int] = mapped_column(Integer)

    orden: Mapped[OrdenProduccion] = relationship(back_populates="productos")
    producto = relationship("Productos", lazy="joined")


class OrdenProduccionInsumoLinea(Base):
    __tablename__ = "ordenes_produccion_insumo_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_produccion.id"))
    insumo_id: Mapped[int] = mapped_column(ForeignKey("costos_insumos.id"))
    cantidad: Mapped[float] = mapped_column(Float)

    orden: Mapped[OrdenProduccion] = relationship(back_populates="insumos")
    insumo = relationship("Insumos", lazy="joined")


class ProductoFabricado(Base):
    __tablename__ = "productos_fabricados"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_produccion.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    cantidad_fabricada: Mapped[float] = mapped_column(Float)
    ubicacion_id: Mapped[int] = mapped_column(ForeignKey("ubicaciones_ubicacion.id"))
    cantidad_desperdicio: Mapped[float] = mapped_column(Float, default=0)
    ubicacion_desperdicio_id: Mapped[int | None] = mapped_column(
        ForeignKey("ubicaciones_ubicacion.id"), default=None
    )
    motivo_desperdicio: Mapped[str | None] = mapped_column(String(500), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    orden: Mapped[OrdenProduccion] = relationship(lazy="joined")
    producto = relationship("Productos", lazy="joined")
    ubicacion = relationship("Ubicacion", foreign_keys=[ubicacion_id], lazy="joined")
    ubicacion_desperdicio = relationship("Ubicacion", foreign_keys=[ubicacion_desperdicio_id], lazy="joined")
