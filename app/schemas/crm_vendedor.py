from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrmVendedorBase(BaseModel):
    nombre: str
    user_id: int | None = None


class CrmVendedorCreate(CrmVendedorBase):
    pass


class CrmVendedorUpdate(CrmVendedorBase):
    pass


class CrmVendedorRead(CrmVendedorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
