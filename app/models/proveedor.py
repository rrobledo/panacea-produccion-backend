from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Proveedor(Base):
    __tablename__ = "costos_proveedor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255))
    cuit: Mapped[str] = mapped_column(String(20), unique=True)
    direccion: Mapped[str | None] = mapped_column(String(255), default=None)
    telefono: Mapped[str | None] = mapped_column(String(50), default=None)
    email: Mapped[str | None] = mapped_column(String(100), default=None)
    fecha_alta: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(10), default="activo")
