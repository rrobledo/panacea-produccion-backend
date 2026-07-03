from datetime import datetime

from pydantic import BaseModel


class RemitoDetalleCreate(BaseModel):
    producto: int
    cantidad: int
    entregado: int | None = None
    observaciones: str | None = None


class RemitoDetalleRead(BaseModel):
    id: int
    remito: int | None
    producto: int
    producto_id: str
    producto_nombre: str
    cantidad: int
    entregado: int | None
    observaciones: str | None

    @classmethod
    def from_orm_row(cls, row) -> "RemitoDetalleRead":
        return cls(
            id=row.id,
            remito=row.remito_id,
            producto=row.producto_id,
            producto_id=str(row.producto_id),
            producto_nombre=row.producto.nombre,
            cantidad=row.cantidad,
            entregado=row.entregado,
            observaciones=row.observaciones,
        )


class RemitoCreate(BaseModel):
    cliente: int | None = None
    observaciones: str | None = None
    vendedor: str
    fecha_entrega: datetime
    fecha_preparacion: datetime | None = None
    fecha_listo: datetime | None = None
    fecha_despacho: datetime | None = None
    fecha_recibido: datetime | None = None
    fecha_facturacion: datetime | None = None
    productos: list[RemitoDetalleCreate] = []


class RemitoRead(BaseModel):
    id: int
    cliente_id: str | None
    cliente_nombre: str | None
    cliente: int | None
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
    productos: list[RemitoDetalleRead]

    @classmethod
    def from_orm_row(cls, row) -> "RemitoRead":
        return cls(
            id=row.id,
            cliente_id=str(row.cliente_id) if row.cliente_id is not None else None,
            cliente_nombre=row.cliente.nom1 + ", " + row.cliente.nom2 if row.cliente else None,
            cliente=row.cliente_id,
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
            productos=[RemitoDetalleRead.from_orm_row(d) for d in row.productos],
        )
