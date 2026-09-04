from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.insumos import Insumos
from app.models.ordenes_produccion import (
    OrdenProduccion,
    OrdenProduccionInsumoLinea,
    OrdenProduccionProductoLinea,
    ProductoFabricado,
)
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.schemas.ordenes_produccion import FinalizarOrdenRequest
from app.schemas.vocab import ORDEN_PRODUCCION_ESTADO_TIMESTAMP_FIELD, ORDEN_PRODUCCION_VALID_TRANSITIONS
from app.services import stock_service


def _orden_stmt():
    return select(OrdenProduccion).options(
        selectinload(OrdenProduccion.productos)
        .selectinload(OrdenProduccionProductoLinea.producto)
        # Explicit chain, not relying on Productos.producto_base's own
        # default lazy strategy — that default doesn't reliably fire once
        # Productos is reached through another relationship's selectinload
        # chain in this async setup (see ProductoRead serialization).
        .selectinload(Productos.producto_base),
        selectinload(OrdenProduccion.insumos).selectinload(OrdenProduccionInsumoLinea.insumo),
    )


async def list_ordenes(
    session: AsyncSession,
    fecha_fabricacion: date | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    estado: str | None = None,
) -> list[OrdenProduccion]:
    stmt = _orden_stmt()
    if fecha_fabricacion is not None:
        stmt = stmt.where(OrdenProduccion.fecha_fabricacion == fecha_fabricacion)
    if fecha_desde is not None:
        stmt = stmt.where(OrdenProduccion.fecha_fabricacion >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(OrdenProduccion.fecha_fabricacion <= fecha_hasta)
    if estado is not None:
        stmt = stmt.where(OrdenProduccion.estado == estado)
    stmt = stmt.order_by(OrdenProduccion.fecha_fabricacion.desc(), OrdenProduccion.codigo)
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def get_orden(session: AsyncSession, orden_id: int) -> OrdenProduccion:
    stmt = _orden_stmt().where(OrdenProduccion.id == orden_id).execution_options(populate_existing=True)
    row = (await session.execute(stmt)).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de producción not found")
    return row


def _redondear_insumo(cantidad: float) -> int:
    """Redondea la cantidad de un insumo a unidades enteras (half-up).

    Producción no maneja fracciones, así que la cantidad se guarda y se
    muestra entera. Dos detalles importantes (ver design.md Decision 4):

    - Se usa Decimal con ROUND_HALF_UP y no el `round()` de Python, que
      aplica banker's rounding: `round(2.5)` da 2, no 3.
    - Un requerimiento mayor que cero nunca baja a cero. Sin ese piso, un
      insumo de 0.4 KG redondearía a 0 y el generador lo descartaría
      (`if cantidad <= 0: continue`), dejándolo fuera de la orden y sin
      reservar ni consumir: un faltante de stock silencioso.
    """
    if cantidad <= 0:
        return 0
    redondeada = int(Decimal(str(cantidad)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(1, redondeada)


async def _get_costos(session: AsyncSession, producto_id: int) -> list[Costos]:
    result = await session.execute(select(Costos).where(Costos.producto_id == producto_id))
    return list(result.scalars().all())


@dataclass
class LineaProductoPreview:
    programacion_id: int
    producto_id: int
    producto_nombre: str
    cantidad_programada: int
    cantidad_planeada: int


@dataclass
class LineaInsumoPreview:
    insumo_id: int
    insumo_nombre: str
    insumo_unidad_medida: str
    cantidad: int


@dataclass
class OrdenPreview:
    responsable: str
    producto_base_id: int
    producto_base_nombre: str
    lote_produccion: int
    cantidad_total: int
    productos: list[LineaProductoPreview] = field(default_factory=list)
    insumos: list[LineaInsumoPreview] = field(default_factory=list)


async def validar_fecha_sin_ordenes(session: AsyncSession, fecha: date) -> None:
    existing = await session.execute(
        select(OrdenProduccion.id).where(OrdenProduccion.fecha_fabricacion == fecha).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ya existen órdenes de producción generadas para {fecha.isoformat()}",
        )


async def calcular_ordenes(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> list[OrdenPreview]:
    """Calcula las órdenes que corresponden a una fecha, sin persistir nada.

    Es la única implementación del cálculo: `generar_ordenes` la usa y
    después persiste lo que devuelve, de modo que la vista previa y la orden
    generada coinciden por construcción (ver design.md Decision 2).

    `overrides` mapea `programacion_id` -> cantidad corregida por el usuario.
    Se indexa por la fila de Programación y no por producto porque un mismo
    producto puede aparecer en más de una fila del mismo grupo (Decision 3).
    Una cantidad en 0 excluye la línea, y un grupo que queda sin líneas no
    genera orden (Decision 7).
    """
    overrides = overrides or {}

    prog_result = await session.execute(
        select(Programacion).where(
            Programacion.fecha == fecha, Programacion.plan.is_not(None), Programacion.plan > 0
        )
    )
    filas = list(prog_result.scalars().all())
    if not filas:
        return []

    producto_ids = {f.producto_id for f in filas if f.producto_id is not None}
    productos_result = await session.execute(select(Productos).where(Productos.id.in_(producto_ids)))
    productos_by_id = {p.id: p for p in productos_result.scalars().all()}

    # Agrupar por (producto_base_id o producto_id si no tiene base, responsable)
    # — ver design.md Decision 4 y 8 de ordenes-produccion-stock.
    grupos: dict[tuple[int, str], list[tuple[Programacion, Productos, int]]] = defaultdict(list)
    for fila in filas:
        producto = productos_by_id.get(fila.producto_id)
        if producto is None:
            continue
        cantidad = overrides.get(fila.id, fila.plan)
        if cantidad is None or cantidad <= 0:
            # Cantidad puesta en 0 en la vista previa: la línea no va.
            continue
        base_id = producto.producto_base_id if producto.producto_base_id is not None else producto.id
        grupos[(base_id, fila.responsable)].append((fila, producto, cantidad))

    previews: list[OrdenPreview] = []
    for (base_id, responsable), items in sorted(grupos.items(), key=lambda kv: kv[0]):
        base_producto = productos_by_id.get(base_id) or await session.get(Productos, base_id)
        cantidad_total = sum(cantidad for _, _, cantidad in items)

        insumo_needs: dict[int, float] = defaultdict(float)
        if base_producto.lote_produccion:
            scale = cantidad_total / base_producto.lote_produccion
            for costo in await _get_costos(session, base_producto.id):
                insumo_needs[costo.insumo_id] += costo.cantidad * scale

        for fila, producto, cantidad in items:
            if producto.id != base_producto.id and producto.producto_base_id is not None:
                # Insumos propios adicionales del producto final (relleno,
                # glaseado, etc.) — se suman aparte de la base compartida.
                own_costos = await _get_costos(session, producto.id)
                if own_costos and producto.lote_produccion:
                    own_scale = cantidad / producto.lote_produccion
                    for costo in own_costos:
                        insumo_needs[costo.insumo_id] += costo.cantidad * own_scale

        # El redondeo se aplica una sola vez, sobre el total acumulado de cada
        # insumo — nunca sobre cada aporte parcial, que acumularía error en las
        # órdenes que suman receta base más insumos propios (Decision 4).
        insumos_redondeados = {
            insumo_id: _redondear_insumo(cantidad) for insumo_id, cantidad in insumo_needs.items()
        }
        insumos_redondeados = {i: c for i, c in insumos_redondeados.items() if c > 0}

        insumos_by_id: dict[int, Insumos] = {}
        if insumos_redondeados:
            insumos_result = await session.execute(
                select(Insumos).where(Insumos.id.in_(insumos_redondeados.keys()))
            )
            insumos_by_id = {i.id: i for i in insumos_result.scalars().all()}

        previews.append(
            OrdenPreview(
                responsable=responsable,
                producto_base_id=base_producto.id,
                producto_base_nombre=base_producto.nombre,
                lote_produccion=base_producto.lote_produccion,
                cantidad_total=cantidad_total,
                productos=[
                    LineaProductoPreview(
                        programacion_id=fila.id,
                        producto_id=producto.id,
                        producto_nombre=producto.nombre,
                        cantidad_programada=fila.plan,
                        cantidad_planeada=cantidad,
                    )
                    for fila, producto, cantidad in items
                ],
                insumos=[
                    LineaInsumoPreview(
                        insumo_id=insumo_id,
                        insumo_nombre=insumos_by_id[insumo_id].nombre if insumo_id in insumos_by_id else "",
                        insumo_unidad_medida=(
                            insumos_by_id[insumo_id].unidad_medida if insumo_id in insumos_by_id else ""
                        ),
                        cantidad=cantidad,
                    )
                    for insumo_id, cantidad in sorted(insumos_redondeados.items())
                ],
            )
        )

    return previews


async def preview_ordenes(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> list[OrdenPreview]:
    await validar_fecha_sin_ordenes(session, fecha)
    return await calcular_ordenes(session, fecha, overrides)


async def generar_ordenes(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> list[OrdenProduccion]:
    await validar_fecha_sin_ordenes(session, fecha)

    previews = await calcular_ordenes(session, fecha, overrides)
    if not previews:
        return []

    hoy = datetime.now(timezone.utc)
    ordenes_creadas: list[OrdenProduccion] = []
    codigo_prefix = fecha.strftime("%y%m%d")

    for idx, preview in enumerate(previews, start=1):
        codigo = f"{codigo_prefix}-{idx:02d}"
        orden = OrdenProduccion(
            codigo=codigo,
            fecha_fabricacion=fecha,
            responsable=preview.responsable,
            estado="ASIGNADA",
            fecha_creacion=hoy,
        )
        session.add(orden)
        await session.flush()

        for linea in preview.productos:
            session.add(
                OrdenProduccionProductoLinea(
                    orden_id=orden.id, producto_id=linea.producto_id, cantidad_planeada=linea.cantidad_planeada
                )
            )
        for linea in preview.insumos:
            # La línea y su RESERVA llevan la misma cantidad entera, así que lo
            # que muestra la orden es exactamente lo reservado y después
            # consumido (spec `stock`).
            session.add(
                OrdenProduccionInsumoLinea(orden_id=orden.id, insumo_id=linea.insumo_id, cantidad=linea.cantidad)
            )
            session.add(stock_service.crear_reserva(linea.insumo_id, linea.cantidad, codigo))

        ordenes_creadas.append(orden)

    await session.commit()
    return [await get_orden(session, orden.id) for orden in ordenes_creadas]


async def iniciar_produccion(session: AsyncSession, orden: OrdenProduccion) -> OrdenProduccion:
    if orden.estado != "ASIGNADA":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition: '{orden.estado}' -> 'EN_PRODUCCION'. Expected current state: 'ASIGNADA'",
        )

    faltantes = []
    for linea in orden.insumos:
        if linea.insumo.cantidad < linea.cantidad:
            faltantes.append(
                f"{linea.insumo.nombre}: necesita {linea.cantidad}, disponible {linea.insumo.cantidad}"
            )
    if faltantes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stock físico insuficiente para iniciar producción: " + "; ".join(faltantes),
        )

    for linea in orden.insumos:
        session.add(stock_service.crear_consumo(linea.insumo, linea.cantidad, orden.codigo))

    orden.estado = "EN_PRODUCCION"
    setattr(orden, ORDEN_PRODUCCION_ESTADO_TIMESTAMP_FIELD["EN_PRODUCCION"], datetime.now(timezone.utc))
    await session.commit()
    return await get_orden(session, orden.id)


async def cancelar_orden(session: AsyncSession, orden: OrdenProduccion) -> OrdenProduccion:
    if orden.estado != "ASIGNADA":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Solo se puede cancelar una orden en estado 'ASIGNADA' (actual: '{orden.estado}')",
        )
    # Liberar la RESERVA: get_comprometido_map solo suma líneas de órdenes en
    # ASIGNADA, así que pasar a CANCELADA ya libera el insumo sin necesitar
    # un movimiento adicional — ver design.md Decision 2 / Risks.
    orden.estado = "CANCELADA"
    setattr(orden, ORDEN_PRODUCCION_ESTADO_TIMESTAMP_FIELD["CANCELADA"], datetime.now(timezone.utc))
    await session.commit()
    return await get_orden(session, orden.id)


async def finalizar_orden(
    session: AsyncSession, orden: OrdenProduccion, payload: FinalizarOrdenRequest
) -> OrdenProduccion:
    if ORDEN_PRODUCCION_VALID_TRANSITIONS.get(orden.estado) != "FINALIZADA":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition: '{orden.estado}' -> 'FINALIZADA'. Expected current state: 'EN_PRODUCCION'",
        )

    producto_ids_en_orden = {linea.producto_id for linea in orden.productos}
    hoy = datetime.now(timezone.utc)
    for linea in payload.lineas:
        if linea.producto_id not in producto_ids_en_orden:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"producto_id {linea.producto_id} no pertenece a esta orden",
            )
        session.add(
            ProductoFabricado(
                orden_id=orden.id,
                producto_id=linea.producto_id,
                cantidad_fabricada=linea.cantidad_fabricada,
                ubicacion_id=linea.ubicacion_id,
                cantidad_desperdicio=linea.cantidad_desperdicio,
                ubicacion_desperdicio_id=linea.ubicacion_desperdicio_id,
                motivo_desperdicio=linea.motivo_desperdicio,
                fecha=hoy,
            )
        )

    orden.estado = "FINALIZADA"
    setattr(orden, ORDEN_PRODUCCION_ESTADO_TIMESTAMP_FIELD["FINALIZADA"], hoy)
    await session.commit()
    return await get_orden(session, orden.id)


async def list_productos_fabricados(
    session: AsyncSession,
    producto_id: int | None = None,
    ubicacion_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> list[ProductoFabricado]:
    stmt = select(ProductoFabricado).options(
        selectinload(ProductoFabricado.producto).selectinload(Productos.producto_base),
        selectinload(ProductoFabricado.ubicacion),
        selectinload(ProductoFabricado.ubicacion_desperdicio),
        selectinload(ProductoFabricado.orden),
    )
    if producto_id is not None:
        stmt = stmt.where(ProductoFabricado.producto_id == producto_id)
    if ubicacion_id is not None:
        stmt = stmt.where(ProductoFabricado.ubicacion_id == ubicacion_id)
    if fecha_desde is not None:
        stmt = stmt.where(ProductoFabricado.fecha >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(ProductoFabricado.fecha <= fecha_hasta)
    stmt = stmt.order_by(ProductoFabricado.fecha.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
