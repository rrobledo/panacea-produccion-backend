from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Insumos(Base):
    __tablename__ = "costos_insumos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), default="")
    nombre: Mapped[str] = mapped_column(String(250))
    unidad_medida: Mapped[str] = mapped_column(String(10), default="GR")
    cantidad: Mapped[float] = mapped_column(Float)
    precio: Mapped[float] = mapped_column(Float)
