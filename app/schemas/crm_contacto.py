from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.vocab import ContactoTipo


class CrmContactoBase(BaseModel):
    tipo: ContactoTipo
    nombre: str
    email: str | None = None
    telefono: str | None = None
    empresa_id: int | None = None
    rubro_id: int | None = None
    ciudad_id: int | None = None
    origen_id: int | None = None
    erp_cliente_id: int | None = None
    observaciones: str | None = None


class CrmContactoCreate(CrmContactoBase):
    pass


class CrmContactoUpdate(CrmContactoBase):
    pass


class CrmErpLinkRequest(BaseModel):
    erp_cliente_id: int


class CrmContactoRead(CrmContactoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_nombre: str | None
    rubro_nombre: str | None
    ciudad_nombre: str | None
    origen_nombre: str | None
    created_at: datetime
    updated_at: datetime
