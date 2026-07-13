from pydantic import BaseModel, ConfigDict


class ItemGastoBase(BaseModel):
    codigo: str | None = None
    nombre: str
    activo: bool = True


class ItemGastoCreate(ItemGastoBase):
    pass


class ItemGastoRead(ItemGastoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
