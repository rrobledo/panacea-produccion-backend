from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ordenes_produccion import OrdenProduccion
from app.models.maquinaria import ProcesoOperacion
from app.models.procesos import ROLES_SALIDA, Proceso, ProcesoLinea
from app.models.productos import Productos
from app.schemas.procesos import ROLES_VALIDOS, TIPOS_VALIDOS, ProcesoWrite

# El grafo de procesos: ver openspec/changes/masa-procesos-y-maquinaria/
# {design.md D2, specs/procesos/spec.md} en el repo `panacea-produccion`.


def _error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _proceso_stmt():
    return select(Proceso)


async def get_proceso(session: AsyncSession, proceso_id: int) -> Proceso:
    proceso = (await session.execute(_proceso_stmt().where(Proceso.id == proceso_id))).scalars().first()
    if proceso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proceso no encontrado")
    return proceso


async def list_procesos(
    session: AsyncSession, tipo: str | None = None, incluir_historicas: bool = False
) -> list[Proceso]:
    stmt = _proceso_stmt()
    if not incluir_historicas:
        # Por defecto sólo las versiones vigentes: las históricas existen para
        # que una orden vieja se pueda releer, no para elegirlas.
        stmt = stmt.where(Proceso.vigente_hasta.is_(None))
    if tipo:
        stmt = stmt.where(Proceso.tipo == tipo)
    stmt = stmt.order_by(Proceso.codigo, Proceso.version)
    return list((await session.execute(stmt)).scalars().all())


# ── Validación que bloquea (task 2.10) ──────────────────────────────────────


def _validar_forma(payload: ProcesoWrite) -> None:
    if payload.tipo not in TIPOS_VALIDOS:
        raise _error(f"Tipo de proceso inválido: '{payload.tipo}'. Esperado uno de {sorted(TIPOS_VALIDOS)}")

    if payload.lote_referencia <= 0:
        raise _error("El lote de referencia tiene que ser mayor que cero")

    # Un lote mínimo por encima del de referencia significa que el proceso no se
    # puede correr nunca: toda corrida arrancaría por debajo del mínimo.
    if payload.lote_minimo is not None and payload.lote_minimo > payload.lote_referencia:
        raise _error(
            f"El lote mínimo ({payload.lote_minimo}) no puede superar al lote de referencia "
            f"({payload.lote_referencia}): las líneas se expresan por lote de referencia"
        )

    for indice, linea in enumerate(payload.lineas, start=1):
        if linea.rol not in ROLES_VALIDOS:
            raise _error(f"Línea {indice}: rol inválido '{linea.rol}'. Esperado uno de {sorted(ROLES_VALIDOS)}")
        # El XOR también está en la base (CHECK de la migración 0028); acá se
        # valida para devolver un mensaje que diga qué línea, en vez del error
        # opaco de Postgres.
        if (linea.insumo_id is None) == (linea.producto_id is None):
            raise _error(
                f"Línea {indice}: tiene que apuntar a un insumo o a un producto, no a los dos ni a ninguno"
            )

    salidas = [linea for linea in payload.lineas if linea.rol in ROLES_SALIDA]
    if not salidas:
        raise _error(
            "El proceso tiene que tener al menos una línea de SALIDA o COPRODUCTO: "
            "un proceso que no produce nada no se puede programar ni costear"
        )


