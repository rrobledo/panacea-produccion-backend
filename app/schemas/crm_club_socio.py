from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CrmClubSocioLinkRequest(BaseModel):
    socio_id: str


class CrmClubSocioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contacto_id: int
    socio_id: str
    categoria: str | None
    puntos: int | None
    fecha_alta: date | None
    actualizado_en: datetime
