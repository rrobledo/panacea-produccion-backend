"""Maquinaria y carga del día.

Ver openspec/changes/masa-procesos-y-maquinaria/{specs/maquinaria/spec.md,
design.md D9-D13} en el repo `panacea-produccion`.

El alcance es el nivel N2 del diseño: **detectar** que el día no entra, no
planificar horarios. El salto de valor grande está entre no saber nada y saber
que la capacidad no alcanza; elegir a qué hora entra cada masa es un problema
de scheduling con restricciones y queda fuera (D9).
"""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maquinaria import (
    ESTADOS_MAQUINA,
    TIPOS_MAQUINA,
    UNIDADES_CAPACIDAD,
    UNIDADES_CONCURRENTES,
    Maquina,
    OrdenOperacion,
    ProcesoOperacion,
)
from app.models.ordenes_produccion import OrdenProduccion
from app.models.procesos import Proceso

# Horas del turno cuando la máquina no declara ventana horaria.
HORAS_TURNO_POR_DEFECTO = 6.0


def _error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


# ── Catálogo (task 6.4) ─────────────────────────────────────────────────────


async def list_maquinas(session: AsyncSession, tipo: str | None = None, solo_activas: bool = False):
    stmt = select(Maquina)
    if tipo:
        stmt = stmt.where(Maquina.tipo == tipo)
    if solo_activas:
        stmt = stmt.where(Maquina.estado == "ACTIVA")
    return list((await session.execute(stmt.order_by(Maquina.tipo, Maquina.nombre))).scalars().all())


async def get_maquina(session: AsyncSession, maquina_id: int) -> Maquina:
    maquina = (await session.execute(select(Maquina).where(Maquina.id == maquina_id))).scalars().first()
    if maquina is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Máquina no encontrada")
    return maquina


def _validar_maquina(payload) -> None:
    if payload.tipo not in TIPOS_MAQUINA:
        raise _error(f"Tipo de máquina inválido: '{payload.tipo}'. Esperado uno de {sorted(TIPOS_MAQUINA)}")
    if payload.estado not in ESTADOS_MAQUINA:
        raise _error(f"Estado inválido: '{payload.estado}'. Esperado uno de {sorted(ESTADOS_MAQUINA)}")
    if payload.capacidad <= 0:
        raise _error("La capacidad tiene que ser mayor que cero")
    # Una capacidad sin unidad no sirve para nada: 12 puede ser kilos, carros o
    # bandejas, y el modo de ocupación depende de cuál sea.
    if payload.capacidad_unidad not in UNIDADES_CAPACIDAD:
        raise _error(
            f"Unidad de capacidad inválida: '{payload.capacidad_unidad}'. "
            f"Esperado una de {sorted(UNIDADES_CAPACIDAD)}"
        )


async def crear_maquina(session: AsyncSession, payload) -> Maquina:
    _validar_maquina(payload)
    existente = (
        await session.execute(select(Maquina).where(Maquina.codigo == payload.codigo))
    ).scalars().first()
    if existente is not None:
        raise _error(f"Ya existe una máquina con el código '{payload.codigo}'")
    maquina = Maquina(**payload.model_dump())
    session.add(maquina)
    await session.commit()
    await session.refresh(maquina)
    return maquina


async def actualizar_maquina(session: AsyncSession, maquina: Maquina, payload) -> Maquina:
    _validar_maquina(payload)
    for campo, valor in payload.model_dump().items():
        setattr(maquina, campo, valor)
    await session.commit()
    await session.refresh(maquina)
    return maquina


async def eliminar_maquina(session: AsyncSession, maquina: Maquina) -> None:
    usada = (
        await session.execute(
            select(OrdenOperacion.id).where(OrdenOperacion.maquina_id == maquina.id).limit(1)
        )
    ).scalars().first()
    if usada is not None:
        raise _error(
            "No se puede borrar una máquina que alguna orden ya usó: es parte del registro de lo "
            "que pasó. Ponela en BAJA para sacarla de circulación."
        )
    await session.delete(maquina)
    await session.commit()


# ── Bachas y ocupación (tasks 6.5, 6.8, 6.9) ────────────────────────────────


def calcular_bachas(cantidad: float, capacidad: float) -> int:
    """Cuántas pasadas hacen falta.

    Una amasadora de 60 kg no amasa 162 kg de una vez: hace tres bachas. El
    tiempo de la operación no es el de una amasada, y el error se acumula en el
    costo (specs/maquinaria/spec.md).
    """
    if cantidad <= 0 or capacidad <= 0:
        return 0
    veces = Decimal(str(cantidad)) / Decimal(str(capacidad))
    return int(veces.to_integral_value(rounding="ROUND_CEILING"))


