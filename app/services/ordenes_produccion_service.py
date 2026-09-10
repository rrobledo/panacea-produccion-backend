import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.insumos import Insumos
from app.models.stock_movimiento import StockMovimiento
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
from app.services import explosion_service, maquinaria_service, stock_service

logger = logging.getLogger("panacea_produccion_backend.ordenes_produccion")


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
    # Sólo los llena el motor del grafo: el viejo no sabe cuánta masa consume
    # cada rama ni con qué gramaje se parte.
    masa_kg: float | None = None
    bollos: int | None = None
    gramaje_g: float | None = None


@dataclass
class LineaInsumoPreview:
    insumo_id: int
    insumo_nombre: str
    insumo_unidad_medida: str
    # Float desde F4: las cantidades en KG y LT dejan de redondearse a entero.
    cantidad: float


@dataclass
class OrdenPreview:
    responsable: str
    producto_base_id: int
    producto_base_nombre: str
    lote_produccion: int
    cantidad_total: int
    productos: list[LineaProductoPreview] = field(default_factory=list)
    insumos: list[LineaInsumoPreview] = field(default_factory=list)
    # Sólo los llena el motor del grafo.
    proceso_id: int | None = None
    proceso_version: int | None = None
    proceso_nombre: str | None = None
    lote_unidad: str | None = None
    masa_requerida: float | None = None
    lote_producido: float | None = None
    masa_desde_stock: float | None = None
    sobrante: float | None = None
    pendientes: list[str] = field(default_factory=list)


_CODIGO_RE = re.compile(r"^\d{6}-(\d+)$")


async def _proximo_indice_codigo(session: AsyncSession, fecha: date) -> int:
    """Siguiente número de orden para esa fecha.

    La numeración NO reinicia: al poder completar un día ya generado, volver a
    empezar en 01 produciría códigos repetidos — y con el índice único de
    `codigo` eso ahora falla en el acto en vez de pasar inadvertido. Se cuentan
    todas las órdenes del día, canceladas incluidas: un código no se reutiliza
    aunque su orden ya no sirva. Un código con formato inesperado se ignora en
    lugar de romper la generación (design.md Decision 3).
    """
    result = await session.execute(
        select(OrdenProduccion.codigo).where(OrdenProduccion.fecha_fabricacion == fecha)
    )
    maximo = 0
    for (codigo,) in result.all():
        match = _CODIGO_RE.match(codigo or "")
        if match:
            maximo = max(maximo, int(match.group(1)))
    return maximo + 1


# Estados cuya orden "cubre" a sus productos para esa fecha. CANCELADA queda
# afuera a propósito: cancelar equivale a "esto no se hizo", así que sus
# productos vuelven a estar pendientes (design.md Decision 1).
ESTADOS_QUE_CUBREN = ("ASIGNADA", "EN_PRODUCCION", "FINALIZADA")


async def productos_cubiertos(session: AsyncSession, fecha: date) -> set[int]:
    """producto_id ya cubiertos por órdenes vivas de esa fecha.

    Se compara por producto y no por fila de Programación porque la línea de
    orden guarda `producto_id` y no la fila de la que salió; emparejar por fila
    exigiría una migración que no puede reconstruir el dato para las órdenes ya
    existentes (design.md Decision 1 y Risks).
    """
    result = await session.execute(
        select(OrdenProduccionProductoLinea.producto_id)
        .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionProductoLinea.orden_id)
        .where(
            OrdenProduccion.fecha_fabricacion == fecha,
            OrdenProduccion.estado.in_(ESTADOS_QUE_CUBREN),
        )
    )
    return {producto_id for (producto_id,) in result.all()}


async def contar_ordenes_de_fecha(session: AsyncSession, fecha: date) -> int:
    result = await session.execute(
        select(func.count()).select_from(OrdenProduccion).where(OrdenProduccion.fecha_fabricacion == fecha)
    )
    return int(result.scalar_one())


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

    Solo se consideran los productos **pendientes**: los que todavía no están
    en ninguna orden viva de esa fecha. Así una fecha ya generada no se
    rechaza, sino que ofrece lo que falta.
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

    cubiertos = await productos_cubiertos(session, fecha)
    filas = [f for f in filas if f.producto_id not in cubiertos]
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


