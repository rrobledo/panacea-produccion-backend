from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Planificacion(Base):
    __tablename__ = "costos_planificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date | None] = mapped_column(Date, default=None)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("costos_productos.id"), default=None)
    plan: Mapped[int | None] = mapped_column(Integer, default=None)
    sistema: Mapped[int | None] = mapped_column(Integer, default=None)
    corregido: Mapped[int | None] = mapped_column(Integer, default=None)
    indice: Mapped[float | None] = mapped_column(Float, default=None)
