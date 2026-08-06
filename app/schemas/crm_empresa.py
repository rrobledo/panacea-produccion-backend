from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrmEmpresaBase(BaseModel):
    nombre: str
    cuit: str | None = None


class CrmEmpresaCreate(CrmEmpresaBase):
    pass


class CrmEmpresaUpdate(CrmEmpresaBase):
    pass


class CrmEmpresaRead(CrmEmpresaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