async def calcular_ordenes_por_grafo(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> list[OrdenPreview]:
    """El mismo cálculo que `calcular_ordenes`, pero explotando por el grafo.

    La diferencia de fondo cabe en una línea: el motor viejo hace
    `Σ cantidad ÷ lote_produccion`, que sólo es correcto si todos los productos
    de la masa pesan lo mismo; este suma en la unidad del semielaborado,
    `Σ (cantidad × gramaje ÷ (1 − merma))`.

    El filtrado de filas —plan > 0, productos ya cubiertos, overrides, líneas en
    cero— es idéntico al del motor viejo a propósito: lo que cambia es la
    aritmética, no las reglas de qué entra en la orden.
    """
    overrides = overrides or {}

    filas = list(
        (
            await session.execute(
                select(Programacion).where(
                    Programacion.fecha == fecha, Programacion.plan.is_not(None), Programacion.plan > 0
                )
            )
        ).scalars().all()
    )
    if not filas:
        return []

    cubiertos = await productos_cubiertos(session, fecha)
    filas = [f for f in filas if f.producto_id not in cubiertos]
    if not filas:
        return []

    producto_ids = {f.producto_id for f in filas if f.producto_id is not None}
    productos_by_id = {
        p.id: p
        for p in (
            await session.execute(select(Productos).where(Productos.id.in_(producto_ids)))
        ).scalars().all()
    }

    items = []
    for fila in filas:
        producto = productos_by_id.get(fila.producto_id)
        if producto is None:
            continue
        cantidad = overrides.get(fila.id, fila.plan)
        if cantidad is None or cantidad <= 0:
            continue
        items.append((fila.id, producto, float(fila.plan), float(cantidad), fila.responsable))

    planes = await explosion_service.planificar_ordenes(session, items)

    insumo_ids = {insumo_id for plan in planes for insumo_id in plan.insumos}
    insumos_by_id = {}
    if insumo_ids:
        insumos_by_id = {
            i.id: i
            for i in (
                await session.execute(select(Insumos).where(Insumos.id.in_(insumo_ids)))
            ).scalars().all()
        }

    previews: list[OrdenPreview] = []
    for plan in sorted(planes, key=lambda p: (p.proceso.codigo, p.responsable)):
        insumos = []
        for insumo_id, cantidad in sorted(plan.insumos.items()):
            insumo = insumos_by_id.get(insumo_id)
            redondeada = explosion_service.redondear_insumo(
                cantidad, insumo.unidad_medida if insumo else None
            )
            if redondeada <= 0:
                continue
            insumos.append(
                LineaInsumoPreview(
                    insumo_id=insumo_id,
                    insumo_nombre=insumo.nombre if insumo else "",
                    insumo_unidad_medida=insumo.unidad_medida if insumo else "",
                    cantidad=redondeada,
                )
            )

        previews.append(
            OrdenPreview(
                responsable=plan.responsable,
                # `producto_base_*` se mantiene poblado con el artículo que el
                # proceso consume: es lo que el frontend y la oblea ya muestran,
                # y evita romperlos mientras dura la convivencia de motores.
                producto_base_id=plan.articulo_entrada_id or plan.proceso.id,
                producto_base_nombre=plan.proceso.nombre,
                lote_produccion=int(plan.proceso.lote_referencia),
                cantidad_total=sum(int(r.cantidad_planeada) for r in plan.ramas),
                productos=[
                    LineaProductoPreview(
                        programacion_id=rama.programacion_id,
                        producto_id=rama.producto_id,
                        producto_nombre=rama.producto_nombre,
                        cantidad_programada=int(rama.cantidad_programada),
                        cantidad_planeada=int(rama.cantidad_planeada),
                        masa_kg=round(rama.masa, 3),
                        bollos=rama.bollos,
                        gramaje_g=rama.gramaje_g,
                    )
                    for rama in plan.ramas
                ],
                insumos=insumos,
                proceso_id=plan.proceso.id,
                proceso_version=plan.proceso.version,
                proceso_nombre=plan.proceso.nombre,
                lote_unidad=plan.proceso.lote_unidad,
                masa_requerida=round(plan.requerido, 3),
                lote_producido=round(plan.lote_a_producir, 3),
                masa_desde_stock=round(plan.desde_stock, 3),
                sobrante=round(plan.sobrante, 3),
                pendientes=plan.pendientes,
            )
        )
    return previews


async def _calcular(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> list[OrdenPreview]:
    """Despacha al motor activo. El flag existe para poder volver sin desplegar."""
    if get_settings().motor_grafo:
        return await calcular_ordenes_por_grafo(session, fecha, overrides)
    return await calcular_ordenes(session, fecha, overrides)


async def preview_ordenes(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> tuple[list[OrdenPreview], int, list[str]]:
    previews = await _calcular(session, fecha, overrides)
    avisos = await maquinaria_service.avisos_de_capacidad(session, fecha, previews)
    return previews, await contar_ordenes_de_fecha(session, fecha), avisos


async def generar_ordenes(
    session: AsyncSession, fecha: date, overrides: dict[int, int] | None = None
) -> list[OrdenProduccion]:
    previews = await _calcular(session, fecha, overrides)
    if not previews:
        return []

    hoy = datetime.now(timezone.utc)
    ordenes_creadas: list[OrdenProduccion] = []
    codigo_prefix = fecha.strftime("%y%m%d")
    primer_indice = await _proximo_indice_codigo(session, fecha)

    for offset, preview in enumerate(previews):
        codigo = f"{codigo_prefix}-{primer_indice + offset:02d}"
        orden = OrdenProduccion(
            codigo=codigo,
            fecha_fabricacion=fecha,
            responsable=preview.responsable,
            estado="ASIGNADA",
            fecha_creacion=hoy,
            # Se congela la versión de receta con la que se emitió: editar el
            # proceso después no puede reescribir el costo de esta orden
            # (design.md D12).
            proceso_id=preview.proceso_id,
            proceso_version=preview.proceso_version,
            masa_requerida=preview.masa_requerida,
            lote_producido=preview.lote_producido,
            masa_desde_stock=preview.masa_desde_stock,
        )
        session.add(orden)
        await session.flush()

        for linea in preview.productos:
            session.add(
                OrdenProduccionProductoLinea(
                    orden_id=orden.id,
                    producto_id=linea.producto_id,
                    cantidad_planeada=linea.cantidad_planeada,
                    programacion_id=linea.programacion_id,
                    masa_kg=linea.masa_kg,
                    bollos=linea.bollos,
                    gramaje_g=linea.gramaje_g,
                )
            )
        for linea in preview.insumos:
            # La línea y su RESERVA llevan la misma cantidad entera, así que lo
            # que muestra la orden es exactamente lo reservado y después
            # consumido (spec `stock`).
            session.add(
                OrdenProduccionInsumoLinea(orden_id=orden.id, insumo_id=linea.insumo_id, cantidad=linea.cantidad)
            )
            session.add(stock_service.crear_reserva(linea.insumo_id, linea.cantidad, codigo, orden.id))

        # Las máquinas se resuelven al emitir, no en la receta: la receta dice
        # qué TIPO hace falta y con qué capacidad mínima (design.md D10).
        for operacion in await maquinaria_service.construir_operaciones_de_orden(
            session, preview.proceso_id, float(preview.lote_producido or 0)
        ):
            operacion.orden_id = orden.id
            session.add(operacion)

        # Lo que salió del stock de semielaborados se consume acá: si no, el
        # saldo quedaría disponible para la orden siguiente y se contaría dos
        # veces (design.md D5).
        if preview.masa_desde_stock and preview.proceso_id:
            articulo_id = preview.producto_base_id
            if articulo_id:
                await stock_service.consumir_articulo(
                    session, articulo_id, preview.masa_desde_stock, codigo, orden.id
                )

        ordenes_creadas.append(orden)

    await session.commit()
    return [await get_orden(session, orden.id) for orden in ordenes_creadas]


# El Responsable es a quién se le asigna el trabajo, así que solo tiene sentido
# cambiarlo mientras la orden sigue viva. En FINALIZADA o CANCELADA es parte del
# registro de lo que pasó y reescribirlo falsearía el histórico.
ESTADOS_REASIGNABLES = ("ASIGNADA", "EN_PRODUCCION")


async def actualizar_responsable(
    session: AsyncSession, orden: OrdenProduccion, responsable: str
) -> OrdenProduccion:
    if orden.estado not in ESTADOS_REASIGNABLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No se puede cambiar el responsable de una orden en estado '{orden.estado}': "
                f"solo se puede en {' o '.join(ESTADOS_REASIGNABLES)}."
            ),
        )
    orden.responsable = responsable.strip()
    await session.commit()
    return await get_orden(session, orden.id)


ESTADOS_BORRABLES = ("ASIGNADA", "CANCELADA")


async def eliminar_orden(session: AsyncSession, orden: OrdenProduccion) -> None:
    """Borra una orden que nunca llegó a producirse, con sus reservas.

    Solo `ASIGNADA` y `CANCELADA`: una `EN_PRODUCCION` ya consumió insumos y
    borrarla dejaría un CONSUMO sin orden que lo explique, y una `FINALIZADA`
    tiene ProductoFabricado apuntándola con un FK sin cascade, así que el
    borrado fallaría con un error de base opaco (design.md Decision 4).

    Las líneas de producto e insumo se van solas por el ON DELETE CASCADE, y
    desde la migración 0026 los movimientos también: `stock_movimientos.orden_id`
    es un FK con ON DELETE CASCADE. El borrado explícito de abajo se mantiene
    como red para los movimientos anteriores a esa migración cuyo backfill no
    haya encontrado orden (quedaron con `orden_id` en NULL y sólo el código en
    `referencia`). Es seguro porque una orden borrable nunca tuvo CONSUMO, y el
    índice único de `codigo` garantiza que la referencia identifique una sola
    orden (Decision 5).
    """
    if orden.estado not in ESTADOS_BORRABLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No se puede borrar una orden en estado '{orden.estado}': solo se pueden borrar "
                f"las órdenes en {' o '.join(ESTADOS_BORRABLES)}."
            ),
        )

    await session.execute(
        delete(StockMovimiento).where(
            StockMovimiento.tipo == "RESERVA", StockMovimiento.referencia == orden.codigo
        )
    )
    await session.delete(orden)
    await session.commit()


