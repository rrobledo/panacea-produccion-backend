from datetime import date

from pydantic import BaseModel, ConfigDict

from app.schemas.vocab import OrdenCompraEstado


class OrdenCompraDetalleCreate(BaseModel):
    descripcion: str | None = None
    insumo_id: int | None = None
    cantidad_pedida: float
    precio_unitario_estimado: float | None = None


class OrdenCompraDetalleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    descripcion: str | None
    insumo_id: int | None
    cantidad_pedida: float
    cantidad_recibida: float
    precio_unitario_estimado: float | None


class OrdenCompraBase(BaseModel):
    proveedor_id: int
    fecha: date
    fecha_entrega_estimada: date | None = None
    observaciones: str | None = None


class OrdenCompraCreate(OrdenCompraBase):
    detalle: list[OrdenCompraDetalleCreate]


class OrdenCompraUpdate(OrdenCompraBase):
    pass


class OrdenCompraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    proveedor_nombre: str
    fecha: date
    fecha_entrega_estimada: date | None
    observaciones: str | None
    estado: OrdenCompraEstado


class OrdenCompraDetailRead(OrdenCompraRead):
    detalle: list[OrdenCompraDetalleRead]
