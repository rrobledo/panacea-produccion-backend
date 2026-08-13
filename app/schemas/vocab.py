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

PagoMedioTipo = Literal["TRANSFERENCIA", "CHEQUE", "ECHEQ", "EFECTIVO", "TARJETA", "NOTA_CREDITO"]
CHEQUE_LIKE_MEDIOS: set[str] = {"CHEQUE", "ECHEQ"}

CompraDetalleTipo = Literal["INSUMO", "ITEM_GASTO", "LIBRE"]

CompraEstado = Literal["PENDIENTE", "PARCIAL", "PAGADO"]
OrdenCompraEstado = Literal["PENDIENTE", "PARCIAL", "RECIBIDA", "CERRADA", "CANCELADA"]
MovimientoCCTipo = Literal["FACTURA", "PAGO", "NOTA_CREDITO", "NOTA_DEBITO"]

ContactoTipo = Literal["B2B", "B2C"]

EtapaVentaNombre = Literal[
    "Lead",
    "Visita",
    "Interesado",
    "Muestras",
    "Presupuesto",
    "Negociacion",
    "Primera Compra",
    "Cliente Activo",
]
ETAPA_VENTA_ORDEN: list[str] = [
    "Lead",
    "Visita",
    "Interesado",
    "Muestras",
    "Presupuesto",
    "Negociacion",
    "Primera Compra",
    "Cliente Activo",
]

SucursalTipo = Literal["SUCURSAL", "FABRICA"]

PedidoEstado = Literal["PENDIENTE", "EN_PREPARACION", "PREPARADO", "LISTO_PARA_ENTREGA", "ENTREGADO", "CANCELADO"]
# Each non-CANCELADO estado's single valid next step (linear sequence, see
# openspec/changes/pedidos-y-remitos/specs/pedidos/spec.md).
PEDIDO_VALID_TRANSITIONS: dict[str, str] = {
    "PENDIENTE": "EN_PREPARACION",
    "EN_PREPARACION": "PREPARADO",
    "PREPARADO": "LISTO_PARA_ENTREGA",
    "LISTO_PARA_ENTREGA": "ENTREGADO",
}
# Historial de estados: campo de fecha que registra el momento en que se
# alcanzó cada estado (incluye CANCELADO, transición lateral aparte de la
# secuencia de arriba) — mismo propósito que REMITO_ESTADO_TIMESTAMP_FIELD.
PEDIDO_ESTADO_TIMESTAMP_FIELD: dict[str, str] = {
    "EN_PREPARACION": "fecha_en_preparacion",
    "PREPARADO": "fecha_preparado",
    "LISTO_PARA_ENTREGA": "fecha_listo_para_entrega",
    "ENTREGADO": "fecha_entregado",
    "CANCELADO": "fecha_cancelado",
}

RemitoTipo = Literal["VENTA", "TRANSFERENCIA"]

RemitoEstado = Literal["LISTO", "EN_TRANSITO", "RECIBIDO"]
# El remito nace en LISTO (fecha_listo se setea en el momento de creación,
# no hay más paso PENDIENTE/EN_PREPARACION previo — ver
# openspec/changes/pedidos-y-remitos/specs/remitos/spec.md).
REMITO_VALID_TRANSITIONS: dict[str, str] = {
    "LISTO": "EN_TRANSITO",
    "EN_TRANSITO": "RECIBIDO",
}
REMITO_ESTADO_TIMESTAMP_FIELD: dict[str, str] = {
    "EN_TRANSITO": "fecha_despacho",
    "RECIBIDO": "fecha_recibido",
}
