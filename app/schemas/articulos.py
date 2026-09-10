from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MovimientoArticuloRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: datetime
    tipo: str
    cantidad: float
    referencia: str | None = None
    orden_id: int | None = None


class StockArticuloRead(BaseModel):
    producto_id: int
    producto_nombre: str
    naturaleza: str
    unidad_base: str
    # Saldo derivado del ledger, no un campo almacenado: no hay nada que
    # mantener sincronizado y por lo tanto nada que se pueda desincronizar.
    disponible: float
    # Cuánto de ese consumo viene de órdenes que todavía no arrancaron. Es 0
    # hasta que F4 conecte el consumo de semielaborados (tarea 5.4).
    comprometido: float
    movimientos: list[MovimientoArticuloRead] = []
