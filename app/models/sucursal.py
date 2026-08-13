from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Sucursal(Base):
    __tablename__ = "sucursales_sucursal"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str] = mapped_column(String(20))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
