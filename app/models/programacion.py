from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Programacion(Base):
    __tablename__ = "costos_programacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date | None] = mapped_column(Date, default=None)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("costos_productos.id"), default=None)
    producto_nombre: Mapped[str | None] = mapped_column(String(255), default=None)
    responsable: Mapped[str] = mapped_column(String(50))
    plan: Mapped[int | None] = mapped_column(Integer, default=None)
    prod: Mapped[int | None] = mapped_column(Integer, default=None)