def minutos_de_operacion(operacion: ProcesoOperacion, maquina: Maquina, cantidad: float) -> tuple[int, int]:
    """(bachas, minutos) de una operación sobre una cantidad dada."""
    # Los `or 0` no son decoración: los defaults de columna sólo se aplican al
    # persistir, así que una operación recién construida en memoria llega con
    # los enteros en None.
    bachas = calcular_bachas(cantidad, maquina.capacidad) if maquina else 1
    bachas = max(bachas, 1)
    minutos = bachas * ((maquina.minutos_setup or 0) if maquina else 0)
    minutos += bachas * (operacion.minutos_por_bacha or 0)
    minutos += (operacion.minutos_por_unidad or 0) * cantidad
    minutos += (maquina.minutos_limpieza or 0) if maquina else 0
    return bachas, int(round(minutos))


async def resolver_maquina(
    session: AsyncSession, maquina_tipo: str, capacidad_minima: float | None
) -> Maquina | None:
    """La máquina concreta que satisface una operación, o None.

    Se elige la de menor capacidad entre las que alcanzan: usar la amasadora
    grande para una masa chica ocupa un recurso escaso sin necesidad.
    """
    candidatas = [
        m
        for m in await list_maquinas(session, tipo=maquina_tipo, solo_activas=True)
        if capacidad_minima is None or m.capacidad >= capacidad_minima
    ]
    if not candidatas:
        return None
    return min(candidatas, key=lambda m: m.capacidad)


async def operaciones_de_proceso(session: AsyncSession, proceso_id: int) -> list[ProcesoOperacion]:
    return list(
        (
            await session.execute(
                select(ProcesoOperacion)
                .where(ProcesoOperacion.proceso_id == proceso_id)
                .order_by(ProcesoOperacion.orden, ProcesoOperacion.id)
            )
        ).scalars().all()
    )


async def construir_operaciones_de_orden(
    session: AsyncSession, proceso_id: int | None, cantidad: float
) -> list[OrdenOperacion]:
    """Resuelve las operaciones de una orden al emitirla (task 6.7)."""
    if not proceso_id:
        return []
    resultado: list[OrdenOperacion] = []
    for operacion in await operaciones_de_proceso(session, proceso_id):
        maquina = await resolver_maquina(session, operacion.maquina_tipo, operacion.capacidad_minima)
        bachas, minutos = minutos_de_operacion(operacion, maquina, cantidad)
        resultado.append(
            OrdenOperacion(
                proceso_operacion_id=operacion.id,
                nombre=operacion.nombre,
                maquina_tipo=operacion.maquina_tipo,
                maquina_id=maquina.id if maquina else None,
                bachas=bachas,
                minutos=minutos,
                requiere_operario=operacion.requiere_operario,
                orden=operacion.orden,
            )
        )
    return resultado


# ── Tablero de carga del día (tasks 6.10 y 6.11) ────────────────────────────


def _horas_de_turno(maquina: Maquina) -> float:
    if not maquina.turno_desde or not maquina.turno_hasta:
        return HORAS_TURNO_POR_DEFECTO
    try:
        desde_h, desde_m = (int(x) for x in maquina.turno_desde.split(":"))
        hasta_h, hasta_m = (int(x) for x in maquina.turno_hasta.split(":"))
    except ValueError:
        return HORAS_TURNO_POR_DEFECTO
    minutos = (hasta_h * 60 + hasta_m) - (desde_h * 60 + desde_m)
    return max(minutos, 0) / 60


