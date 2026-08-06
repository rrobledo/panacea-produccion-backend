from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CrmOportunidadCreate(BaseModel):
    contacto_id: int
    visita_id: int | None = None


class CrmOportunidadEtapaUpdate(BaseModel):
    etapa_nombre: str


class CrmOportunidadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contacto_id: int
    visita_id: int | None
    etapa_id: int
    etapa_nombre: str
    created_at: datetime
    updated_at: datetime


class CrmActividadCreate(BaseModel):
    tipo: str
    fecha: date
    notas: str | None = None


class CrmActividadRead(CrmActividadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    oportunidad_id: int
    created_at: datetime
