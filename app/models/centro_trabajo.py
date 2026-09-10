from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CentroTrabajo(Base):
    """Área de trabajo con tarifa horaria.

    Reemplaza al enum `responsable` como fuente del costo de mano de obra. Sin
    tarifa por centro no se puede costear el tiempo de operario sin máquina —el
    formado a mano—, que es justamente donde está la diferencia entre el francés
    y el pebete (design.md D14).
    """

    __tablename__ = "costos_centro_trabajo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50))
    tarifa_hora: Mapped[float] = mapped_column(Float, default=0)
    horas_turno: Mapped[float] = mapped_column(Float, default=6)
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True)