async def iniciar_produccion(session: AsyncSession, orden: OrdenProduccion) -> OrdenProduccion:
    if orden.estado != "ASIGNADA":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition: '{orden.estado}' -> 'EN_PRODUCCION'. Expected current state: 'ASIGNADA'",
        )

    # STOCK_FALTANTES_BLOQUEA_INICIO=false desactiva solo esta validación: el
    # CONSUMO de abajo se registra igual y el insumo puede quedar en negativo
    # (ver app/config.py).
    if get_settings().stock_faltantes_bloquea_inicio:
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
        session.add(stock_service.crear_consumo(linea.insumo, linea.cantidad, orden.codigo, orden.id))

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


def _redondear_ejecutado(cantidad: float) -> int:
    """Redondea la cantidad ejecutada a unidades enteras (half-up).

    `costos_programacion.prod` es INTEGER y `cantidad_fabricada` es FLOAT, así
    que el total hay que redondearlo. Se usa Decimal con ROUND_HALF_UP y no el
    `round()` de Python, que aplica banker's rounding (`round(2.5)` da 2), y no
    se trunca: truncar sesgaría el ejecutado siempre a la baja y ese sesgo se
    acumula en el `porcentaje_ejecutado` del reporte de Producción
    (design.md Decision 4).

    A diferencia de `_redondear_insumo`, acá **no** hay piso de 1: ese piso
    existe para que un insumo requerido no desaparezca de la orden, mientras
    que un ejecutado es un hecho — si se fabricó menos de media unidad, el
    entero que le corresponde es 0, y forzar un 1 inventaría producción.
    """
    if cantidad <= 0:
        return 0
    return int(Decimal(str(cantidad)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def sincronizar_ejecutado_programacion(
    session: AsyncSession, fecha: date, producto_ids: Iterable[int]
) -> None:
    """Escribe en la Programación de `fecha` lo ejecutado de esos productos.

    El valor se **recalcula** como la suma de `cantidad_fabricada` registrada
    por las órdenes `FINALIZADA` de ese producto y esa fecha; no se incrementa
    el valor que hubiera. Así la función es idempotente: correrla dos veces da
    el mismo número. Importa porque `prod` se suma en los reportes
    (`analytics_service`: `sum(prod)`, `porcentaje_ejecutado`, y el consumo
    estimado de insumo), donde un valor duplicado no se nota hasta que alguien
    audita el mes (design.md Decision 1).

    Un valor cargado a mano en la celda E queda reemplazado por el real: la
    finalización es la fuente de verdad de lo producido.

    La fecha es la de fabricación de la orden y no `ProductoFabricado.fecha`,
    que es el instante del cierre: una orden del viernes cerrada el sábado
    tiene que imputar el viernes (Decision 2). Y el desperdicio no entra —
    E se compara contra P, que es cuánto de lo planeado se logró (Decision 3).

    No falla si la Programación no tiene fila para un producto y esa fecha: la
    orden se finaliza igual y queda registro en el log. Negar el cierre por una
    fila de libro mayor dejaría al usuario con una orden abierta y sin forma de
    avanzar, habiendo perdido lo que registró (Decision 6).
    """
    producto_ids = {producto_id for producto_id in producto_ids if producto_id is not None}
    if not producto_ids:
        return

    # Un agregado por GROUP BY y un IN, no una consulta por producto: una orden
    # agrupa varios productos de la misma base (Decision 8).
    totales_result = await session.execute(
        select(ProductoFabricado.producto_id, func.sum(ProductoFabricado.cantidad_fabricada))
        .join(OrdenProduccion, OrdenProduccion.id == ProductoFabricado.orden_id)
        .where(
            ProductoFabricado.producto_id.in_(producto_ids),
            OrdenProduccion.fecha_fabricacion == fecha,
            OrdenProduccion.estado == "FINALIZADA",
        )
        .group_by(ProductoFabricado.producto_id)
    )
    totales = {producto_id: total for producto_id, total in totales_result.all()}

    filas_result = await session.execute(
        select(Programacion)
        .where(Programacion.producto_id.in_(producto_ids), Programacion.fecha == fecha)
        .order_by(Programacion.id)
    )
    # `setdefault` deja la fila de menor id si un producto tuviera más de una
    # para la misma fecha. Se escribe una sola: `analytics_service` hace
    # `sum(cp.prod)`, así que escribir el total en las dos duplicaría el
    # producido y el consumo estimado de insumo (Decision 7).
    filas_por_producto: dict[int, Programacion] = {}
    for fila in filas_result.scalars().all():
        filas_por_producto.setdefault(fila.producto_id, fila)

    for producto_id in sorted(producto_ids):
        fila = filas_por_producto.get(producto_id)
        if fila is None:
            logger.warning(
                "No hay fila de Programación para producto_id=%s y fecha=%s: "
                "se omite la sincronización del ejecutado de ese producto",
                producto_id,
                fecha,
            )
            continue
        fila.prod = _redondear_ejecutado(float(totales.get(producto_id) or 0))


async def _registrar_produccion_en_stock(
    session: AsyncSession, orden: OrdenProduccion, payload: FinalizarOrdenRequest
) -> None:
    """Un movimiento PRODUCCION por cada artículo producido que la orden cerró.

    El disponible de un artículo producido se deriva sumando su ledger, así que
    esto es lo único que hace falta para que la masa amasada de más quede con
    saldo y una orden posterior la pueda consumir (design.md D4 y D5).

    Las cantidades en cero se saltean: una línea que registró que no salió nada
    no tiene por qué dejar un movimiento que después haya que explicar.
    """
    producto_ids = [linea.producto_id for linea in payload.lineas if linea.cantidad_fabricada]
    if not producto_ids:
        return

    naturalezas = dict(
        (
            await session.execute(
                select(Productos.id, Productos.naturaleza).where(Productos.id.in_(producto_ids))
            )
        ).all()
    )
    for linea in payload.lineas:
        if not linea.cantidad_fabricada:
            continue
        if naturalezas.get(linea.producto_id) not in ("SEMIELABORADO", "TERMINADO"):
            continue
        session.add(
            stock_service.crear_produccion(
                linea.producto_id, float(linea.cantidad_fabricada), orden.codigo, orden.id
            )
        )


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

    # F2b: lo fabricado entra al ledger de artículos. El desperdicio no: no está
    # disponible para consumir, y sumarlo inflaría el saldo de la masa
    # (specs/stock/spec.md). Sólo los artículos producidos — un insumo nunca se
    # fabrica — y sólo lo que efectivamente salió.
    await _registrar_produccion_en_stock(session, orden, payload)

    orden.estado = "FINALIZADA"
    setattr(orden, ORDEN_PRODUCCION_ESTADO_TIMESTAMP_FIELD["FINALIZADA"], hoy)

    # La consulta del ejecutado filtra por `estado = 'FINALIZADA'` y suma los
    # ProductoFabricado, o sea justo lo que estas líneas acaban de escribir en
    # la sesión: si no estuvieran en la base, la orden que se está cerrando no
    # se contaría y el ejecutado quedaría en el total anterior (0 en el caso
    # normal) sin que nada falle. El autoflush de SQLAlchemy ya las manda al
    # ejecutar el SELECT, así que este flush es explícito a propósito: deja la
    # dependencia a la vista y no la hace depender de que el autoflush siga
    # activo (design.md Decision 5).
    await session.flush()
    # Los producto_id se deduplican dentro: una orden puede tener dos líneas
    # del mismo producto (dos filas de Programación en el mismo grupo).
    await sincronizar_ejecutado_programacion(
        session, orden.fecha_fabricacion, [linea.producto_id for linea in orden.productos]
    )

    # Un solo commit para el Registro de Producto Fabricado, el cambio de estado
    # y el ejecutado de la Programación: si fueran dos transacciones, un fallo en
    # el medio dejaría las dos fuentes diciendo cosas distintas y no existe
    # ninguna operación de resincronización que lo arregle (Decision 5).
    await session.commit()
    return await get_orden(session, orden.id)


async def list_productos_fabricados(
    session: AsyncSession,
    producto_id: int | None = None,
    ubicacion_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    orden_id: int | None = None,
) -> list[ProductoFabricado]:
    stmt = select(ProductoFabricado).options(
        selectinload(ProductoFabricado.producto).selectinload(Productos.producto_base),
        selectinload(ProductoFabricado.ubicacion),
        selectinload(ProductoFabricado.ubicacion_desperdicio),
        selectinload(ProductoFabricado.orden),
    )
    if orden_id is not None:
        stmt = stmt.where(ProductoFabricado.orden_id == orden_id)
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


# ── Comparación entre motores (task 4.7) ────────────────────────────────────


async def comparar_motores(session: AsyncSession, fecha: date) -> dict:
    """Las cantidades de insumo de los dos motores, lado a lado para una fecha.

    Es la red del cambio de motor: antes de que F4 modifique lo que se reserva,
    esto muestra exactamente dónde y cuánto cambia. Mientras el relevamiento de
    gramajes no esté completo, el motor nuevo devuelve un resultado parcial y
    la respuesta lo dice en `pendientes` en vez de mostrar una diferencia que
    sería mentira.
    """
    # A propósito el motor viejo directo y no `preview_ordenes`: si el flag ya
    # estuviera prendido, la comparación mostraría el motor nuevo contra sí mismo.
    previews = await calcular_ordenes(session, fecha, None)
    viejo: dict[int, float] = {}
    for preview in previews:
        for linea in preview.insumos:
            viejo[linea.insumo_id] = viejo.get(linea.insumo_id, 0) + linea.cantidad

    demanda = await explosion_service.demanda_de_la_fecha(session, fecha)
    nuevo = await explosion_service.explotar_demanda(session, demanda)

    insumo_ids = sorted(set(viejo) | set(nuevo.insumos))
    nombres = {}
    if insumo_ids:
        nombres = dict(
            (
                await session.execute(select(Insumos.id, Insumos.nombre).where(Insumos.id.in_(insumo_ids)))
            ).all()
        )

    filas = []
    for insumo_id in insumo_ids:
        cantidad_vieja = float(viejo.get(insumo_id, 0))
        cantidad_nueva = float(nuevo.insumos.get(insumo_id, 0))
        filas.append(
            {
                "insumo_id": insumo_id,
                "insumo_nombre": nombres.get(insumo_id, ""),
                "motor_viejo": round(cantidad_vieja, 3),
                "motor_nuevo": round(cantidad_nueva, 3),
                "diferencia": round(cantidad_nueva - cantidad_vieja, 3),
                "cambia": abs(cantidad_nueva - cantidad_vieja) > 0.001,
            }
        )

    return {
        "fecha": fecha,
        "comparable": nuevo.completo,
        "pendientes": nuevo.pendientes,
        "insumos_que_cambian": sum(1 for f in filas if f["cambia"]),
        "filas": filas,
    }
