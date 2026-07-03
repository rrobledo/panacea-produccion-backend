from pydantic import BaseModel, ConfigDict


class ProductoBase(BaseModel):
    codigo: str
    categoria: str = "PANADERIA"
    nombre: str
    ref_id: str | None = None
    utilidad: float
    precio_actual: float
    unidad_medida: str = "GR"
    lote_produccion: int
    tiempo_produccion: int = 0
    responsable: str = "Todos"
    is_producto: bool = True
    habilitado: bool = True
    prioridad: int = 10


class ProductoCreate(ProductoBase):
    pass


class ProductoRead(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class CostoCreate(BaseModel):
    insumo: int
    cantidad: int


class CostoRead(BaseModel):
    id: int
    producto: int
    insumo: int
    insumo_nombre: str
    insumo_unidad_medida: str
    cantidad: int

    @classmethod
    def from_orm_row(cls, row) -> "CostoRead":
        return cls(
            id=row.id,
            producto=row.producto_id,
            insumo=row.insumo_id,
            insumo_nombre=row.insumo.nombre,
            insumo_unidad_medida=row.insumo.unidad_medida,
            cantidad=row.cantidad,
        )
