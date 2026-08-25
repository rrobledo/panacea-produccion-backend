from datetime import datetime

from pydantic import BaseModel, model_validator

from app.schemas.clientes import ClienteRead
from app.schemas.productos import ProductoRead
from app.schemas.sucursal import SucursalRead
from app.schemas.vocab import PedidoTipo


class PedidoDetalleCreate(BaseModel):
    producto_id: int
    cantidad_pedida: int
    observaciones: str | None = None


class PedidoDetalleRead(BaseModel):
    id: int
    producto_id: int
    cantidad_pedida: int
    cantidad_entregada: int
    observaciones: str | None
    producto: ProductoRead | None
    fecha_creacion: datetime

    @classmethod
    def from_orm_row(cls, row) -> "PedidoDetalleRead":
        return cls(
            id=row.id,
            producto_id=row.producto_id,
            cantidad_pedida=row.cantidad_pedida,
            cantidad_entregada=row.cantidad_entregada,
            observaciones=row.observaciones,
            producto=ProductoRead.model_validate(row.producto) if row.producto else None,
            fecha_creacion=row.fecha_creacion,
        )


class _PedidoTipoFieldsMixin(BaseModel):
    tipo: PedidoTipo = "CLIENTE"
    cliente_id: int | None = None
    sucursal_id: int | None = None

    @model_validator(mode="after")
    def _validate_tipo_fields(self):
        if self.tipo == "CLIENTE":
            if self.cliente_id is None:
                raise ValueError("cliente_id is required when tipo=CLIENTE")
            if self.sucursal_id is not None:
                raise ValueError("sucursal_id must be null when tipo=CLIENTE")
        elif self.tipo == "SUCURSAL":
            if self.cliente_id is not None:
                raise ValueError("cliente_id must be null when tipo=SUCURSAL")
            if self.sucursal_id is None:
                raise ValueError("sucursal_id is required when tipo=SUCURSAL")
        return self


class PedidoCreate(_PedidoTipoFieldsMixin):
    vendedor: str
    observaciones: str | None = None
    fecha_entrega: datetime
    detalles: list[PedidoDetalleCreate] = []


class PedidoUpdate(BaseModel):
    cliente_id: int | None = None
    vendedor: str | None = None
    observaciones: str | None = None
    fecha_entrega: datetime | None = None
    detalles: list[PedidoDetalleCreate] | None = None


class PedidoRead(BaseModel):
    id: int
    tipo: str
    cliente_id: int | None
    cliente: ClienteRead | None
    sucursal_id: int | None
    sucursal: SucursalRead | None
    estado: str
    vendedor: str
    observaciones: str | None
    fecha_carga: datetime
    fecha_entrega: datetime
    fecha_en_preparacion: datetime | None
    fecha_preparado: datetime | None
    fecha_listo_para_entrega: datetime | None
    fecha_entregado: datetime | None
    fecha_cancelado: datetime | None
    detalles: list[PedidoDetalleRead]

    @classmethod
    def from_orm_row(cls, row) -> "PedidoRead":
        return cls(
            id=row.id,
            tipo=row.tipo,
            cliente_id=row.cliente_id,
            cliente=ClienteRead.from_orm_row(row.cliente) if row.cliente else None,
            sucursal_id=row.sucursal_id,
            sucursal=SucursalRead.from_orm_row(row.sucursal) if row.sucursal else None,
            estado=row.estado,
            vendedor=row.vendedor,
            observaciones=row.observaciones,
            fecha_carga=row.fecha_carga,
            fecha_entrega=row.fecha_entrega,
            fecha_en_preparacion=row.fecha_en_preparacion,
            fecha_preparado=row.fecha_preparado,
            fecha_listo_para_entrega=row.fecha_listo_para_entrega,
            fecha_entregado=row.fecha_entregado,
            fecha_cancelado=row.fecha_cancelado,
            detalles=[PedidoDetalleRead.from_orm_row(d) for d in row.detalles],
        )


class EstadoTransitionRequest(BaseModel):
    nuevo_estado: str


class PedidoEntregaLinea(BaseModel):
    detalle_id: int
    cantidad_entregada: int


class PedidoEntregaRequest(BaseModel):
    lineas: list[PedidoEntregaLinea]
