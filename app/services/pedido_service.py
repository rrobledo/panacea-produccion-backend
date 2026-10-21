from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pedido import Pedido, PedidoDetalle, PedidoRemitoLegacy
from app.models.productos import Productos
from app.models.sucursal import Sucursal
from app.schemas.pedido import PedidoCreate, PedidoEntregaRequest, PedidoFacturacionRequest, PedidoUpdate
from app.schemas.vocab import PEDIDO_ESTADO_TIMESTAMP_FIELD, PEDIDO_VALID_TRANSITIONS, REMITO_ESTADO_INICIAL

# Estados en los que un envío puede marcarse como facturado — ver
# openspec/changes/unificar-pedidos-y-remitos/design.md D5.
_FACTURABLE_ESTADOS = {"LISTO_PARA_ENTREGA", "ENTREGADO"}


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _pedido_stmt():
    # Explicit chain down to producto_base — ProductoRead serializes it, and
    # Productos.producto_base's own default lazy strategy doesn't reliably
    # fire once Productos is reached via another relationship's selectinload
    # chain in this async setup.
    return select(Pedido).options(
        selectinload(Pedido.detalles).selectinload(PedidoDetalle.producto).selectinload(Productos.producto_base),
        selectinload(Pedido.remitos_legacy),
    )


def _add_detalle_rows(session: AsyncSession, pedido_id: int, detalles, es_remito: bool) -> None:
    for item in detalles:
        if es_remito:
            # Remito directo: nada pedido, lo despachado va en cantidad_entregada.
            if item.cantidad_entregada > 0:
                session.add(
                    PedidoDetalle(
                        pedido_id=pedido_id,
                        producto_id=item.producto_id,
                        cantidad_pedida=0,
                        cantidad_entregada=item.cantidad_entregada,
                        observaciones=item.observaciones,
                    )
                )
        elif item.cantidad_pedida > 0:
            session.add(
                PedidoDetalle(
                    pedido_id=pedido_id,
                    producto_id=item.producto_id,
                    cantidad_pedida=item.cantidad_pedida,
                    observaciones=item.observaciones,
                )
            )


async def create_pedido(session: AsyncSession, payload: PedidoCreate) -> Pedido:
    data = payload.model_dump(exclude={"detalles"})
    if payload.tipo == "SUCURSAL" and payload.origen_sucursal_id is None:
        fabrica = await _get_fabrica_sucursal(session)
        if fabrica.id == payload.sucursal_id:
            raise _unprocessable("origen_sucursal_id and sucursal_id must be different")
        data["origen_sucursal_id"] = fabrica.id

    now = datetime.now(timezone.utc)
    pedido = Pedido(fecha_carga=now, **data)
    if payload.es_remito:
        # El remito directo nace listo para entregar, sin pasar por la
        # preparación — ver specs/envios/spec.md "Remito directo como envío".
        pedido.estado = REMITO_ESTADO_INICIAL
        setattr(pedido, PEDIDO_ESTADO_TIMESTAMP_FIELD[REMITO_ESTADO_INICIAL], now)
    session.add(pedido)
    await session.flush()
    _add_detalle_rows(session, pedido.id, payload.detalles, payload.es_remito)
    await session.commit()
    return await get_pedido(session, pedido.id)


