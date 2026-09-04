from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pedido import Pedido, PedidoDetalle
from app.models.productos import Productos
from app.models.remito import Remito, RemitoDetalle
from app.models.sucursal import Sucursal
from app.schemas.pedido import PedidoCreate, PedidoEntregaRequest, PedidoUpdate
from app.schemas.vocab import PEDIDO_ESTADO_TIMESTAMP_FIELD, PEDIDO_VALID_TRANSITIONS

# Estados that generate a Remito when reached — see
# specs/pedidos/spec.md "Generación automática de remito al completar la
# entrega" and design.md Decision 3.
_REMITO_GENERATING_ESTADOS = {"LISTO_PARA_ENTREGA", "ENTREGADO"}


def _pedido_stmt():
    # Explicit chain down to producto_base — ProductoRead serializes it, and
    # Productos.producto_base's own default lazy strategy doesn't reliably
    # fire once Productos is reached via another relationship's selectinload
    # chain in this async setup.
    return select(Pedido).options(
        selectinload(Pedido.detalles).selectinload(PedidoDetalle.producto).selectinload(Productos.producto_base)
    )


def _add_detalle_rows(session: AsyncSession, pedido_id: int, detalles) -> None:
    for item in detalles:
        if item.cantidad_pedida > 0:
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
    pedido = Pedido(fecha_carga=datetime.now(timezone.utc), **data)
    session.add(pedido)
    await session.flush()
    _add_detalle_rows(session, pedido.id, payload.detalles)
    await session.commit()
    return await get_pedido(session, pedido.id)


async def list_pedidos(
    session: AsyncSession,
    tipo: str | None = None,
    cliente_id: int | None = None,
    sucursal_id: int | None = None,
    estado: str | None = None,
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
    if estado is not None:
        stmt = stmt.where(Pedido.estado == estado)
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


def ensure_pendiente(pedido: Pedido) -> None:
    if pedido.estado != "PENDIENTE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only pedidos in 'PENDIENTE' estado can be edited or deleted",
        )


async def update_pedido(session: AsyncSession, pedido: Pedido, payload: PedidoUpdate) -> Pedido:
    data = payload.model_dump(exclude={"detalles"}, exclude_unset=True)
    for field, value in data.items():
        setattr(pedido, field, value)

    if payload.detalles is not None:
        # Merge by producto_id instead of delete-and-recreate, so
        # fecha_creacion is preserved on items that already existed — it
        # only advances for genuinely new lines. See PedidoDetalle.fecha_creacion.
        existentes = {d.producto_id: d for d in pedido.detalles}
        vistos: set[int] = set()
        for item in payload.detalles:
            if item.cantidad_pedida <= 0:
                continue
            vistos.add(item.producto_id)
            detalle = existentes.get(item.producto_id)
            if detalle is not None:
                detalle.cantidad_pedida = item.cantidad_pedida
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot register entrega for a pedido in estado '{pedido.estado}'",
        )

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
    # Origen implícito de los remitos TRANSFERENCIA generados a partir de un
    # Pedido tipo=SUCURSAL: la sucursal, al igual que un cliente, no elige
    # su propio origen — siempre se despacha desde "la fábrica". Requiere
    # que exista exactamente una Sucursal tipo=FABRICA.
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


async def _generar_remito(session: AsyncSession, pedido: Pedido) -> None:
    # Only the lines whose cantidad_entregada grew since the last remito
    # generated for this pedido — see design.md Decision 3.
    incrementos = [(d, d.cantidad_entregada - d.cantidad_remitida) for d in pedido.detalles]
    incrementos = [(d, inc) for d, inc in incrementos if inc > 0]
    if not incrementos:
        # No new delta. If a remito was already generated earlier for this
        # pedido (cantidad_remitida > 0 somewhere), this is just a later
        # step in the same flow with nothing new to ship (e.g. the whole
        # order was delivered in one shot at LISTO_PARA_ENTREGA, and
        # ENTREGADO is now just an administrative step) — skip silently
        # rather than blocking the transition. Only reject when nothing
        # was EVER delivered for this pedido, since generating the very
        # first remito with zero lines makes no sense.
        ya_genero_remito = any(d.cantidad_remitida > 0 for d in pedido.detalles)
        if not ya_genero_remito:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No hay ninguna entrega registrada para generar un remito",
            )
        return

    now = datetime.now(timezone.utc)
    # El pedido llegando a LISTO_PARA_ENTREGA/ENTREGADO ya documenta la
    # entrega en sí — el remito generado no necesita su propio seguimiento
    # de despacho/recepción, nace directamente en RECIBIDO.
    if pedido.tipo == "SUCURSAL":
        fabrica = await _get_fabrica_sucursal(session)
        remito = Remito(
            tipo="TRANSFERENCIA",
            origen_sucursal_id=fabrica.id,
            destino_sucursal_id=pedido.sucursal_id,
            pedido_id=pedido.id,
            vendedor=pedido.vendedor,
            fecha_carga=now,
            fecha_listo=now,
            fecha_despacho=now,
            fecha_recibido=now,
        )
    else:
        remito = Remito(
            tipo="VENTA",
            cliente_id=pedido.cliente_id,
            pedido_id=pedido.id,
            vendedor=pedido.vendedor,
            fecha_carga=now,
            fecha_listo=now,
            fecha_despacho=now,
            fecha_recibido=now,
        )
    session.add(remito)
    await session.flush()
    for detalle, incremento in incrementos:
        session.add(RemitoDetalle(remito_id=remito.id, producto_id=detalle.producto_id, cantidad=incremento))
        detalle.cantidad_remitida = detalle.cantidad_entregada


async def transition_estado(session: AsyncSession, pedido: Pedido, nuevo_estado: str) -> Pedido:
    current = pedido.estado

    if nuevo_estado == "CANCELADO":
        if current in ("ENTREGADO", "CANCELADO"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot cancel a pedido in estado '{current}'",
            )
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

    if nuevo_estado in _REMITO_GENERATING_ESTADOS:
        # Same transaction as the estado change: if generating the Remito
        # fails, the whole transition rolls back (see design.md Risks).
        await _generar_remito(session, pedido)

    pedido.estado = nuevo_estado
    setattr(pedido, PEDIDO_ESTADO_TIMESTAMP_FIELD[nuevo_estado], datetime.now(timezone.utc))
    await session.commit()
    return await get_pedido(session, pedido.id)
