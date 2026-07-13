from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.vocab import CONDICION_IVA_VALUES, CondicionPago

EstadoProveedor = Literal["activo", "inactivo"]


class ProveedorBase(BaseModel):
    codigo: str | None = None
    nombre: str
    nombre_fantasia: str | None = None
    cuit: str
    condicion_iva: str | None = None
    condicion_pago: CondicionPago = "CUENTA_CORRIENTE"
    direccion: str | None = None
    telefono: str | None = None
    email: str | None = None

    @field_validator("condicion_iva")
    @classmethod
    def _validate_condicion_iva(cls, value: str | None) -> str | None:
        if value is not None and value not in CONDICION_IVA_VALUES:
            raise ValueError(f"condicion_iva must be one of {sorted(CONDICION_IVA_VALUES)}")
        return value


class ProveedorCreate(ProveedorBase):
    estado: EstadoProveedor = "activo"


class ProveedorUpdate(ProveedorBase):
    estado: EstadoProveedor = "activo"


class ProveedorRead(ProveedorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_alta: date
    estado: EstadoProveedor
