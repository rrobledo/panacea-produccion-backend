from datetime import date
from typing import Literal

from pydantic import BaseModel

TipoMovimiento = Literal["FACTURA", "PAGO"]


class DetalleInsumoCreate(BaseModel):
    insumo: int
    cantidad: float
    subtotal: float


class DetalleInsumoRead(BaseModel):
    id: int
    insumo: int
    cantidad: float
    subtotal: float

    @classmethod
    def from_orm_row(cls, row) -> "DetalleInsumoRead":
        return cls(id=row.id, insumo=row.insumo_id, cantidad=row.cantidad, subtotal=row.subtotal)


class CuentaCorrienteProveedorCreate(BaseModel):
    proveedor: int
    tipo_movimiento: TipoMovimiento = "FACTURA"
    numero: str
    fecha_emision: date
    fecha_vencimiento: date | None = None
    importe_total: float
    iva: float = 0
    percepcion: float = 0
    observaciones: str | None = None
    categoria: str = "MATERIA_PRIMA"
    tipo_pago: str = "CUENTA_CORRIENTE"
    caja: str = "VA"
    image: str | None = None
    image2: str | None = None
    # Only used when tipo_movimiento == "PAGO": the factura this payment applies to.
    factura_id: int | None = None
    insumos: list[DetalleInsumoCreate] | None = None


class CuentaCorrienteProveedorUpdate(CuentaCorrienteProveedorCreate):
    estado: str | None = None
    importe_pendiente: float | None = None


class CuentaCorrienteProveedorRead(BaseModel):
    id: int
    proveedor_id: str
    proveedor_nombre: str
    proveedor: int
    tipo_movimiento: TipoMovimiento
    numero: str
    fecha_emision: date
    fecha_vencimiento: date | None
    importe_total: float
    importe_pendiente: float | None
    iva: float | None
    percepcion: float | None
    observaciones: str | None
    categoria: str
    tipo_pago: str
    caja: str
    estado: str

    @classmethod
    def from_orm_row(cls, row) -> "CuentaCorrienteProveedorRead":
        return cls(**cls._base_fields(row))

    @staticmethod
    def _base_fields(row) -> dict:
        return dict(
            id=row.id,
            proveedor_id=str(row.proveedor_id),
            proveedor_nombre=row.proveedor.nombre,
            proveedor=row.proveedor_id,
            tipo_movimiento=row.tipo_movimiento,
            numero=row.numero,
            fecha_emision=row.fecha_emision,
            fecha_vencimiento=row.fecha_vencimiento,
            importe_total=row.importe_total,
            importe_pendiente=row.importe_pendiente,
            iva=row.iva,
            percepcion=row.percepcion,
            observaciones=row.observaciones,
            categoria=row.categoria,
            tipo_pago=row.tipo_pago,
            caja=row.caja,
            estado=row.estado,
        )


class CuentaCorrienteProveedorDetailRead(CuentaCorrienteProveedorRead):
    # Only used for single-record create/read/update responses, never list.
    image: str | None
    image2: str | None
    insumos: list[DetalleInsumoRead]

    @classmethod
    def from_orm_row(cls, row) -> "CuentaCorrienteProveedorDetailRead":
        return cls(
            **cls._base_fields(row),
            image=row.image,
            image2=row.image2,
            insumos=[DetalleInsumoRead.from_orm_row(d) for d in row.detalle],
        )
