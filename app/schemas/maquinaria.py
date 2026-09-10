from datetime import date

from pydantic import BaseModel, ConfigDict


class MaquinaBase(BaseModel):
    codigo: str
    nombre: str
    tipo: str
    capacidad: float
    capacidad_unidad: str
    minutos_setup: int = 0
    minutos_limpieza: int = 0
    tarifa_hora: float = 0
    area: str = "Todos"
    estado: str = "ACTIVA"
    turno_desde: str | None = None
    turno_hasta: str | None = None


class MaquinaWrite(MaquinaBase):
    pass


class MaquinaRead(MaquinaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ProcesoOperacionBase(BaseModel):
    orden: int = 0
    nombre: str
    maquina_tipo: str
    capacidad_minima: float | None = None
    minutos_por_bacha: int = 0
    minutos_por_unidad: float = 0
    requiere_operario: bool = True
    puede_solapar: bool = False


class ProcesoOperacionWrite(ProcesoOperacionBase):
    pass


class ProcesoOperacionRead(ProcesoOperacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proceso_id: int


class OrdenOperacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    maquina_tipo: str
    maquina_id: int | None = None
    maquina_nombre: str | None = None
    bachas: int
    minutos: int
    requiere_operario: bool
    orden: int
    estado: str

    @classmethod
    def from_orm_row(cls, row) -> "OrdenOperacionRead":
        return cls(
            id=row.id,
            nombre=row.nombre,
            maquina_tipo=row.maquina_tipo,
            maquina_id=row.maquina_id,
            maquina_nombre=row.maquina.nombre if row.maquina else None,
            bachas=row.bachas,
            minutos=row.minutos,
            requiere_operario=row.requiere_operario,
            orden=row.orden,
            estado=row.estado,
        )


class CargaFilaRead(BaseModel):
    tipo: str
    maquinas: int
    concurrente: bool
    capacidad_horas: float
    requerido_horas: float
    uso: float
    estado: str


class CargaDiaRead(BaseModel):
    fecha: date
    filas: list[CargaFilaRead]
    sobrecapacidad: list[CargaFilaRead]
