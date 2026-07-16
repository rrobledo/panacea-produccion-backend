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
    idcliente: int
    nom1: str | None
    nom2: str | None
    cuit: str | None
    direccion: str | None
    localidad: str | None
    provincia: str | None
    tel1: str | None
    celular: str | None
    email1: str | None
    personacontacto: str | None
    activo: int | None

    @classmethod
    def from_orm_row(cls, row) -> "ClienteRead":
        return cls(
            idcliente=row.id,
            nom1=row.nom1,
            nom2=row.nom2,
            cuit=row.cuit,
            direccion=row.direccion,
            localidad=row.localidad,
            provincia=row.provincia,
            tel1=row.tel1,
            celular=row.celular,
            email1=row.email1,
            personacontacto=row.personacontacto,
            activo=row.activo,
        )