async def _detectar_ciclo(session: AsyncSession, codigo: str, payload: ProcesoWrite) -> None:
    """Rechaza que un proceso dependa, directa o indirectamente, de su salida.

    Se recorre hacia atrás: de cada producto que este proceso consume se busca
    qué proceso lo produce, y así. Si en ese recorrido se vuelve a llegar al
    proceso que se está guardando, hay ciclo. Los nodos se identifican por
    `codigo` y no por `id` porque las versiones de un proceso son el mismo nodo
    del grafo.

    La validación de auto-referencia que ya existe en `ProductoForm.jsx` no
    alcanza: sólo mira un salto, y un ciclo puede tener tres procesos.
    """
    entradas = [linea.producto_id for linea in payload.lineas if linea.rol == "ENTRADA" and linea.producto_id]
    if not entradas:
        return

    # Qué proceso vigente produce cada producto.
    filas = (
        await session.execute(
            select(ProcesoLinea.producto_id, Proceso.codigo, Proceso.nombre)
            .join(Proceso, Proceso.id == ProcesoLinea.proceso_id)
            .where(
                ProcesoLinea.rol.in_(ROLES_SALIDA),
                ProcesoLinea.producto_id.is_not(None),
                Proceso.vigente_hasta.is_(None),
            )
        )
    ).all()
    productor: dict[int, tuple[str, str]] = {
        producto_id: (proceso_codigo, proceso_nombre) for producto_id, proceso_codigo, proceso_nombre in filas
    }

    # Qué productos consume cada proceso vigente.
    filas_entrada = (
        await session.execute(
            select(Proceso.codigo, ProcesoLinea.producto_id)
            .join(ProcesoLinea, ProcesoLinea.proceso_id == Proceso.id)
            .where(
                ProcesoLinea.rol == "ENTRADA",
                ProcesoLinea.producto_id.is_not(None),
                Proceso.vigente_hasta.is_(None),
            )
        )
    ).all()
    consume: dict[str, list[int]] = {}
    for proceso_codigo, producto_id in filas_entrada:
        consume.setdefault(proceso_codigo, []).append(producto_id)

    # Lo que este proceso produce. El recorrido hacia atrás tiene que chocar
    # contra esto: el proceso que se está guardando todavía no está en el
    # grafo, así que buscarlo por `codigo` sólo alcanza cuando se edita uno ya
    # existente. Un alta cierra el ciclo por sus salidas, no por su código.
    salidas_nuevas = {
        linea.producto_id for linea in payload.lineas if linea.rol in ROLES_SALIDA and linea.producto_id
    }

    def _buscar(producto_id: int, cadena: list[str], vistos: set[str]) -> list[str] | None:
        if producto_id in salidas_nuevas:
            return cadena
        origen = productor.get(producto_id)
        if origen is None:
            return None
        origen_codigo, origen_nombre = origen
        if origen_codigo == codigo:
            return cadena + [origen_nombre]
        if origen_codigo in vistos:
            return None
        vistos.add(origen_codigo)
        for siguiente in consume.get(origen_codigo, []):
            encontrado = _buscar(siguiente, cadena + [origen_nombre], vistos)
            if encontrado:
                return encontrado
        return None

    for producto_id in entradas:
        # Un proceso que consume su propia salida: el ciclo más corto posible.
        if producto_id in salidas_nuevas:
            raise _error(
                f"El proceso consume el mismo producto que produce (producto {producto_id}): "
                f"eso es un ciclo de un solo paso"
            )
        cadena = _buscar(producto_id, [payload.nombre], set())
        if cadena:
            raise _error("Ciclo en el grafo de procesos: " + " -> ".join(cadena))


# ── Advertencias que no bloquean (task 2.12) ────────────────────────────────


def _advertencias(proceso: Proceso) -> list[str]:
    avisos: list[str] = []

    entradas = [linea for linea in proceso.lineas if linea.rol == "ENTRADA"]
    salidas = [linea for linea in proceso.lineas if linea.rol in ROLES_SALIDA]

    if not entradas:
        avisos.append("El proceso no tiene ninguna línea de ENTRADA: no consume nada")

    # La suma de las ramas contra el lote. Es advertencia y no error porque hay
    # procesos legítimos que no cierran exacto, y porque las salidas quedan en
    # cero hasta que el relevamiento de F3 carga el gramaje: bloquear acá haría
    # inguardable todo lo que dejó el backfill.
    consumido = sum(linea.cantidad for linea in salidas)
    if consumido and abs(consumido - proceso.lote_referencia) > 0.001:
        diferencia = proceso.lote_referencia - consumido
        avisos.append(
            f"Las ramas suman {consumido:g} {proceso.lote_unidad} contra un lote de "
            f"{proceso.lote_referencia:g} {proceso.lote_unidad}: "
            f"{'sobran' if diferencia < 0 else 'faltan'} {abs(diferencia):g} {proceso.lote_unidad}"
        )

    # El gramaje se exige recién en F3 (tarea 4.3), cuando el relevamiento lo
    # haya cargado. Hasta entonces se avisa.
    sin_gramaje = [
        linea for linea in salidas
        if linea.producto and linea.producto.unidad_base == "UN" and not linea.gramaje_g
    ]
    for linea in sin_gramaje:
        avisos.append(
            f"La salida '{linea.producto.nombre}' se cuenta por unidad y no tiene gramaje cargado: "
            f"no se puede calcular cuánta masa consume"
        )

    return avisos


