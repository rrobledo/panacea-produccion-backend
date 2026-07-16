from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Clientes(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column("idcliente", primary_key=True)
    nom1: Mapped[str | None] = mapped_column(String)
    nom2: Mapped[str | None] = mapped_column(String)
    cuit: Mapped[str | None] = mapped_column(String)
    direccion: Mapped[str | None] = mapped_column(String)
    localidad: Mapped[str | None] = mapped_column(String)
    provincia: Mapped[str | None] = mapped_column(String)
    tel1: Mapped[str | None] = mapped_column(String)
    celular: Mapped[str | None] = mapped_column(String)
    email1: Mapped[str | None] = mapped_column(String)
    personacontacto: Mapped[str | None] = mapped_column(String)
    activo: Mapped[int | None] = mapped_column(Integer)
