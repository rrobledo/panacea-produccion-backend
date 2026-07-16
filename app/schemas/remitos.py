from datetime import datetime

from pydantic import BaseModel

from app.schemas.clientes import ClienteRead
from app.schemas.productos import ProductoRead


class RemitoDetalleCreate(BaseModel):
    producto_id: int
    cantidad: int
    observaciones: str | None = None
    # Not part of mayorista's RemitoDetalleCreate contract (it never lets a
    # caller set this at create/update time) — kept as an extra optional
    # field since callers that don't send it behave identically to mayorista.
    entregado: int | None = None


class RemitoDetalleRead(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    entregado: int | None
    observaciones: str | None
    producto: ProductoRead | None

    @classmethod
    def from_orm_row(cls, row) -> "RemitoDetalleRead":
        return cls(
            id=row.id,
            producto_id=row.producto_id,
            cantidad=row.cantidad,
            entregado=row.entregado,
            observaciones=row.observaciones,
            producto=ProductoRead.model_validate(row.producto) if row.producto else None,
        )


class EstadoTransitionRequest(BaseModel):
    nuevo_estado: str


class RemitoCreate(BaseModel):
    cliente_id: int
    vendedor: str
    observaciones: str | None = None
    fecha_entrega: datetime
    detalles: list[RemitoDetalleCreate] = []


class RemitoUpdate(BaseModel):
    cliente_id: int | None = None
    vendedor: str | None = None
    observaciones: str | None = None
    fecha_entrega: datetime | None = None
    detalles: list[RemitoDetalleCreate] | None = None


class RemitoRead(BaseModel):
    id: int
    cliente_id: int | None
    cliente: ClienteRead | None
    estado: str
    observaciones: str | None
    vendedor: str
    fecha_carga: datetime
    fecha_entrega: datetime
    fecha_preparacion: datetime | None
    fecha_listo: datetime | None
    fecha_despacho: datetime | None
    fecha_recibido: datetime | None
    fecha_facturacion: datetime | None
    detalles: list[RemitoDetalleRead]

    @classmethod
    def from_orm_row(cls, row) -> "RemitoRead":
        return cls(
            id=row.id,
            cliente_id=row.cliente_id,
            cliente=ClienteRead.from_orm_row(row.cliente) if row.cliente else None,
            estado=row.estado,
            observaciones=row.observaciones,
            vendedor=row.vendedor,
            fecha_carga=row.fecha_carga,
            fecha_entrega=row.fecha_entrega,
            fecha_preparacion=row.fecha_preparacion,
            fecha_listo=row.fecha_listo,
            fecha_despacho=row.fecha_despacho,
            fecha_recibido=row.fecha_recibido,
            fecha_facturacion=row.fecha_facturacion,
            detalles=[RemitoDetalleRead.from_orm_row(d) for d in row.detalles],
        )