async def advertencias_de(proceso: Proceso) -> list[str]:
    return _advertencias(proceso)


# ── Escritura ───────────────────────────────────────────────────────────────


def _aplicar_campos(proceso: Proceso, payload: ProcesoWrite) -> None:
    proceso.codigo = payload.codigo
    proceso.nombre = payload.nombre
    proceso.tipo = payload.tipo
    proceso.responsable = payload.responsable
    proceso.lote_referencia = payload.lote_referencia
    proceso.lote_unidad = payload.lote_unidad
    proceso.lote_minimo = payload.lote_minimo
    proceso.lote_multiplo = payload.lote_multiplo
    proceso.minutos_setup = payload.minutos_setup


def _operaciones_de(payload: ProcesoWrite, proceso_id: int) -> list[ProcesoOperacion]:
    return [
        ProcesoOperacion(
            proceso_id=proceso_id,
            orden=operacion.orden if operacion.orden else indice,
            nombre=operacion.nombre,
            maquina_tipo=operacion.maquina_tipo,
            capacidad_minima=operacion.capacidad_minima,
            minutos_por_bacha=operacion.minutos_por_bacha,
            minutos_por_unidad=operacion.minutos_por_unidad,
            requiere_operario=operacion.requiere_operario,
            puede_solapar=operacion.puede_solapar,
        )
        for indice, operacion in enumerate(payload.operaciones)
    ]


async def _reemplazar_operaciones(session: AsyncSession, proceso_id: int, payload: ProcesoWrite) -> None:
    await session.execute(delete(ProcesoOperacion).where(ProcesoOperacion.proceso_id == proceso_id))
    for operacion in _operaciones_de(payload, proceso_id):
        session.add(operacion)


def _lineas_de(payload: ProcesoWrite) -> list[ProcesoLinea]:
    return [
        ProcesoLinea(
            rol=linea.rol,
            insumo_id=linea.insumo_id,
            producto_id=linea.producto_id,
            cantidad=linea.cantidad,
            unidad=linea.unidad,
            gramaje_g=linea.gramaje_g,
            porcentaje_panadero=linea.porcentaje_panadero,
            merma_pct=linea.merma_pct,
            rendimiento_pct=linea.rendimiento_pct,
            minutos_directos=linea.minutos_directos,
            minutos_maquina=linea.minutos_maquina,
            criterio_reparto=linea.criterio_reparto,
            orden=linea.orden if linea.orden else indice,
        )
        for indice, linea in enumerate(payload.lineas)
    ]


async def crear_proceso(session: AsyncSession, payload: ProcesoWrite) -> Proceso:
    _validar_forma(payload)
    await _detectar_ciclo(session, payload.codigo, payload)

    existente = (
        await session.execute(
            select(Proceso).where(Proceso.codigo == payload.codigo, Proceso.vigente_hasta.is_(None))
        )
    ).scalars().first()
    if existente is not None:
        raise _error(f"Ya existe un proceso vigente con el código '{payload.codigo}'")

    proceso = Proceso(version=1, vigente_desde=date.today())
    _aplicar_campos(proceso, payload)
    proceso.lineas = _lineas_de(payload)
    session.add(proceso)
    await session.flush()
    await _reemplazar_operaciones(session, proceso.id, payload)
    await session.commit()
    return await get_proceso(session, proceso.id)


async def _fue_usado_por_una_orden(session: AsyncSession, proceso_id: int) -> bool:
    encontrado = (
        await session.execute(
            select(OrdenProduccion.id).where(OrdenProduccion.proceso_id == proceso_id).limit(1)
        )
    ).scalars().first()
    return encontrado is not None


