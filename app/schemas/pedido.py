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
    # En un remito directo (es_remito) es lo despachado, al crear y al
    # editar. En un pedido, solo la tiene en cuenta update_pedido al crear un
    # ítem nuevo durante una edición — un ítem agregado a un pedido ya creado
    # puede nacer ya entregado; create_pedido la ignora.
    cantidad_entregada: int = 0


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
    # Origen de una transferencia (tipo=SUCURSAL, sucursal_id es el destino).
    # Si no se informa, create_pedido asigna la única sucursal FABRICA.
    origen_sucursal_id: int | None = None

    @model_validator(mode="after")
    def _validate_tipo_fields(self):
        if self.tipo == "CLIENTE":
            if self.cliente_id is None:
                raise ValueError("cliente_id is required when tipo=CLIENTE")
            if self.sucursal_id is not None or self.origen_sucursal_id is not None:
                raise ValueError("sucursal_id/origen_sucursal_id must be null when tipo=CLIENTE")
        elif self.tipo == "SUCURSAL":
            if self.cliente_id is not None:
                raise ValueError("cliente_id must be null when tipo=SUCURSAL")
            if self.sucursal_id is None:
                raise ValueError("sucursal_id is required when tipo=SUCURSAL")
            if self.origen_sucursal_id is not None and self.origen_sucursal_id == self.sucursal_id:
                raise ValueError("origen_sucursal_id and sucursal_id must be different")
        return self


class PedidoCreate(_PedidoTipoFieldsMixin):
    vendedor: str
    observaciones: str | None = None
    fecha_entrega: datetime
    es_remito: bool = False
    detalles: list[PedidoDetalleCreate] = []

    @model_validator(mode="after")
    def _validate_remito_detalles(self):
        if self.es_remito:
            if any(d.cantidad_pedida != 0 for d in self.detalles):
                raise ValueError("cantidad_pedida must be 0 on every line when es_remito=true")
            if not any(d.cantidad_entregada > 0 for d in self.detalles):
                raise ValueError("a remito needs at least one line with cantidad_entregada > 0")
        return self


class PedidoUpdate(BaseModel):
    cliente_id: int | None = None
    vendedor: str | None = None
    observaciones: str | None = None
    fecha_entrega: datetime | None = None
    detalles: list[PedidoDetalleCreate] | None = None


class PedidoFacturacionRequest(BaseModel):
    """Las dos informadas marcan el envío como facturado; las dos nulas lo
    desmarcan."""

    fecha_facturado: datetime | None = None
    factura_referencia: str | None = None

    @model_validator(mode="after")
    def _validate_par(self):
        if self.factura_referencia is not None:
            self.factura_referencia = self.factura_referencia.strip() or None
        if (self.fecha_facturado is None) != (self.factura_referencia is None):
            raise ValueError("fecha_facturado and a non-empty factura_referencia go together (or both null)")
        if self.factura_referencia is not None and len(self.factura_referencia) > 100:
            raise ValueError("factura_referencia must be at most 100 characters")
        return self


class PedidoRead(BaseModel):
    id: int
    tipo: str
    es_remito: bool
    cliente_id: int | None
    cliente: ClienteRead | None
    sucursal_id: int | None
    sucursal: SucursalRead | None
    origen_sucursal_id: int | None
    origen_sucursal: SucursalRead | None
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
    fecha_facturado: datetime | None
    factura_referencia: str | None
    remitos_legacy_ids: list[int]
    detalles: list[PedidoDetalleRead]

    @classmethod
    def from_orm_row(cls, row) -> "PedidoRead":
        return cls(
            id=row.id,
            tipo=row.tipo,
            es_remito=row.es_remito,
            cliente_id=row.cliente_id,
            cliente=ClienteRead.from_orm_row(row.cliente) if row.cliente else None,
            sucursal_id=row.sucursal_id,
            sucursal=SucursalRead.from_orm_row(row.sucursal) if row.sucursal else None,
            origen_sucursal_id=row.origen_sucursal_id,
            origen_sucursal=SucursalRead.from_orm_row(row.origen_sucursal) if row.origen_sucursal else None,
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
            fecha_facturado=row.fecha_facturado,
            factura_referencia=row.factura_referencia,
            remitos_legacy_ids=sorted(r.remito_legacy_id for r in row.remitos_legacy),
            detalles=[PedidoDetalleRead.from_orm_row(d) for d in row.detalles],
        )


class EstadoTransitionRequest(BaseModel):
    nuevo_estado: str


class PedidoEntregaLinea(BaseModel):
    detalle_id: int
    cantidad_entregada: int


class PedidoEntregaRequest(BaseModel):
    lineas: list[PedidoEntregaLinea]
