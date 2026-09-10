from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

TIPOS_MAQUINA = (
    "AMASADORA", "SOBADORA", "DIVISORA", "LAMINADORA", "BATIDORA", "CAMARA", "HORNO", "MESA",
)
UNIDADES_CAPACIDAD = ("KG", "LITROS", "KG_HORA", "CARROS", "BANDEJAS")
# La unidad de capacidad decide el modo de ocupación: contar horas exclusivas o
# contar cuántos caben a la vez (design.md D11).
UNIDADES_EXCLUSIVAS = ("KG", "LITROS", "KG_HORA")
UNIDADES_CONCURRENTES = ("CARROS", "BANDEJAS")
ESTADOS_MAQUINA = ("ACTIVA", "MANTENIMIENTO", "BAJA")


class Maquina(Base):
    __tablename__ = "maquinaria_maquina"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50))
    nombre: Mapped[str] = mapped_column(String(250))
    tipo: Mapped[str] = mapped_column(String(30))
    capacidad: Mapped[float] = mapped_column(Float)
    capacidad_unidad: Mapped[str] = mapped_column(String(20))
    minutos_setup: Mapped[int] = mapped_column(Integer, default=0)
    minutos_limpieza: Mapped[int] = mapped_column(Integer, default=0)
    tarifa_hora: Mapped[float] = mapped_column(Float, default=0)
    area: Mapped[str] = mapped_column(String(50), default="Todos")
    estado: Mapped[str] = mapped_column(String(20), default="ACTIVA")
    turno_desde: Mapped[str | None] = mapped_column(String(5), default=None)
    turno_hasta: Mapped[str | None] = mapped_column(String(5), default=None)

    @property
    def es_concurrente(self) -> bool:
        return self.capacidad_unidad in UNIDADES_CONCURRENTES


class ProcesoOperacion(Base):
    __tablename__ = "procesos_proceso_operacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    proceso_id: Mapped[int] = mapped_column(ForeignKey("procesos_proceso.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    nombre: Mapped[str] = mapped_column(String(250))
    # El TIPO requerido, nunca una máquina concreta: así sacar una máquina de
    # circulación es cambiar su estado, no editar recetas (design.md D10).
    maquina_tipo: Mapped[str] = mapped_column(String(30))
    capacidad_minima: Mapped[float | None] = mapped_column(Float, default=None)
    minutos_por_bacha: Mapped[int] = mapped_column(Integer, default=0)
    minutos_por_unidad: Mapped[float] = mapped_column(Float, default=0)
    requiere_operario: Mapped[bool] = mapped_column(Boolean, default=True)
    puede_solapar: Mapped[bool] = mapped_column(Boolean, default=False)

    proceso = relationship("Proceso", lazy="joined")


class OrdenOperacion(Base):
    __tablename__ = "ordenes_produccion_operacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes_produccion.id", ondelete="CASCADE"))
    proceso_operacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("procesos_proceso_operacion.id"), default=None
    )
    nombre: Mapped[str] = mapped_column(String(250), default="")
    maquina_tipo: Mapped[str] = mapped_column(String(30), default="")
    # None = ninguna máquina activa satisface la operación. La orden se emite
    # igual y esto queda como la señal de que hay que resolverlo a mano.
    maquina_id: Mapped[int | None] = mapped_column(ForeignKey("maquinaria_maquina.id"), default=None)
    bachas: Mapped[int] = mapped_column(Integer, default=1)
    minutos: Mapped[int] = mapped_column(Integer, default=0)
    requiere_operario: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    inicio_previsto: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fin_previsto: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    inicio_real: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fin_real: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE")

    maquina = relationship("Maquina", lazy="joined")
