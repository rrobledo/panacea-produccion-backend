from pydantic import BaseModel

from app.schemas.pedido import PedidoRead


class PedidosPendientesPorDia(BaseModel):
    fecha: str
    total_pedidos: int
    total_pendientes: int
    total_en_preparacion: int
    total_listo_para_entrega: int
    total_entregados: int
    total_cancelados: int
    pedidos: list[PedidoRead]


class ProductoPendienteItem(BaseModel):
    producto: str
    cantidad: int


class ResponsableProductosPendientes(BaseModel):
    responsable: str
    productos: list[ProductoPendienteItem]


class ProductosPendientesPorDia(BaseModel):
    fecha: str
    responsables: list[ResponsableProductosPendientes]
