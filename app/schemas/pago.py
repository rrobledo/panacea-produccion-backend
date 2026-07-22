from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.vocab import CHEQUE_LIKE_MEDIOS, PagoMedioTipo


class PagoMedioCreate(BaseModel):
    tipo: PagoMedioTipo
    importe: float
    banco: str | None = None
    numero: str | None = None
    fecha_acreditacion: date | None = None

    @model_validator(mode="after")
    def _validate_cheque_fields(self) -> "PagoMedioCreate":
        if self.tipo in CHEQUE_LIKE_MEDIOS and (not self.banco or not self.numero or not self.fecha_acreditacion):
            raise ValueError("banco, numero, and fecha_acreditacion are required when tipo is CHEQUE or ECHEQ")
        return self


class PagoMedioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    importe: float
    banco: str | None
    numero: str | None
    fecha_acreditacion: date | None


class PagoAplicacionCreate(BaseModel):
    compra_id: int
    importe: float


class PagoAplicacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pago_id: int
    compra_id: int
    importe: float
    comprobante: str


class PagoBase(BaseModel):
    proveedor_id: int
    fecha: date
    importe: float
    observaciones: str | None = None


class PagoCreate(PagoBase):
    medios: list[PagoMedioCreate]

    @model_validator(mode="after")
    def _validate_medios(self) -> "PagoCreate":
        if not self.medios:
            raise ValueError("at least one medio is required")
        total = sum(m.importe for m in self.medios)
        if abs(total - self.importe) > 0.01:
            raise ValueError("importe must equal the sum of medios' importe")
        return self


class PagoUpdate(PagoBase):
    pass


class PagoAdjuntoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: str | None
    fecha: datetime


class PagoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    proveedor_nombre: str
    fecha: date
    importe: float
    estado: str
    observaciones: str | None
    created_at: datetime


class PagoDetailRead(PagoRead):
    medios: list[PagoMedioRead]
    adjuntos: list[PagoAdjuntoRead]
