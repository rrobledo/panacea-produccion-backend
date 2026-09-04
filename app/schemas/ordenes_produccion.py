from datetime import date, datetime

from pydantic import BaseModel, model_validator

from app.schemas.productos import ProductoRead
from app.schemas.ubicacion import UbicacionRead


class OrdenProduccionProductoLineaRead(BaseModel):
    id: int
    producto_id: int
    cantidad_planeada: int
    producto: ProductoRead | None

    @classmethod
    def from_orm_row(cls, row) -> "OrdenProduccionProductoLineaRead":
        return cls(
            id=row.id,
            producto_id=row.producto_id,
            cantidad_planeada=row.cantidad_planeada,
            producto=ProductoRead.model_validate(row.producto) if row.producto else None,
        )


class OrdenProduccionInsumoLineaRead(BaseModel):
    id: int
    insumo_id: int
    cantidad: float
    insumo_nombre: str
    insumo_unidad_medida: str

    @classmethod
    def from_orm_row(cls, row) -> "OrdenProduccionInsumoLineaRead":
        return cls(
            id=row.id,
            insumo_id=row.insumo_id,
            cantidad=row.cantidad,
            insumo_nombre=row.insumo.nombre,
            insumo_unidad_medida=row.insumo.unidad_medida,
        )


class OrdenProduccionRead(BaseModel):
    id: int
    codigo: str
    fecha_fabricacion: date
    responsable: str
    estado: str
    fecha_creacion: datetime
    fecha_en_produccion: datetime | None
    fecha_finalizada: datetime | None
    fecha_cancelada: datetime | None
    productos: list[OrdenProduccionProductoLineaRead]
    insumos: list[OrdenProduccionInsumoLineaRead]

    @classmethod
    def from_orm_row(cls, row) -> "OrdenProduccionRead":
        return cls(
            id=row.id,
            codigo=row.codigo,
            fecha_fabricacion=row.fecha_fabricacion,
            responsable=row.responsable,
            estado=row.estado,
            fecha_creacion=row.fecha_creacion,
            fecha_en_produccion=row.fecha_en_produccion,
            fecha_finalizada=row.fecha_finalizada,
            fecha_cancelada=row.fecha_cancelada,
            productos=[OrdenProduccionProductoLineaRead.from_orm_row(p) for p in row.productos],
            insumos=[OrdenProduccionInsumoLineaRead.from_orm_row(i) for i in row.insumos],
        )


class GenerarOrdenesRequest(BaseModel):
    fecha: date


class FinalizarLineaRequest(BaseModel):
    producto_id: int
    cantidad_fabricada: float
    ubicacion_id: int
    cantidad_desperdicio: float = 0
    ubicacion_desperdicio_id: int | None = None
    motivo_desperdicio: str | None = None

    @model_validator(mode="after")
    def _validate_desperdicio(self):
        if self.cantidad_desperdicio > 0:
            if self.ubicacion_desperdicio_id is None:
                raise ValueError("ubicacion_desperdicio_id is required when cantidad_desperdicio > 0")
            if not self.motivo_desperdicio:
                raise ValueError("motivo_desperdicio is required when cantidad_desperdicio > 0")
        return self


class FinalizarOrdenRequest(BaseModel):
    lineas: list[FinalizarLineaRequest]


class ProductoFabricadoRead(BaseModel):
    id: int
    orden_id: int
    orden_codigo: str
    producto_id: int
    producto: ProductoRead | None
    cantidad_fabricada: float
    ubicacion: UbicacionRead
    cantidad_desperdicio: float
    ubicacion_desperdicio: UbicacionRead | None
    motivo_desperdicio: str | None
    fecha: datetime

    @classmethod
    def from_orm_row(cls, row) -> "ProductoFabricadoRead":
        return cls(
            id=row.id,
            orden_id=row.orden_id,
            orden_codigo=row.orden.codigo,
            producto_id=row.producto_id,
            producto=ProductoRead.model_validate(row.producto) if row.producto else None,
            cantidad_fabricada=row.cantidad_fabricada,
            ubicacion=UbicacionRead.model_validate(row.ubicacion),
            cantidad_desperdicio=row.cantidad_desperdicio,
            ubicacion_desperdicio=UbicacionRead.model_validate(row.ubicacion_desperdicio)
            if row.ubicacion_desperdicio
            else None,
            motivo_desperdicio=row.motivo_desperdicio,
            fecha=row.fecha,
        )
