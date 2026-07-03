from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Clientes(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column("idcliente", primary_key=True)
    nom1: Mapped[str | None] = mapped_column(String)
    nom2: Mapped[str | None] = mapped_column(String)
