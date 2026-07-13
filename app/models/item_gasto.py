from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ItemGasto(Base):
    __tablename__ = "compras_item_gasto"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str | None] = mapped_column(String(50), default=None)
    nombre: Mapped[str] = mapped_column(String(250))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
