from datetime import datetime

from pydantic import BaseModel, model_validator

from app.schemas.clientes import ClienteRead
from app.schemas.productos import ProductoRead
from app.schemas.sucursal import SucursalRead
from app.schemas.vocab import RemitoTipo


class RemitoDetalleCreate(BaseModel):
    producto_id: int
    cantidad: int
    observaciones: str | None = None


class RemitoDetalleRead(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    observaciones: str | None
    producto: ProductoRead | None

    @classmethod
    def from_orm_row(cls, row) -> "RemitoDetalleRead":
        return cls(
            id=row.id,
            producto_id=row.producto_id,
            cantidad=row.cantidad,
            observaciones=row.observaciones,
            producto=ProductoRead.model_validate(row.producto) if row.producto else None,
        )


class _RemitoTipoFieldsMixin(BaseModel):
    tipo: RemitoTipo
    cliente_id: int | None = None
    pedido_id: int | None = None
    origen_sucursal_id: int | None = None
    destino_sucursal_id: int | None = None

    @model_validator(mode="after")
    def _validate_tipo_fields(self):
        if self.tipo == "VENTA":
            if self.cliente_id is None:
                raise ValueError("cliente_id is required when tipo=VENTA")
            if self.origen_sucursal_id is not None or self.destino_sucursal_id is not None:
                raise ValueError("origen_sucursal_id/destino_sucursal_id must be null when tipo=VENTA")
        elif self.tipo == "TRANSFERENCIA":
            if self.cliente_id is not None or self.pedido_id is not None:
                raise ValueError("cliente_id/pedido_id must be null when tipo=TRANSFERENCIA")
            if self.origen_sucursal_id is None or self.destino_sucursal_id is None:
                raise ValueError("origen_sucursal_id and destino_sucursal_id are required when tipo=TRANSFERENCIA")
            if self.origen_sucursal_id == self.destino_sucursal_id:
                raise ValueError("origen_sucursal_id and destino_sucursal_id must be different")
        return self


class RemitoCreate(_RemitoTipoFieldsMixin):
    vendedor: str | None = None
    observaciones: str | None = None
    detalles: list[RemitoDetalleCreate] = []


class RemitoUpdate(BaseModel):
    vendedor: str | None = None
    observaciones: str | None = None
    detalles: list[RemitoDetalleCreate] | None = None


class RemitoRead(BaseModel):
    id: int
    tipo: str
    cliente_id: int | None
    cliente: ClienteRead | None
    pedido_id: int | None
    origen_sucursal_id: int | None
    origen_sucursal: SucursalRead | None
    destino_sucursal_id: int | None
    destino_sucursal: SucursalRead | None
    estado: str
    vendedor: str | None
    observaciones: str | None
    fecha_carga: datetime
    fecha_listo: datetime | None
    fecha_despacho: datetime | None
    fecha_recibido: datetime | None
    detalles: list[RemitoDetalleRead]

    @classmethod
    def from_orm_row(cls, row) -> "RemitoRead":
        return cls(
            id=row.id,
            tipo=row.tipo,
            cliente_id=row.cliente_id,
            cliente=ClienteRead.from_orm_row(row.cliente) if row.cliente else None,
            pedido_id=row.pedido_id,
            origen_sucursal_id=row.origen_sucursal_id,
            origen_sucursal=SucursalRead.from_orm_row(row.origen_sucursal) if row.origen_sucursal else None,
            destino_sucursal_id=row.destino_sucursal_id,
            destino_sucursal=SucursalRead.from_orm_row(row.destino_sucursal) if row.destino_sucursal else None,
            estado=row.estado,
            vendedor=row.vendedor,
            observaciones=row.observaciones,
            fecha_carga=row.fecha_carga,
            fecha_listo=row.fecha_listo,
            fecha_despacho=row.fecha_despacho,
            fecha_recibido=row.fecha_recibido,
            detalles=[RemitoDetalleRead.from_orm_row(d) for d in row.detalles],
        )


class EstadoTransitionRequest(BaseModel):
    nuevo_estado: str
