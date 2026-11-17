"""Vínculo entre los artículos de caja de las sucursales y los productos fabricados.

`articulos_final` es una vista de producción que une los artículos de los tres
sistemas de caja desplazando sus ids: Villa Allende tal cual, Carlos Paz + 2000
y Córdoba + 4000. El vínculo vive en `costos_productosref`, una fila por
producto: una promo tiene varias filas con el mismo `ref_id`.
"""

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.productos import Productos, ProductosRef
from app.schemas.referencias_articulos import RelacionArticuloWrite

# Una sola definición del rango de cada sucursal, usada en todas las consultas.
SUCURSAL_SQL = (
    "case when a.idarticulo < 2000 then 'VA' "
    "when a.idarticulo < 4000 then 'CP' else 'CBA' end"
)

# `ref_id` es texto libre. Las consultas viejas hacen `ref_id::int` directo, y
# con una sola fila sucia se cae la consulta entera. El CASE garantiza que el
# cast sólo se evalúe sobre texto numérico; lo demás queda en NULL y no se
# asocia a ningún artículo.
REF_IDARTICULO_SQL = (
    r"case when r.ref_id ~ '^\s*[0-9]{1,9}\s*$' then trim(r.ref_id)::int end"
)

_REFS_CTE = f"""
    refs as (
        select r.id, r.producto_id, r.unidad_conversion,
               {REF_IDARTICULO_SQL} as idarticulo
          from costos_productosref r
    )
"""


def _filtros_articulo(
    sucursal: str | None,
    categoria: str | None,
    q: str | None,
    idarticulo: int | None,
) -> tuple[list[str], dict]:
    where = ["a.activo = 1"]
    params: dict = {}
    if sucursal:
        where.append(f"{SUCURSAL_SQL} = :sucursal")
        params["sucursal"] = sucursal
    if categoria:
        where.append("a.categoria = :categoria")
        params["categoria"] = categoria
    if q:
        where.append("a.nombre ilike :q")
        params["q"] = f"%{q}%"
    if idarticulo is not None:
        where.append("a.idarticulo = :idarticulo")
        params["idarticulo"] = idarticulo
    return where, params


async def _items(
    session: AsyncSession,
    *,
    estado: str = "todos",
    sucursal: str | None = None,
    categoria: str | None = None,
    q: str | None = None,
    idarticulo: int | None = None,
) -> list[dict]:
    where, params = _filtros_articulo(sucursal, categoria, q, idarticulo)
    vinculado = "exists (select 1 from refs x where x.idarticulo = a.idarticulo)"
    if estado == "pendiente":
        where.append(f"not {vinculado}")
    elif estado == "vinculado":
        where.append(vinculado)

    stmt = text(
        f"""
        with {_REFS_CTE}
        select a.idarticulo, a.nombre, a.categoria, a.precio::float as precio,
               {SUCURSAL_SQL} as sucursal,
               refs.id as ref_pk, refs.producto_id, refs.unidad_conversion,
               p.nombre as producto_nombre
          from articulos_final a
          left join refs on refs.idarticulo = a.idarticulo
          left join costos_productos p on p.id = refs.producto_id
         where {" and ".join(where)}
         order by a.idarticulo, p.nombre, refs.id
        """
    )
    rows = (await session.execute(stmt, params)).mappings().all()

    # Una fila por relación: se agrupa por artículo para que una promo
    # aparezca una sola vez con todos sus productos.
    por_articulo: dict[int, dict] = {}
    for row in rows:
        item = por_articulo.get(row["idarticulo"])
        if item is None:
            item = por_articulo[row["idarticulo"]] = {
                "idarticulo": row["idarticulo"],
                "nombre": row["nombre"],
                "categoria": row["categoria"],
                "sucursal": row["sucursal"],
                "precio": row["precio"],
                "relaciones": [],
            }
        if row["ref_pk"] is not None:
            item["relaciones"].append(
                {
                    "id": row["ref_pk"],
                    "producto_id": row["producto_id"],
                    "producto_nombre": row["producto_nombre"],
                    "unidad_conversion": row["unidad_conversion"],
                }
            )
    for item in por_articulo.values():
        item["estado"] = "vinculado" if item["relaciones"] else "pendiente"
    return list(por_articulo.values())


async def _resumen(session: AsyncSession, sucursal: str | None) -> dict:
    where, params = _filtros_articulo(sucursal, None, None, None)
    stmt = text(
        f"""
        with {_REFS_CTE}
        select count(*) as total,
               count(*) filter (
                   where exists (select 1 from refs x where x.idarticulo = a.idarticulo)
               ) as vinculados
          from articulos_final a
         where {" and ".join(where)}
        """
    )
    row = (await session.execute(stmt, params)).mappings().one()
    return {
        "total": row["total"],
        "vinculados": row["vinculados"],
        "pendientes": row["total"] - row["vinculados"],
    }


async def listar_articulos(
    session: AsyncSession,
    estado: str = "pendiente",
    sucursal: str | None = None,
    categoria: str | None = None,
    q: str | None = None,
) -> dict:
    return {
        "resumen": await _resumen(session, sucursal),
        "items": await _items(session, estado=estado, sucursal=sucursal, categoria=categoria, q=q),
    }


async def obtener_articulo(session: AsyncSession, idarticulo: int) -> dict:
    items = await _items(session, idarticulo=idarticulo)
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artículo no encontrado o inactivo")
    return items[0]


async def reemplazar_relaciones(
    session: AsyncSession, idarticulo: int, relaciones: list[RelacionArticuloWrite]
) -> dict:
    # Todo se valida antes de tocar una sola fila: un PUT inválido deja la
    # relación anterior intacta.
    await obtener_articulo(session, idarticulo)

    invalidas = [r.producto_id for r in relaciones if r.unidad_conversion < 1]
    if invalidas:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La cantidad debe ser un entero mayor o igual a 1 (producto {', '.join(map(str, invalidas))})",
        )

    ids = [r.producto_id for r in relaciones]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Producto repetido en la relación: {', '.join(map(str, repetidos))}",
        )
    if ids:
        existentes = set(
            (await session.execute(select(Productos.id).where(Productos.id.in_(ids)))).scalars().all()
        )
        faltantes = [i for i in ids if i not in existentes]
        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Producto inexistente: {', '.join(map(str, faltantes))}",
            )

    # Reemplazo del conjunto completo. Ninguna tabla referencia
    # costos_productosref.id, así que regenerar los ids no rompe nada. Se borra
    # con la misma regla de coincidencia que usa el listado, para que también
    # se vayan las variantes con espacios (' 500').
    await session.execute(
        text(f"delete from costos_productosref r where {REF_IDARTICULO_SQL} = :idarticulo"),
        {"idarticulo": idarticulo},
    )
    session.add_all(
        ProductosRef(producto_id=r.producto_id, ref_id=str(idarticulo), unidad_conversion=r.unidad_conversion)
        for r in relaciones
    )
    await session.commit()
    return await obtener_articulo(session, idarticulo)
