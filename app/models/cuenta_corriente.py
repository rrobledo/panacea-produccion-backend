from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.insumos import Insumos
from app.models.proveedor import Proveedor


class CuentaCorrienteProveedor(Base):
    __tablename__ = "costos_cuentacorrienteproveedor"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("costos_proveedor.id"))
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    tipo_movimiento: Mapped[str] = mapped_column(String(250), default="FACTURA")
    numero: Mapped[str] = mapped_column(String(50))
    fecha_emision: Mapped[date] = mapped_column(Date)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, default=None)
    importe_total: Mapped[float] = mapped_column(Float)
    importe_pendiente: Mapped[float | None] = mapped_column(Float, default=0)
    observaciones: Mapped[str | None] = mapped_column(String(250), default=None)
    categoria: Mapped[str] = mapped_column(String(250), default="MATERIA_PRIMA")
    tipo_pago: Mapped[str] = mapped_column(String(250), default="CUENTA_CORRIENTE")
    caja: Mapped[str] = mapped_column(String(250), default="VA")
    estado: Mapped[str] = mapped_column(String(250), default="PENDIENTE")
    iva: Mapped[float | None] = mapped_column(Float, default=0)
    percepcion: Mapped[float | None] = mapped_column(Float, default=0)
    # Deferred: these hold base64 receipt images (observed ~1GB total across
    # ~900 rows in production) — loading them on every list/query would pull
    # that whole volume over the wire for data callers never use. Only
    # fetched when explicitly requested via `.options(undefer(...))`.
    image: Mapped[str | None] = mapped_column(Text, default=None, deferred=True)
    image2: Mapped[str | None] = mapped_column(Text, default=None, deferred=True)
    content_type: Mapped[str | None] = mapped_column(String(100), default=None, deferred=True)
    detalle: Mapped[list["CuentaCorrienteProveedorDetalle"]] = relationship(
        back_populates="cuenta_corriente", cascade="all, delete-orphan"
    )


class CuentaCorrienteProveedorAfect(Base):
    __tablename__ = "costos_cuentacorrienteproveedorafect"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("costos_cuentacorrienteproveedor.id"))
    pago_id: Mapped[int] = mapped_column(ForeignKey("costos_cuentacorrienteproveedor.id"))
    importe: Mapped[float] = mapped_column(Float)


class CuentaCorrienteProveedorDetalle(Base):
    __tablename__ = "costos_cuentacorrienteproveedordetalle"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuentacorrienteproveedor_id: Mapped[int] = mapped_column(
        ForeignKey("costos_cuentacorrienteproveedor.id", ondelete="CASCADE")
    )
    insumo_id: Mapped[int] = mapped_column(ForeignKey("costos_insumos.id"))
    cantidad: Mapped[float] = mapped_column(Float)
    subtotal: Mapped[float] = mapped_column(Float)

    cuenta_corriente: Mapped[CuentaCorrienteProveedor] = relationship(back_populates="detalle")
    insumo: Mapped[Insumos] = relationship(lazy="joined")
