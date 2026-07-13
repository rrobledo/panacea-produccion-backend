"""Shared vocabularies for the Compras/Tesorería/Proveedores domain.

Kept as app-level Literal validation rather than DB constraints or
separate lookup tables — see
openspec/changes/redesign-cuenta-corriente-proveedor/design.md (D3/D4):
adding a new value is a vocabulary edit here, not a migration.
"""

from typing import Literal

CondicionIva = Literal["RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO", "CONSUMIDOR_FINAL"]
CONDICION_IVA_VALUES: set[str] = {"RESPONSABLE_INSCRIPTO", "MONOTRIBUTO", "EXENTO", "CONSUMIDOR_FINAL"}

CondicionPago = Literal["CONTADO", "CUENTA_CORRIENTE"]

TipoComprobante = Literal[
    "FACTURA_A", "FACTURA_B", "FACTURA_C", "FACTURA_M", "NOTA_CREDITO", "NOTA_DEBITO", "TICKET", "GASTO"
]

CompraImpuestoTipo = Literal[
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
]

PagoMedioTipo = Literal["TRANSFERENCIA", "CHEQUE", "ECHEQ", "EFECTIVO", "TARJETA"]
CHEQUE_LIKE_MEDIOS: set[str] = {"CHEQUE", "ECHEQ"}

CompraDetalleTipo = Literal["INSUMO", "ITEM_GASTO", "LIBRE"]

CompraEstado = Literal["PENDIENTE", "PARCIAL", "PAGADO"]
OrdenCompraEstado = Literal["PENDIENTE", "PARCIAL", "RECIBIDA", "CERRADA", "CANCELADA"]
MovimientoCCTipo = Literal["FACTURA", "PAGO", "NOTA_CREDITO", "NOTA_DEBITO"]
