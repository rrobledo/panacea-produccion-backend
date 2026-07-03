from pydantic import BaseModel


class ClienteCreate(BaseModel):
    # The reference Django serializer only exposes a read-only computed
    # `nombre` for this managed=False legacy table — no field actually lets
    # a caller set nom1/nom2, making its POST/PUT effectively a no-op.
    # Exposing nom1/nom2 directly here instead, since a write endpoint that
    # can't write anything isn't a feature worth porting literally.
    nom1: str | None = None
    nom2: str | None = None


class ClienteRead(BaseModel):
    id: int
    nombre: str

    @classmethod
    def from_orm_row(cls, row) -> "ClienteRead":
        return cls(id=row.id, nombre=f"{row.nom1}, {row.nom2}")
