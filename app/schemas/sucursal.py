from pydantic import BaseModel

from app.schemas.vocab import SucursalTipo


class SucursalCreate(BaseModel):
    nombre: str
    tipo: SucursalTipo
    activa: bool = True


class SucursalUpdate(BaseModel):
    nombre: str | None = None
    tipo: SucursalTipo | None = None
    activa: bool | None = None


class SucursalRead(BaseModel):
    id: int
    nombre: str
    tipo: str
    activa: bool

    @classmethod
    def from_orm_row(cls, row) -> "SucursalRead":
        return cls(id=row.id, nombre=row.nombre, tipo=row.tipo, activa=row.activa)
