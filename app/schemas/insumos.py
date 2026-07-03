from pydantic import BaseModel, ConfigDict


class InsumoBase(BaseModel):
    nombre: str
    unidad_medida: str = "GR"
    cantidad: float
    precio: float


class InsumoCreate(InsumoBase):
    pass


class InsumoRead(InsumoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
