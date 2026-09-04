from pydantic import BaseModel, ConfigDict


class InsumoBase(BaseModel):
    nombre: str
    unidad_medida: str = "GR"
    precio: float


class InsumoCreate(InsumoBase):
    # Cantidad de apertura del insumo nuevo — sigue siendo editable solo en
    # la creación (ver design.md Decision 3); a partir de ahí se calcula
    # desde stock_movimientos.
    cantidad: float


class InsumoUpdate(InsumoBase):
    pass


class InsumoRead(InsumoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cantidad: float
    comprometido: float = 0
    disponible: float = 0

    @classmethod
    def from_orm_row(cls, row, comprometido: float = 0) -> "InsumoRead":
        return cls(
            id=row.id,
            nombre=row.nombre,
            unidad_medida=row.unidad_medida,
            cantidad=row.cantidad,
            precio=row.precio,
            comprometido=comprometido,
            disponible=row.cantidad - comprometido,
        )
