from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.procesos import ROLES_LINEA, TIPOS_PROCESO
from app.schemas.maquinaria import ProcesoOperacionRead, ProcesoOperacionWrite


class ProcesoLineaBase(BaseModel):
    rol: str
    insumo_id: int | None = None
    producto_id: int | None = None
    cantidad: float
    unidad: str | None = None
    gramaje_g: float | None = None
    porcentaje_panadero: float | None = None
    merma_pct: float = 0
    rendimiento_pct: float = 100
    minutos_directos: int = 0
    minutos_maquina: int = 0
    criterio_reparto: str = "PESO"
    orden: int = 0


class ProcesoLineaWrite(ProcesoLineaBase):
    pass


class ProcesoLineaRead(ProcesoLineaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    insumo_nombre: str | None = None
    producto_nombre: str | None = None

    @classmethod
    def from_orm_row(cls, row) -> "ProcesoLineaRead":
        return cls(
            id=row.id,
            rol=row.rol,
            insumo_id=row.insumo_id,
            producto_id=row.producto_id,
            cantidad=row.cantidad,
            unidad=row.unidad,
            gramaje_g=row.gramaje_g,
            porcentaje_panadero=row.porcentaje_panadero,
            merma_pct=row.merma_pct,
            rendimiento_pct=row.rendimiento_pct,
            minutos_directos=row.minutos_directos,
            minutos_maquina=row.minutos_maquina,
            criterio_reparto=row.criterio_reparto,
            orden=row.orden,
            insumo_nombre=row.insumo.nombre if row.insumo else None,
            producto_nombre=row.producto.nombre if row.producto else None,
        )


class ProcesoBase(BaseModel):
    codigo: str
    nombre: str
    tipo: str
    responsable: str = "Todos"
    lote_referencia: float
    lote_unidad: str = "KG"
    lote_minimo: float | None = None
    lote_multiplo: float | None = None
    minutos_setup: int = 0


class ProcesoWrite(ProcesoBase):
    lineas: list[ProcesoLineaWrite] = []
    # Las etapas por las que pasa el proceso, cada una apuntando a un TIPO de
    # máquina. Se mandan junto con el proceso: son parte de la receta.
    operaciones: list["ProcesoOperacionWrite"] = []


class ProcesoRead(ProcesoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    vigente_desde: date
    vigente_hasta: date | None = None
    lineas: list[ProcesoLineaRead] = []
    operaciones: list["ProcesoOperacionRead"] = []
    # Lo que no bloquea el guardado pero conviene que el usuario vea: ramas que
    # no suman el lote, salidas sin gramaje, procesos sin entrada.
    advertencias: list[str] = []

    @classmethod
    def from_orm_row(cls, row, advertencias: list[str] | None = None, operaciones=None) -> "ProcesoRead":
        return cls(
            id=row.id,
            codigo=row.codigo,
            version=row.version,
            nombre=row.nombre,
            tipo=row.tipo,
            responsable=row.responsable,
            lote_referencia=row.lote_referencia,
            lote_unidad=row.lote_unidad,
            lote_minimo=row.lote_minimo,
            lote_multiplo=row.lote_multiplo,
            minutos_setup=row.minutos_setup,
            vigente_desde=row.vigente_desde,
            vigente_hasta=row.vigente_hasta,
            lineas=[ProcesoLineaRead.from_orm_row(linea) for linea in row.lineas],
            operaciones=[ProcesoOperacionRead.model_validate(o) for o in operaciones or []],
            advertencias=advertencias or [],
        )


TIPOS_VALIDOS = set(TIPOS_PROCESO)
ROLES_VALIDOS = set(ROLES_LINEA)
