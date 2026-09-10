"""Desvío entre la merma declarada en la fórmula y la registrada al finalizar.

Ver openspec/changes/masa-procesos-y-maquinaria/design.md D8 y
specs/procesos/spec.md. Hasta ahora sólo existía la registrada
(`cantidad_desperdicio`), que no dimensiona nada y ni siquiera afecta el costo.
Con las dos, el porcentaje esperado dimensiona la producción y el registrado
mide contra él.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ordenes_produccion import OrdenProduccion, ProductoFabricado
from app.models.procesos import ROLES_SALIDA, Proceso, ProcesoLinea
from app.models.productos import Productos


async def desvios(
    session: AsyncSession, fecha_desde: date | None = None, fecha_hasta: date | None = None
) -> list[dict]:
    stmt = (
        select(ProductoFabricado, OrdenProduccion, Productos)
        .join(OrdenProduccion, OrdenProduccion.id == ProductoFabricado.orden_id)
        .join(Productos, Productos.id == ProductoFabricado.producto_id)
        .where(OrdenProduccion.estado == "FINALIZADA")
    )
    if fecha_desde:
        stmt = stmt.where(OrdenProduccion.fecha_fabricacion >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(OrdenProduccion.fecha_fabricacion <= fecha_hasta)
    filas = (await session.execute(stmt.order_by(OrdenProduccion.fecha_fabricacion))).all()

    declaradas = {
        producto_id: float(merma or 0)
        for producto_id, merma in (
            await session.execute(
                select(ProcesoLinea.producto_id, ProcesoLinea.merma_pct)
                .join(Proceso, Proceso.id == ProcesoLinea.proceso_id)
                .where(ProcesoLinea.rol.in_(ROLES_SALIDA), Proceso.vigente_hasta.is_(None))
            )
        ).all()
    }

    resultado = []
    for fabricado, orden, producto in filas:
        total = float(fabricado.cantidad_fabricada or 0) + float(fabricado.cantidad_desperdicio or 0)
        if total <= 0:
            continue
        real = float(fabricado.cantidad_desperdicio or 0) / total * 100
        declarada = declaradas.get(producto.id, 0.0)
        resultado.append(
            {
                "producto_id": producto.id,
                "producto_nombre": producto.nombre,
                "fecha": orden.fecha_fabricacion,
                "cantidad_fabricada": float(fabricado.cantidad_fabricada or 0),
                "cantidad_desperdicio": float(fabricado.cantidad_desperdicio or 0),
                "merma_real_pct": round(real, 2),
                "merma_declarada_pct": round(declarada, 2),
                "desvio_pct": round(real - declarada, 2),
            }
        )
    return resultado