async def actualizar_proceso(session: AsyncSession, proceso: Proceso, payload: ProcesoWrite) -> Proceso:
    """Edita en el lugar, o crea una versión nueva si la receta ya se usó.

    Si alguna orden emitida referencia esta versión, editarla reescribiría el
    costo histórico de esa orden hacia atrás y en silencio, que es exactamente
    lo que pasa hoy y lo que el versionado viene a cortar (design.md D12). En
    ese caso se cierra la versión actual con `vigente_hasta` y se abre una
    nueva; la orden sigue apuntando a la que usó.

    Un proceso que ninguna orden usó todavía se edita en el lugar: versionar
    cada corrección de tipeo llenaría la tabla de versiones que nadie va a leer.
    """
    _validar_forma(payload)
    await _detectar_ciclo(session, payload.codigo, payload)

    if not await _fue_usado_por_una_orden(session, proceso.id):
        _aplicar_campos(proceso, payload)
        proceso.lineas = _lineas_de(payload)
        await _reemplazar_operaciones(session, proceso.id, payload)
        await session.commit()
        return await get_proceso(session, proceso.id)

    hoy = date.today()
    # El índice parcial `procesos_proceso_codigo_vigente_key` permite una sola
    # versión vigente por código, así que hay que cerrar la vieja y recién
    # después insertar la nueva.
    proceso.vigente_hasta = hoy
    await session.flush()

    nueva = Proceso(version=proceso.version + 1, vigente_desde=hoy)
    _aplicar_campos(nueva, payload)
    nueva.codigo = proceso.codigo  # el código identifica al proceso, no a la versión
    nueva.lineas = _lineas_de(payload)
    session.add(nueva)
    await session.flush()
    await _reemplazar_operaciones(session, nueva.id, payload)
    await session.commit()
    return await get_proceso(session, nueva.id)


async def eliminar_proceso(session: AsyncSession, proceso: Proceso) -> None:
    if await _fue_usado_por_una_orden(session, proceso.id):
        raise _error(
            "No se puede borrar un proceso que alguna orden ya usó: es la receta con la que "
            "se fabricó. Cerralo con una versión nueva en lugar de borrarlo."
        )
    await session.delete(proceso)
    await session.commit()


# ── Avance del relevamiento (task 4.5) ──────────────────────────────────────


async def pendientes_de_relevamiento(session: AsyncSession) -> dict:
    """Qué líneas de salida todavía no tienen el gramaje cargado.

    El gramaje no está en ninguna tabla del modelo viejo y no se puede deducir:
    `producto_base_id` dice de qué masa sale un producto, nunca cuánta consume.
    Por eso el backfill deja estas líneas en blanco y este endpoint mide cuánto
    falta del relevamiento de planta, que es el camino crítico del change.

    Sólo cuentan las salidas que de verdad lo necesitan:

    - Un producto vendido por kilo se calcula con el rendimiento del horno.
    - Una salida con `cantidad` cargada declara cuánto rinde un lote y la
      explosión la resuelve por regla de tres. Es el caso de los ELABORACION 1:1
      que dejó el backfill, y contarlos como pendientes inflaría el relevamiento
      con productos que no lo necesitan.
    """
    filas = (
        await session.execute(
            select(Proceso, ProcesoLinea, Productos)
            .join(ProcesoLinea, ProcesoLinea.proceso_id == Proceso.id)
            .join(Productos, Productos.id == ProcesoLinea.producto_id)
            .where(
                Proceso.vigente_hasta.is_(None),
                ProcesoLinea.rol.in_(ROLES_SALIDA),
                Productos.unidad_base == "UN",
                func.coalesce(ProcesoLinea.cantidad, 0) == 0,
            )
            .order_by(Proceso.codigo, ProcesoLinea.orden)
        )
    ).all()

    pendientes = []
    completas = 0
    for proceso, linea, producto in filas:
        if linea.gramaje_g:
            completas += 1
            continue
        pendientes.append(
            {
                "proceso_id": proceso.id,
                "proceso_codigo": proceso.codigo,
                "proceso_nombre": proceso.nombre,
                "linea_id": linea.id,
                "producto_id": producto.id,
                "producto_nombre": producto.nombre,
            }
        )

    total = completas + len(pendientes)
    # Procesos con al menos una rama sin gramaje: es la unidad en que se releva
    # (se va a la planta a medir una masa entera, no una rama suelta).
    procesos_pendientes = {p["proceso_id"] for p in pendientes}
    return {
        "lineas_totales": total,
        "lineas_completas": completas,
        "lineas_pendientes": len(pendientes),
        "procesos_pendientes": len(procesos_pendientes),
        "porcentaje": round(completas * 100 / total, 1) if total else 100.0,
        "pendientes": pendientes,
    }