async def carga_del_dia(session: AsyncSession, fecha: date) -> dict:
    """Suma las operaciones de todas las órdenes de una fecha por tipo de máquina.

    Leído de arriba abajo tiene que decir algo accionable de una pasada: sobra
    amasadora, falta horno. Por eso se ordena por uso descendente.
    """
    filas = (
        await session.execute(
            select(OrdenOperacion)
            .join(OrdenProduccion, OrdenProduccion.id == OrdenOperacion.orden_id)
            .where(
                OrdenProduccion.fecha_fabricacion == fecha,
                OrdenProduccion.estado.in_(("ASIGNADA", "EN_PRODUCCION", "FINALIZADA")),
            )
        )
    ).scalars().all()

    maquinas = await list_maquinas(session, solo_activas=True)
    por_tipo: dict[str, list[Maquina]] = {}
    for maquina in maquinas:
        por_tipo.setdefault(maquina.tipo, []).append(maquina)

    requerido: dict[str, float] = {}
    for operacion in filas:
        requerido[operacion.maquina_tipo] = requerido.get(operacion.maquina_tipo, 0) + operacion.minutos

    tipos = sorted(set(por_tipo) | set(requerido))
    resultado = []
    for tipo in tipos:
        del_tipo = por_tipo.get(tipo, [])
        concurrente = bool(del_tipo) and del_tipo[0].capacidad_unidad in UNIDADES_CONCURRENTES
        capacidad_horas = sum(_horas_de_turno(m) for m in del_tipo)
        requerido_horas = requerido.get(tipo, 0) / 60
        # Una máquina concurrente atiende varias órdenes a la vez, así que su
        # capacidad en horas se multiplica por cuántas caben.
        if concurrente:
            capacidad_horas *= max(del_tipo[0].capacidad, 1)
        uso = (requerido_horas / capacidad_horas * 100) if capacidad_horas else (100 if requerido_horas else 0)
        if uso > 100:
            estado = "SOBRECAPACIDAD"
        elif uso >= 85:
            estado = "CUELLO_DE_BOTELLA"
        elif uso >= 70:
            estado = "AJUSTADO"
        else:
            estado = "HOLGADO"
        resultado.append(
            {
                "tipo": tipo,
                "maquinas": len(del_tipo),
                "concurrente": concurrente,
                "capacidad_horas": round(capacidad_horas, 2),
                "requerido_horas": round(requerido_horas, 2),
                "uso": round(uso, 1),
                "estado": estado,
            }
        )

    resultado.sort(key=lambda fila: fila["uso"], reverse=True)
    return {
        "fecha": fecha,
        "filas": resultado,
        "sobrecapacidad": [f for f in resultado if f["estado"] == "SOBRECAPACIDAD"],
    }


async def avisos_de_capacidad(session: AsyncSession, fecha: date, previews) -> list[str]:
    """Advertencia de sobrecapacidad antes de confirmar la generación (task 6.11).

    Suma lo que ya está comprometido para esa fecha más lo que las órdenes del
    preview agregarían, y avisa si algún tipo se pasa del turno. No bloquea: el
    jefe de planta puede saber algo que el sistema no.
    """
    carga = await carga_del_dia(session, fecha)
    capacidad = {f["tipo"]: f["capacidad_horas"] for f in carga["filas"]}
    acumulado = {f["tipo"]: f["requerido_horas"] for f in carga["filas"]}

    for preview in previews:
        proceso_id = getattr(preview, "proceso_id", None)
        if not proceso_id:
            continue
        cantidad = float(getattr(preview, "lote_producido", 0) or 0)
        for operacion in await operaciones_de_proceso(session, proceso_id):
            maquina = await resolver_maquina(session, operacion.maquina_tipo, operacion.capacidad_minima)
            _bachas, minutos = minutos_de_operacion(operacion, maquina, cantidad)
            acumulado[operacion.maquina_tipo] = acumulado.get(operacion.maquina_tipo, 0) + minutos / 60
            capacidad.setdefault(operacion.maquina_tipo, 0)

    avisos = []
    for tipo, horas in sorted(acumulado.items()):
        disponible = capacidad.get(tipo, 0)
        if disponible and horas > disponible:
            avisos.append(
                f"{tipo.capitalize()}: el día pide {horas:.1f} h y hay {disponible:.1f} h de turno "
                f"({horas - disponible:.1f} h de más)"
            )
        elif not disponible and horas:
            avisos.append(f"{tipo.capitalize()}: se necesitan {horas:.1f} h y no hay ninguna máquina activa")
    return avisos


# ── Validación blanda de lote contra capacidad (task 6.12) ──────────────────


async def advertencia_de_lote(session: AsyncSession, proceso: Proceso) -> str | None:
    """Cuánto se desperdicia de la última bacha con el lote declarado.

    Avisa, no prohíbe: hay masas legítimas que se hacen en dos máquinas
    distintas, y bloquear el guardado por esto sería peor que el problema.
    """
    operaciones = await operaciones_de_proceso(session, proceso.id)
    amasado = next((o for o in operaciones if o.maquina_tipo == "AMASADORA"), None)
    if amasado is None:
        return None
    maquina = await resolver_maquina(session, amasado.maquina_tipo, amasado.capacidad_minima)
    if maquina is None or maquina.capacidad <= 0:
        return None

    bachas = calcular_bachas(proceso.lote_referencia, maquina.capacidad)
    if bachas == 0:
        return None
    ultima = proceso.lote_referencia - (bachas - 1) * maquina.capacidad
    if abs(ultima - maquina.capacidad) < 0.001:
        return None
    return (
        f"El lote de {proceso.lote_referencia:g} {proceso.lote_unidad} entra en {bachas} bachas de "
        f"{maquina.nombre} ({maquina.capacidad:g} {maquina.capacidad_unidad}): la última corre a "
        f"{ultima:g} de {maquina.capacidad:g}"
    )
