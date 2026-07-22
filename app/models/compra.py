from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.proveedor import Proveedor


class Compra(Base):
    __tablename__ = "compras_compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("costos_proveedor.id"))
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    # Plain Integer, not an ORM ForeignKey: compras_orden_compra is defined
    # in app/models/orden_compra.py, imported separately (Group 8) — the DB
    # already enforces this FK via the raw-SQL migration; the ORM doesn't
    # need cross-module metadata coupling to know about it.
    orden_compra_id: Mapped[int | None] = mapped_column(Integer, default=None)
    tipo_comprobante: Mapped[str] = mapped_column(String(20))
    punto_venta: Mapped[str | None] = mapped_column(String(20), default=None)
    numero: Mapped[str] = mapped_column(String(50))
    fecha: Mapped[date] = mapped_column(Date)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, default=None)
    condicion_pago: Mapped[str] = mapped_column(String(20), default="CUENTA_CORRIENTE")
    categoria: Mapped[str] = mapped_column(String(250), default="MATERIA_PRIMA")
    observaciones: Mapped[str | None] = mapped_column(String(500), default=None)
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    iva: Mapped[float] = mapped_column(Float, default=0)
    percepciones: Mapped[float] = mapped_column(Float, default=0)
    impuestos: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    # Trigger-maintained (trg_update_compra_saldo_pendiente on
    # compras_pago_aplicacion) — application code must never decrement this
    # directly. See design.md D1/D2.
    saldo_pendiente: Mapped[float] = mapped_column(Float, default=0)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    detalle: Mapped[list["CompraDetalle"]] = relationship(
        back_populates="compra", cascade="all, delete-orphan"
    )
    impuestos_detalle: Mapped[list["CompraImpuesto"]] = relationship(
        back_populates="compra", cascade="all, delete-orphan"
    )
    adjuntos: Mapped[list["CompraAdjunto"]] = relationship(
        back_populates="compra", cascade="all, delete-orphan"
    )

    @property
    def proveedor_nombre(self) -> str:
        return self.proveedor.nombre


class CompraDetalle(Base):
    __tablename__ = "compras_compra_detalle"

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras_compra.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(20), default="LIBRE")
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("costos_insumos.id"), default=None)
    item_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("compras_item_gasto.id"), default=None)
    descripcion: Mapped[str] = mapped_column(String(500))
    cantidad: Mapped[float] = mapped_column(Float, default=1)
    precio_unitario: Mapped[float] = mapped_column(Float)
    descuento: Mapped[float] = mapped_column(Float, default=0)
    alicuota_iva: Mapped[float] = mapped_column(Float, default=0)
    importe_neto: Mapped[float] = mapped_column(Float)
    importe_iva: Mapped[float] = mapped_column(Float, default=0)
    importe_total: Mapped[float] = mapped_column(Float)
    # Reserved for a future accounting capability — no behavior yet (Non-Goal).
    centro_costo_id: Mapped[int | None] = mapped_column(Integer, default=None)
    cuenta_contable_id: Mapped[int | None] = mapped_column(Integer, default=None)

    compra: Mapped[Compra] = relationship(back_populates="detalle")


class CompraImpuesto(Base):
    __tablename__ = "compras_compra_impuesto"

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras_compra.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(30))
    base_imponible: Mapped[float] = mapped_column(Float, default=0)
    porcentaje: Mapped[float | None] = mapped_column(Float, default=None)
    importe: Mapped[float] = mapped_column(Float)

    compra: Mapped[Compra] = relationship(back_populates="impuestos_detalle")


class CompraAdjunto(Base):
    __tablename__ = "compras_compra_adjunto"

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras_compra.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(255))
    # Stored directly in Postgres instead of external object storage —
    # deferred so listing/reading a Compra never pulls image bytes over the
    # wire; fetched only via GET /compras/{id}/adjuntos/{adjunto_id}.
    contenido: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    tipo: Mapped[str | None] = mapped_column(String(20), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    compra: Mapped[Compra] = relationship(back_populates="adjuntos")
