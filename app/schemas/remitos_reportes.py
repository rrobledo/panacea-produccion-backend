from pydantic import BaseModel

from app.schemas.remitos import RemitoRead


class RemitosPendientesPorDia(BaseModel):
    fecha: str
    total_remitos: int
    total_pendientes: int
    total_en_preparacion: int
    total_listo_para_entrega: int
    total_en_camino: int
    total_entregados: int
    remitos: list[RemitoRead]


class ProductoPendienteItem(BaseModel):
    producto: str
    cantidad: int


class ResponsableProductosPendientes(BaseModel):
    responsable: str
    productos: list[ProductoPendienteItem]


class ProductosPendientesPorDia(BaseModel):
    fecha: str
    responsables: list[ResponsableProductosPendientes]
