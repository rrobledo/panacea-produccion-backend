from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.compra import Compra
from app.models.proveedor import Proveedor


class Pago(Base):
    __tablename__ = "compras_pago"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("costos_proveedor.id"))
    proveedor: Mapped[Proveedor] = relationship(lazy="joined")
    fecha: Mapped[date] = mapped_column(Date)
    importe: Mapped[float] = mapped_column(Float)
    categoria: Mapped[str] = mapped_column(String(250), default="MATERIA_PRIMA")
    estado: Mapped[str] = mapped_column(String(20), default="REGISTRADO")
    observaciones: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    medios: Mapped[list["PagoMedio"]] = relationship(back_populates="pago", cascade="all, delete-orphan")
    adjuntos: Mapped[list["PagoAdjunto"]] = relationship(back_populates="pago", cascade="all, delete-orphan")

    @property
    def proveedor_nombre(self) -> str:
        return self.proveedor.nombre


class PagoMedio(Base):
    __tablename__ = "compras_pago_medio"

    id: Mapped[int] = mapped_column(primary_key=True)
    pago_id: Mapped[int] = mapped_column(ForeignKey("compras_pago.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(20))
    importe: Mapped[float] = mapped_column(Float)
    banco: Mapped[str | None] = mapped_column(String(100), default=None)
    numero: Mapped[str | None] = mapped_column(String(50), default=None)
    fecha_acreditacion: Mapped[date | None] = mapped_column(Date, default=None)

    pago: Mapped[Pago] = relationship(back_populates="medios")


class PagoAplicacion(Base):
    __tablename__ = "compras_pago_aplicacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    pago_id: Mapped[int] = mapped_column(ForeignKey("compras_pago.id", ondelete="CASCADE"))
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras_compra.id"))
    importe: Mapped[float] = mapped_column(Float)

    compra: Mapped[Compra] = relationship(lazy="joined")

    @property
    def comprobante(self) -> str:
        punto_venta = (self.compra.punto_venta or "0").zfill(4)
        numero = self.compra.numero.zfill(8)
        return f"{self.compra.tipo_comprobante}:{punto_venta}-{numero}"


class PagoAdjunto(Base):
    __tablename__ = "compras_pago_adjunto"

    id: Mapped[int] = mapped_column(primary_key=True)
    pago_id: Mapped[int] = mapped_column(ForeignKey("compras_pago.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(255))
    # Same deferred-in-DB storage as CompraAdjunto.contenido.
    contenido: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    tipo: Mapped[str | None] = mapped_column(String(20), default=None)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pago: Mapped[Pago] = relationship(back_populates="adjuntos")
