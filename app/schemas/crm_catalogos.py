from pydantic import BaseModel, ConfigDict


class CrmCatalogoBase(BaseModel):
    nombre: str


class CrmCatalogoCreate(CrmCatalogoBase):
    pass


class CrmCatalogoRead(CrmCatalogoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
