from pydantic import BaseModel, ConfigDict


class UbicacionCreate(BaseModel):
    nombre: str


class UbicacionUpdate(BaseModel):
    nombre: str


class UbicacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
