from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StockMovimientoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    insumo_id: int
    tipo: str
    cantidad: float
    referencia: str | None
    fecha: datetime


class AjusteStockCreate(BaseModel):
    cantidad: float
    motivo: str
