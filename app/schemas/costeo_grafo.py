from datetime import date

from pydantic import BaseModel, ConfigDict


class CentroTrabajoBase(BaseModel):
    nombre: str
    tarifa_hora: float = 0
    horas_turno: float = 6
    habilitado: bool = True


class CentroTrabajoWrite(CentroTrabajoBase):
    pass


class CentroTrabajoRead(CentroTrabajoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class CostoDetalleRead(BaseModel):
    tipo: str
    nombre: str
    cantidad: float
    importe: float


class CostoArticuloRead(BaseModel):
    articulo_id: int
    nombre: str
    unidad_base: str
    costo_insumos: float
    costo_mano_obra: float
    costo_maquina: float
    costo_total: float
    cantidad_buena: float
    costo_unitario: float
    detalle: list[CostoDetalleRead] = []
    pendientes: list[str] = []

    @classmethod
    def from_costo(cls, costo) -> "CostoArticuloRead":
        return cls(
            articulo_id=costo.articulo_id,
            nombre=costo.nombre,
            unidad_base=costo.unidad_base,
            costo_insumos=round(costo.costo_insumos, 2),
            costo_mano_obra=round(costo.costo_mano_obra, 2),
            costo_maquina=round(costo.costo_maquina, 2),
            costo_total=round(costo.costo_total, 2),
            cantidad_buena=round(costo.cantidad_buena, 3),
            costo_unitario=round(costo.costo_unitario, 4),
            detalle=[CostoDetalleRead(**d) for d in costo.detalle],
            pendientes=costo.pendientes,
        )


class DesvioMermaRead(BaseModel):
    producto_id: int
    producto_nombre: str
    fecha: date
    cantidad_fabricada: float
    cantidad_desperdicio: float
    merma_real_pct: float
    merma_declarada_pct: float
    desvio_pct: float
