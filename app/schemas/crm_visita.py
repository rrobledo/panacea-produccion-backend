from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CrmVisitaBase(BaseModel):
    contacto_id: int
    vendedor_id: int
    fecha: date
    notas: str | None = None
    resultado: str | None = None


class CrmVisitaCreate(CrmVisitaBase):
    pass


class CrmVisitaRead(CrmVisitaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
