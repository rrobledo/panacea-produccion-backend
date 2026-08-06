from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CrmCampanaBase(BaseModel):
    nombre: str
    fecha_inicio: date
    fecha_fin: date | None = None
    objetivo: str | None = None
    costo: float | None = None


class CrmCampanaCreate(CrmCampanaBase):
    pass


class CrmCampanaUpdate(CrmCampanaBase):
    pass


class CrmCampanaRead(CrmCampanaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CrmCampanaConversion(BaseModel):
    campana_id: int
    contactos_asociados: int
    contactos_con_erp: int


class CrmContactoCampanaCreate(BaseModel):
    contacto_id: int


class CrmContactoCampanaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contacto_id: int
    campana_id: int
    fecha_asociacion: datetime