async def list_pedidos(
    session: AsyncSession,
    tipo: str | None = None,
    cliente_id: int | None = None,
    sucursal_id: int | None = None,
    origen_sucursal_id: int | None = None,
    estado: str | None = None,
    es_remito: bool | None = None,
    facturado: bool | None = None,
    remito_legacy_id: int | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Pedido]:
    stmt = _pedido_stmt()
    if tipo is not None:
        stmt = stmt.where(Pedido.tipo == tipo)
    if cliente_id is not None:
        stmt = stmt.where(Pedido.cliente_id == cliente_id)
    if sucursal_id is not None:
        stmt = stmt.where(Pedido.sucursal_id == sucursal_id)
    if origen_sucursal_id is not None:
        stmt = stmt.where(Pedido.origen_sucursal_id == origen_sucursal_id)
    if estado is not None:
        stmt = stmt.where(Pedido.estado == estado)
    if es_remito is not None:
        stmt = stmt.where(Pedido.es_remito == es_remito)
    if facturado is not None:
        stmt = stmt.where(Pedido.fecha_facturado.is_not(None) if facturado else Pedido.fecha_facturado.is_(None))
    if remito_legacy_id is not None:
        stmt = stmt.where(
            Pedido.id.in_(
                select(PedidoRemitoLegacy.pedido_id).where(PedidoRemitoLegacy.remito_legacy_id == remito_legacy_id)
            )
        )
    if fecha_desde:
        stmt = stmt.where(Pedido.fecha_entrega >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Pedido.fecha_entrega <= fecha_hasta)
    stmt = stmt.order_by(Pedido.fecha_carga.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def get_pedido(session: AsyncSession, pedido_id: int) -> Pedido:
    stmt = _pedido_stmt().where(Pedido.id == pedido_id).execution_options(populate_existing=True)
    row = (await session.execute(stmt)).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido not found")
    return row


def ensure_editable(pedido: Pedido) -> None:
    if pedido.es_remito:
        if pedido.estado != REMITO_ESTADO_INICIAL or pedido.fecha_facturado is not None:
            raise _unprocessable(
                f"Only remitos in '{REMITO_ESTADO_INICIAL}' estado and not yet facturados can be edited or deleted"
            )
    elif pedido.estado != "PENDIENTE":
        raise _unprocessable("Only pedidos in 'PENDIENTE' estado can be edited or deleted")


async def update_pedido(session: AsyncSession, pedido: Pedido, payload: PedidoUpdate) -> Pedido:
    data = payload.model_dump(exclude={"detalles"}, exclude_unset=True)
    for field, value in data.items():
        setattr(pedido, field, value)

    if payload.detalles is not None:
        if pedido.es_remito and any(item.cantidad_pedida != 0 for item in payload.detalles):
            raise _unprocessable("cantidad_pedida must be 0 on every line of a remito")
        # Merge by producto_id instead of delete-and-recreate, so
        # fecha_creacion is preserved on items that already existed — it
        # only advances for genuinely new lines. See PedidoDetalle.fecha_creacion.
        existentes = {d.producto_id: d for d in pedido.detalles}
        vistos: set[int] = set()
        for item in payload.detalles:
            if item.cantidad_pedida <= 0 and item.cantidad_entregada <= 0:
                continue
            vistos.add(item.producto_id)
            detalle = existentes.get(item.producto_id)
            if detalle is not None:
                detalle.cantidad_pedida = item.cantidad_pedida
                if pedido.es_remito:
                    # En un remito lo editable es lo despachado.
                    detalle.cantidad_entregada = item.cantidad_entregada
                detalle.observaciones = item.observaciones
            else:
                session.add(
                    PedidoDetalle(
                        pedido_id=pedido.id,
                        producto_id=item.producto_id,
                        cantidad_pedida=item.cantidad_pedida,
                        cantidad_entregada=item.cantidad_entregada,
                        observaciones=item.observaciones,
                    )
                )
        for producto_id, detalle in existentes.items():
            if producto_id not in vistos:
                await session.delete(detalle)

    await session.commit()
    return await get_pedido(session, pedido.id)


async def registrar_entrega(session: AsyncSession, pedido: Pedido, payload: PedidoEntregaRequest) -> Pedido:
    if pedido.estado in ("ENTREGADO", "CANCELADO"):
        raise _unprocessable(f"Cannot register entrega for a pedido in estado '{pedido.estado}'")
    if pedido.fecha_facturado is not None:
        raise _unprocessable("Cannot register entrega for a facturado pedido")

    detalle_by_id = {d.id: d for d in pedido.detalles}
    for linea in payload.lineas:
        detalle = detalle_by_id.get(linea.detalle_id)
        if detalle is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"detalle_id {linea.detalle_id} does not belong to this pedido",
            )
        if linea.cantidad_entregada < detalle.cantidad_entregada:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"cantidad_entregada cannot decrease for detalle_id {linea.detalle_id}",
            )
        # cantidad_entregada puede superar cantidad_pedida — un pedido puede
        # entregarse de más respecto a lo originalmente solicitado.
        detalle.cantidad_entregada = linea.cantidad_entregada

    await session.commit()
    return await get_pedido(session, pedido.id)


async def _get_fabrica_sucursal(session: AsyncSession) -> Sucursal:
    # Origen por defecto de un envío tipo=SUCURSAL que no informa
    # origen_sucursal_id: la sucursal, al igual que un cliente, en general no
    # elige su propio origen — se despacha desde "la fábrica". Requiere que
    # exista exactamente una Sucursal tipo=FABRICA.
    result = await session.execute(select(Sucursal).where(Sucursal.tipo == "FABRICA"))
    fabricas = list(result.scalars().all())
    if len(fabricas) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No se pudo determinar la sucursal de origen (Fábrica): debe existir "
                f"exactamente una sucursal de tipo FABRICA (hay {len(fabricas)})"
            ),
        )
    return fabricas[0]


async def transition_estado(session: AsyncSession, pedido: Pedido, nuevo_estado: str) -> Pedido:
    current = pedido.estado

    if nuevo_estado == "CANCELADO":
        if current in ("ENTREGADO", "CANCELADO"):
            raise _unprocessable(f"Cannot cancel a pedido in estado '{current}'")
        if pedido.fecha_facturado is not None:
            raise _unprocessable("Cannot cancel a facturado pedido")
        pedido.estado = "CANCELADO"
        pedido.fecha_cancelado = datetime.now(timezone.utc)
        await session.commit()
        return await get_pedido(session, pedido.id)

    expected_next = PEDIDO_VALID_TRANSITIONS.get(current)
    if expected_next is None or expected_next != nuevo_estado:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition: '{current}' -> '{nuevo_estado}'. Expected next state: '{expected_next}'",
        )

    if nuevo_estado == "LISTO_PARA_ENTREGA" and not any(d.cantidad_entregada > 0 for d in pedido.detalles):
        # Un envío listo para entregar se imprime como remito: sin nada
        # entregado sería un remito vacío.
        raise _unprocessable("No hay ninguna entrega registrada para dejar el pedido listo para entrega")

    pedido.estado = nuevo_estado
    setattr(pedido, PEDIDO_ESTADO_TIMESTAMP_FIELD[nuevo_estado], datetime.now(timezone.utc))
    await session.commit()
    return await get_pedido(session, pedido.id)


async def registrar_facturacion(session: AsyncSession, pedido: Pedido, payload: PedidoFacturacionRequest) -> Pedido:
    if payload.fecha_facturado is not None and pedido.estado not in _FACTURABLE_ESTADOS:
        raise _unprocessable(f"Cannot facturar a pedido in estado '{pedido.estado}'")
    pedido.fecha_facturado = payload.fecha_facturado
    pedido.factura_referencia = payload.factura_referencia
    await session.commit()
    return await get_pedido(session, pedido.id)
