from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.vocab import (
    CompraDetalleTipo,
    CompraEstado,
    CompraImpuestoTipo,
    CondicionPago,
    TipoComprobante,
)

COMPRA_IMPUESTO_TIPOS: set[str] = {
    "IVA_21",
    "IVA_10_5",
    "IVA_27",
    "PERCEPCION_IVA",
    "PERCEPCION_IIBB",
    "PERCEPCION_MUNICIPAL",
    "RETENCION_IVA",
    "RETENCION_GANANCIAS",
    "RETENCION_SUSS",
    "IMPUESTOS_INTERNOS",
    "HISTORICO_SIN_DESGLOSE",
}


class CompraDetalleCreate(BaseModel):
    tipo: CompraDetalleTipo = "LIBRE"
    # Required when tipo=LIBRE; when tipo=INSUMO/ITEM_GASTO it's an optional
    # override — the service snapshots the catalog's nombre if omitted, so
    # the line keeps a stable label even if the catalog entry is renamed
    # later.
    descripcion: str | None = None
    insumo_id: int | None = None
    item_gasto_id: int | None = None
    cantidad: float = 1
    precio_unitario: float
    descuento: float = 0
    alicuota_iva: float = 0
    centro_costo_id: int | None = None
    cuenta_contable_id: int | None = None

    @model_validator(mode="after")
    def _validate_referencia(self) -> "CompraDetalleCreate":
        if self.tipo == "INSUMO":
            if self.insumo_id is None:
                raise ValueError("insumo_id is required when tipo=INSUMO")
            if self.item_gasto_id is not None:
                raise ValueError("item_gasto_id must be null when tipo=INSUMO")
        elif self.tipo == "ITEM_GASTO":
            if self.item_gasto_id is None:
                raise ValueError("item_gasto_id is required when tipo=ITEM_GASTO")
            if self.insumo_id is not None:
                raise ValueError("insumo_id must be null when tipo=ITEM_GASTO")
        else:  # LIBRE
            if self.insumo_id is not None or self.item_gasto_id is not None:
                raise ValueError("insumo_id/item_gasto_id must be null when tipo=LIBRE")
            if not self.descripcion:
                raise ValueError("descripcion is required when tipo=LIBRE")
        return self


class CompraDetalleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    insumo_id: int | None
    item_gasto_id: int | None
    descripcion: str
    cantidad: float
    precio_unitario: float
    descuento: float
    alicuota_iva: float
    importe_neto: float
    importe_iva: float
    importe_total: float
    centro_costo_id: int | None
    cuenta_contable_id: int | None


class CompraImpuestoCreate(BaseModel):
    tipo: CompraImpuestoTipo
    base_imponible: float = 0
    porcentaje: float | None = None
    importe: float

    @field_validator("tipo")
    @classmethod
    def _validate_tipo(cls, value: str) -> str:
        if value not in COMPRA_IMPUESTO_TIPOS:
            raise ValueError(f"tipo must be one of {sorted(COMPRA_IMPUESTO_TIPOS)}")
        return value


class CompraImpuestoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    base_imponible: float
    porcentaje: float | None
    importe: float


class CompraAdjuntoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    tipo: str | None
    fecha: datetime


class CompraBase(BaseModel):
    proveedor_id: int
    tipo_comprobante: TipoComprobante
    punto_venta: str | None = None
    numero: str
    fecha: date
    fecha_vencimiento: date | None = None
    # None => defaulted from the proveedor's condicion_pago by the service.
    condicion_pago: CondicionPago | None = None
    observaciones: str | None = None
    orden_compra_id: int | None = None


class CompraCreate(CompraBase):
    detalle: list[CompraDetalleCreate] = []
    impuestos: list[CompraImpuestoCreate] = []


class CompraUpdate(CompraBase):
    pass


class CompraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    proveedor_nombre: str
    orden_compra_id: int | None
    tipo_comprobante: str
    punto_venta: str | None
    numero: str
    fecha: date
    fecha_vencimiento: date | None
    condicion_pago: str
    observaciones: str | None
    subtotal: float
    iva: float
    percepciones: float
    impuestos: float
    total: float
    saldo_pendiente: float
    estado: CompraEstado
    created_at: datetime


class CompraDetailRead(CompraRead):
    detalle: list[CompraDetalleRead]
    impuestos_detalle: list[CompraImpuestoRead]
    adjuntos: list[CompraAdjuntoRead]
