from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrmSegmentoCriterio(BaseModel):
    """Simple AND-filter over Contacto attributes. Every field set must match."""

    tipo: str | None = None
    empresa_id: int | None = None
    rubro_id: int | None = None
    ciudad_id: int | None = None
    origen_id: int | None = None


class CrmSegmentoBase(BaseModel):
    nombre: str
    criterio: CrmSegmentoCriterio


class CrmSegmentoCreate(CrmSegmentoBase):
    pass


class CrmSegmentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    criterio: dict
    created_at: datetime
    updated_at: datetime


class CrmContactoSegmentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contacto_id: int
    segmento_id: int
    recalculado_en: datetime
