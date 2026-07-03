from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

EstadoProveedor = Literal["activo", "inactivo"]


class ProveedorBase(BaseModel):
    nombre: str
    cuit: str
    direccion: str | None = None
    telefono: str | None = None
    email: str | None = None


class ProveedorCreate(ProveedorBase):
    estado: EstadoProveedor = "activo"


class ProveedorUpdate(ProveedorBase):
    estado: EstadoProveedor = "activo"


class ProveedorRead(ProveedorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_alta: date
    estado: EstadoProveedor
