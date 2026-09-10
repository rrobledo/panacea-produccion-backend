from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# El grafo: un proceso toma N artículos y devuelve M artículos, y la salida de
# uno puede ser la entrada de otro. Ver
# openspec/changes/masa-procesos-y-maquinaria/design.md D2 en el repo
# `panacea-produccion`.

TIPOS_PROCESO = ("ELABORACION", "DIVISION", "TRANSFORMACION", "FRACCIONAMIENTO")
ROLES_LINEA = ("ENTRADA", "SALIDA", "COPRODUCTO", "RESIDUO")
ROLES_SALIDA = ("SALIDA", "COPRODUCTO")


class Proceso(Base):
    __tablename__ = "procesos_proceso"

    id: Mapped[int] = mapped_column(primary_key=True)
    # `codigo` es el identificador lógico y `version` la ordena: cada fila es
    # una versión, y `vigente_hasta IS NULL` marca la vigente (design.md D12).
    codigo: Mapped[str] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(Integer, default=1)
    nombre: Mapped[str] = mapped_column(String(250))
    tipo: Mapped[str] = mapped_column(String(20))
    responsable: Mapped[str] = mapped_column(String(50), default="Todos")
    lote_referencia: Mapped[float] = mapped_column(Float)
    lote_unidad: Mapped[str] = mapped_column(String(10), default="KG")
    lote_minimo: Mapped[float | None] = mapped_column(Float, default=None)
    lote_multiplo: Mapped[float | None] = mapped_column(Float, default=None)
    minutos_setup: Mapped[int] = mapped_column(Integer, default=0)
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, default=None)

    lineas: Mapped[list["ProcesoLinea"]] = relationship(
        back_populates="proceso", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProcesoLinea.orden, ProcesoLinea.id",
    )


class ProcesoLinea(Base):
    __tablename__ = "procesos_proceso_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    proceso_id: Mapped[int] = mapped_column(ForeignKey("procesos_proceso.id", ondelete="CASCADE"))
    rol: Mapped[str] = mapped_column(String(20))
    # Un artículo, en dos tablas: exactamente uno de los dos va cargado. El
    # CHECK de la migración 0028 impide que sea ninguno o los dos.
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("costos_insumos.id"), default=None)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("costos_productos.id"), default=None)
    cantidad: Mapped[float] = mapped_column(Float)
    unidad: Mapped[str | None] = mapped_column(String(10), default=None)
    # Peso del bollo crudo. Obligatorio en las salidas que se cuentan por
    # unidad: es lo que traduce kilos de masa en cantidad de bollos (D3).
    gramaje_g: Mapped[float | None] = mapped_column(Float, default=None)
    porcentaje_panadero: Mapped[float | None] = mapped_column(Float, default=None)
    merma_pct: Mapped[float] = mapped_column(Float, default=0)
    rendimiento_pct: Mapped[float] = mapped_column(Float, default=100)
    minutos_directos: Mapped[int] = mapped_column(Integer, default=0)
    minutos_maquina: Mapped[int] = mapped_column(Integer, default=0)
    criterio_reparto: Mapped[str] = mapped_column(String(10), default="PESO")
    orden: Mapped[int] = mapped_column(Integer, default=0)

    proceso: Mapped[Proceso] = relationship(back_populates="lineas")
    insumo = relationship("Insumos", lazy="joined")
    producto = relationship("Productos", lazy="joined")

    @property
    def es_salida(self) -> bool:
        return self.rol in ROLES_SALIDA
