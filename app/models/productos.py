from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Productos(Base):
    __tablename__ = "costos_productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50))
    categoria: Mapped[str] = mapped_column(String(250), default="PANADERIA")
    nombre: Mapped[str] = mapped_column(String(250))
    ref_id: Mapped[str | None] = mapped_column(String(250), default=None)
    utilidad: Mapped[float] = mapped_column(Float)
    precio_actual: Mapped[float] = mapped_column(Float)
    unidad_medida: Mapped[str] = mapped_column(String(10), default="GR")
    lote_produccion: Mapped[int] = mapped_column(Integer)
    tiempo_produccion: Mapped[int] = mapped_column(Integer, default=0)
    responsable: Mapped[str] = mapped_column(String(50), default="Todos")
    is_producto: Mapped[bool] = mapped_column(Boolean, default=True)
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True)
    prioridad: Mapped[int] = mapped_column(Integer, default=10)


class ProductosRef(Base):
    __tablename__ = "costos_productosref"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    ref_id: Mapped[str | None] = mapped_column(String(250), default=None)
    unidad_conversion: Mapped[int] = mapped_column(Integer, default=1)


class Costos(Base):
    __tablename__ = "costos_costos"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("costos_productos.id"))
    insumo_id: Mapped[int] = mapped_column(ForeignKey("costos_insumos.id"))
    cantidad: Mapped[int] = mapped_column(Integer)

    insumo = relationship("Insumos", lazy="joined")
