from typing import Literal

from pydantic import BaseModel

Sucursal = Literal["VA", "CP", "CBA"]
EstadoReferencia = Literal["pendiente", "vinculado"]


class RelacionArticuloRead(BaseModel):
    id: int
    producto_id: int
    producto_nombre: str | None
    unidad_conversion: int


class ArticuloReferenciaRead(BaseModel):
    idarticulo: int
    nombre: str | None
    categoria: str | None
    sucursal: Sucursal
    precio: float | None
    estado: EstadoReferencia
    relaciones: list[RelacionArticuloRead] = []


class ResumenReferencias(BaseModel):
    # Sólo respeta el filtro de sucursal: es el avance de la vinculación, no un
    # conteo del listado, y no debería moverse mientras el usuario busca.
    total: int
    vinculados: int
    pendientes: int


class ReferenciasArticulosRead(BaseModel):
    resumen: ResumenReferencias
    items: list[ArticuloReferenciaRead]


class RelacionArticuloWrite(BaseModel):
    producto_id: int
    # Unidades del producto fabricado por cada unidad del artículo vendida: es
    # lo que `panacea_sales_v2` multiplica por `count`. En una promo de seis
    # medialunas vale 6.
    # Se valida (>= 1) en el servicio para responder 422 como el resto de los
    # errores de la relación; la validación de pydantic acá sale como 400.
    unidad_conversion: int


class ReferenciasArticuloWrite(BaseModel):
    relaciones: list[RelacionArticuloWrite]
