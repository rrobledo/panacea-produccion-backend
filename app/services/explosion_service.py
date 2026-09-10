"""Explosión de demanda por el grafo de procesos.

Ver openspec/changes/masa-procesos-y-maquinaria/{design.md D3, specs/procesos/spec.md}
en el repo `panacea-produccion`.

En F3 esto se usa **sólo para comparar** contra el motor viejo: sirve para ver,
fecha por fecha, dónde cambian las cantidades de insumo antes de que cambien de
verdad. F4 (tarea 5.1) lo conecta al preview y a la generación.

La diferencia con el motor viejo cabe en una línea. El viejo hace

    escala = Σ cantidad_de_cada_producto ÷ lote_produccion_del_base

que sólo es correcto si todos los productos pesan lo mismo. Este suma en la
unidad del semielaborado:

    masa = Σ (cantidad × gramaje ÷ (1 − merma))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procesos import ROLES_SALIDA, Proceso, ProcesoLinea
from app.models.productos import Productos
from app.models.programacion import Programacion

# Un grafo mal cargado podría encadenar procesos sin fin. La validación de
# ciclos lo impide al guardar, pero el cálculo no debería colgarse si alguno se
# coló por una carga directa a la base.
PROFUNDIDAD_MAXIMA = 20


@dataclass
class ExplosionResultado:
    insumos: dict[int, float] = field(default_factory=dict)
    # Cuánta cantidad de cada semielaborado hace falta, en su unidad base.
    articulos: dict[int, float] = field(default_factory=dict)
    # Por qué una rama no se pudo calcular. Mientras haya pendientes, el
    # resultado es parcial y no sirve para comparar contra el motor viejo.
    pendientes: list[str] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return not self.pendientes


async def _mapa_de_salidas(session: AsyncSession) -> dict[int, tuple[Proceso, ProcesoLinea]]:
    """Qué proceso vigente produce cada producto, y con qué línea."""
    filas = (
        await session.execute(
            select(Proceso, ProcesoLinea)
            .join(ProcesoLinea, ProcesoLinea.proceso_id == Proceso.id)
            .where(
                ProcesoLinea.rol.in_(ROLES_SALIDA),
                ProcesoLinea.producto_id.is_not(None),
                Proceso.vigente_hasta.is_(None),
            )
        )
    ).all()
    return {linea.producto_id: (proceso, linea) for proceso, linea in filas}


def _consumo_de_la_rama(
    cantidad_pedida: float, producto: Productos, linea: ProcesoLinea
) -> float | None:
    """Cuánto del artículo de entrada consume esta rama, en la unidad del lote.

    Dos caminos según cómo se mida el producto:

    - Contado por unidad: cada bollo consume `gramaje_g`, y hay que reponer lo
      que se pierde al partir, de ahí la división por `(1 − merma)`.
    - Vendido por kilo: lo pedido son kilos ya horneados, así que primero se
      vuelve al peso crudo dividiendo por el rendimiento del horno, y recién
      después se aplica la merma de división.

    Devuelve None si falta el gramaje: el dato no se puede inventar y el
    resultado tiene que quedar marcado como incompleto.
    """
    merma = 1 - (linea.merma_pct or 0) / 100
    if merma <= 0:
        return None

    if producto.unidad_base == "UN":
        if not linea.gramaje_g:
            return None
        return cantidad_pedida * (linea.gramaje_g / 1000) / merma

    rendimiento = (linea.rendimiento_pct or 100) / 100
    if rendimiento <= 0:
        return None
    return cantidad_pedida / rendimiento / merma


async def explotar_demanda(
    session: AsyncSession, demanda: dict[int, float]
) -> ExplosionResultado:
    """Traduce una demanda de productos terminados en insumos, por el grafo."""
    resultado = ExplosionResultado()
    if not demanda:
        return resultado

    salidas = await _mapa_de_salidas(session)
    productos = {
        p.id: p for p in (await session.execute(select(Productos))).scalars().all()
    }

    pendiente_de_resolver = dict(demanda)
    for _ in range(PROFUNDIDAD_MAXIMA):
        if not pendiente_de_resolver:
            break
        siguiente: dict[int, float] = {}

        for producto_id, cantidad in pendiente_de_resolver.items():
            producto = productos.get(producto_id)
            if producto is None:
                resultado.pendientes.append(f"El producto {producto_id} no existe")
                continue

            origen = salidas.get(producto_id)
            if origen is None:
                resultado.pendientes.append(
                    f"'{producto.nombre}' no es salida de ningún proceso vigente"
                )
                continue
            proceso, linea = origen

            # Cuánto del artículo de entrada consume esta rama.
            if linea.gramaje_g or producto.unidad_base != "UN":
                consumo = _consumo_de_la_rama(cantidad, producto, linea)
                if consumo is None:
                    resultado.pendientes.append(
                        f"'{producto.nombre}' se cuenta por unidad y su línea no tiene gramaje cargado"
                    )
                    continue
                escala = consumo / proceso.lote_referencia if proceso.lote_referencia else None
            elif linea.cantidad:
                # Proceso 1:1 del modelo viejo: la salida declara cuánto rinde
                # un lote, así que la escala sale de la regla de tres directa.
                escala = cantidad / linea.cantidad
            else:
                resultado.pendientes.append(
                    f"'{producto.nombre}' se cuenta por unidad y su línea no tiene gramaje cargado"
                )
                continue

            if escala is None:
                resultado.pendientes.append(
                    f"El proceso '{proceso.nombre}' tiene lote de referencia cero"
                )
                continue

            for entrada in proceso.lineas:
                if entrada.rol != "ENTRADA":
                    continue
                aporte = entrada.cantidad * escala
                if entrada.insumo_id:
                    resultado.insumos[entrada.insumo_id] = (
                        resultado.insumos.get(entrada.insumo_id, 0) + aporte
                    )
                elif entrada.producto_id:
                    resultado.articulos[entrada.producto_id] = (
                        resultado.articulos.get(entrada.producto_id, 0) + aporte
                    )
                    siguiente[entrada.producto_id] = siguiente.get(entrada.producto_id, 0) + aporte

        pendiente_de_resolver = siguiente
    else:
        if pendiente_de_resolver:
            resultado.pendientes.append(
                "El grafo encadena más procesos de los que el cálculo recorre: revisar si hay un ciclo"
            )

    return resultado


async def demanda_de_la_fecha(session: AsyncSession, fecha: date) -> dict[int, float]:
    """Lo programado para una fecha, en la unidad de cada producto."""
    filas = (
        await session.execute(
            select(Programacion.producto_id, Programacion.plan).where(
                Programacion.fecha == fecha,
                Programacion.producto_id.is_not(None),
                Programacion.plan.is_not(None),
                Programacion.plan > 0,
            )
        )
    ).all()
    demanda: dict[int, float] = {}
    for producto_id, plan in filas:
        demanda[producto_id] = demanda.get(producto_id, 0) + float(plan)
    return demanda


# ── Plan de órdenes por el grafo (F4, tareas 5.1-5.5) ───────────────────────

from decimal import ROUND_HALF_UP, Decimal  # noqa: E402

from app.services import stock_service  # noqa: E402


@dataclass
class RamaPlan:
    """Una rama de la partición: qué producto sale y cuánta masa consume."""

    programacion_id: int
    producto_id: int
    producto_nombre: str
    cantidad_programada: float
    cantidad_planeada: float
    # Cuánta entrada consume esta rama, en la unidad del lote del proceso.
    masa: float
    # Cuántos bollos hay que cortar. None si el producto no se cuenta por unidad.
    bollos: int | None
    gramaje_g: float | None


@dataclass
class ProcesoPlan:
    proceso: Proceso
    responsable: str
    ramas: list[RamaPlan] = field(default_factory=list)
    # Lo que las ramas piden, antes de tocar stock y de redondear a lote.
    requerido: float = 0.0
    desde_stock: float = 0.0
    lote_a_producir: float = 0.0
    sobrante: float = 0.0
    insumos: dict[int, float] = field(default_factory=dict)
    # El artículo intermedio que este proceso consume, si consume alguno.
    articulo_entrada_id: int | None = None
    pendientes: list[str] = field(default_factory=list)


def redondear_a_lote(requerido: float, lote_minimo: float | None, lote_multiplo: float | None) -> float:
    """Lleva el requerimiento al múltiplo de lote, nunca por debajo del mínimo.

    Se redondea siempre hacia arriba: producir de menos deja la orden corta, y
    la masa que sobra tiene un destino — queda con saldo para la orden
    siguiente (design.md D5).
    """
    if requerido <= 0:
        return 0.0
    lote = max(requerido, float(lote_minimo or 0))
    if lote_multiplo:
        veces = Decimal(str(lote)) / Decimal(str(lote_multiplo))
        veces = veces.to_integral_value(rounding="ROUND_CEILING")
        lote = float(veces * Decimal(str(lote_multiplo)))
    return lote


def redondear_insumo(cantidad: float, unidad_medida: str | None) -> float:
    """Redondea según la unidad del insumo, sin piso de 1.

    El piso de 1 del motor viejo existía para que un insumo requerido no
    desapareciera de la orden al redondear a entero, pero sobre-reservaba
    sistemáticamente los insumos caros medidos en KG o LT: 0,4 kg se reservaban
    como 1. Con las cantidades no enteras permitidas para esas unidades el piso
    deja de hacer falta (design.md D6).
    """
    if cantidad <= 0:
        return 0.0
    if (unidad_medida or "").upper() == "UN":
        return float(Decimal(str(cantidad)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return float(Decimal(str(cantidad)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _bollos_de_la_rama(cantidad: float, producto: Productos, linea: ProcesoLinea) -> int | None:
    """Cuántos bollos hay que cortar para esa cantidad.

    Si el producto se cuenta por unidad, la cantidad pedida ya son bollos. Si se
    vende por kilo, hay que volver del peso horneado al bollo crudo.
    """
    if producto.unidad_base == "UN":
        return int(round(cantidad))
    if not linea.gramaje_g:
        return None
    rendimiento = (linea.rendimiento_pct or 100) / 100
    if rendimiento <= 0:
        return None
    return int(round(cantidad / (linea.gramaje_g / 1000 * rendimiento)))


async def planificar_ordenes(
    session: AsyncSession, items: list[tuple[int, Productos, float, float, str]]
) -> list[ProcesoPlan]:
    """Agrupa la demanda por proceso y resuelve stock, lote y explosión.

    `items` es una lista de `(programacion_id, producto, cantidad_programada,
    cantidad_planeada, responsable)`.

    La agrupación es por `(proceso, responsable)` — la misma forma que el motor
    viejo agrupaba por `(producto_base_id, responsable)`, así que el tablero
    semanal y la oblea siguen funcionando sin tocarse.
    """
    salidas = await _mapa_de_salidas(session)
    grupos: dict[tuple[int, str], ProcesoPlan] = {}

    for programacion_id, producto, cantidad_programada, cantidad, responsable in items:
        origen = salidas.get(producto.id)
        if origen is None:
            continue
        proceso, linea = origen
        clave = (proceso.id, responsable)
        plan = grupos.get(clave)
        if plan is None:
            plan = ProcesoPlan(proceso=proceso, responsable=responsable)
            grupos[clave] = plan

        if linea.gramaje_g or producto.unidad_base != "UN":
            consumo = _consumo_de_la_rama(cantidad, producto, linea)
            if consumo is None:
                plan.pendientes.append(
                    f"'{producto.nombre}' se cuenta por unidad y su línea no tiene gramaje cargado"
                )
                continue
        elif linea.cantidad:
            # Proceso 1:1 heredado del modelo viejo: la salida declara cuánto
            # rinde un lote, así que la regla de tres es directa.
            consumo = cantidad / linea.cantidad * proceso.lote_referencia
        else:
            plan.pendientes.append(
                f"'{producto.nombre}' se cuenta por unidad y su línea no tiene gramaje cargado"
            )
            continue

        plan.ramas.append(
            RamaPlan(
                programacion_id=programacion_id,
                producto_id=producto.id,
                producto_nombre=producto.nombre,
                cantidad_programada=cantidad_programada,
                cantidad_planeada=cantidad,
                masa=consumo,
                bollos=_bollos_de_la_rama(cantidad, producto, linea),
                gramaje_g=linea.gramaje_g,
            )
        )
        plan.requerido += consumo

    for plan in grupos.values():
        await _resolver_lote_e_insumos(session, plan)

    return [plan for plan in grupos.values() if plan.ramas]


async def _resolver_lote_e_insumos(session: AsyncSession, plan: ProcesoPlan) -> None:
    proceso = plan.proceso
    entrada_articulo = next(
        (linea for linea in proceso.lineas if linea.rol == "ENTRADA" and linea.producto_id), None
    )

    if entrada_articulo is None:
        # El proceso produce directamente lo que se pide: no hay semielaborado
        # intermedio, y el lote se redondea contra los parámetros del proceso.
        plan.lote_a_producir = redondear_a_lote(plan.requerido, proceso.lote_minimo, proceso.lote_multiplo)
        plan.sobrante = plan.lote_a_producir - plan.requerido
        escala = plan.lote_a_producir / proceso.lote_referencia if proceso.lote_referencia else 0
        _sumar_insumos(plan, proceso, escala)
        return

    # El proceso consume un semielaborado: lo que ya haya en stock se descuenta
    # antes de decidir cuánto amasar (design.md D5).
    plan.articulo_entrada_id = entrada_articulo.producto_id
    disponible = await stock_service.disponible_de_articulo(session, entrada_articulo.producto_id)
    plan.desde_stock = min(max(disponible, 0.0), plan.requerido)
    a_producir = plan.requerido - plan.desde_stock

    productor = (await _mapa_de_salidas(session)).get(entrada_articulo.producto_id)
    if productor is None:
        plan.pendientes.append(
            f"El artículo que consume '{proceso.nombre}' no es salida de ningún proceso vigente"
        )
        plan.lote_a_producir = a_producir
        return
    elaboracion, _linea_salida = productor

    plan.lote_a_producir = redondear_a_lote(a_producir, elaboracion.lote_minimo, elaboracion.lote_multiplo)
    plan.sobrante = plan.lote_a_producir - a_producir

    escala_elab = plan.lote_a_producir / elaboracion.lote_referencia if elaboracion.lote_referencia else 0
    _sumar_insumos(plan, elaboracion, escala_elab)

    # Insumos propios de la partición (relleno, semillas), que escalan con lo
    # que se parte y no con lo que se amasa.
    escala_propia = plan.requerido / proceso.lote_referencia if proceso.lote_referencia else 0
    _sumar_insumos(plan, proceso, escala_propia)


def _sumar_insumos(plan: ProcesoPlan, proceso: Proceso, escala: float) -> None:
    for linea in proceso.lineas:
        if linea.rol != "ENTRADA" or not linea.insumo_id:
            continue
        plan.insumos[linea.insumo_id] = plan.insumos.get(linea.insumo_id, 0) + linea.cantidad * escala
