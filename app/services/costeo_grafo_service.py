"""Costeo por capas sobre el grafo de procesos.

Ver openspec/changes/masa-procesos-y-maquinaria/{specs/reportes-costos/spec.md,
design.md D7 y D14} en el repo `panacea-produccion`.

El costo se arma en dos capas. La primera pertenece a la masa y se comparte;
la segunda pertenece a cada rama y no se comparte. Esa separación es la que
hace que dos productos de la misma masa no terminen costando lo mismo:

    costo_kg_masa = (Σ(cantidad × precio) + minutos de amasado × tarifa)
                    ÷ cantidad buena del lote

    costo_rama    = masa_consumida × costo_kg_masa
                  + minutos_directos × tarifa_centro
                  + minutos_maquina  × tarifa_maquina

    costo_unitario = costo_rama ÷ salida_buena_de_la_rama
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.centro_trabajo import CentroTrabajo
from app.models.insumos import Insumos
from app.models.maquinaria import ProcesoOperacion
from app.models.procesos import ROLES_SALIDA, Proceso, ProcesoLinea
from app.models.productos import Productos
from app.services import maquinaria_service

PROFUNDIDAD_MAXIMA = 10


@dataclass
class CostoArticulo:
    articulo_id: int
    nombre: str
    unidad_base: str
    costo_insumos: float = 0.0
    costo_mano_obra: float = 0.0
    costo_maquina: float = 0.0
    cantidad_buena: float = 0.0
    detalle: list[dict] = field(default_factory=list)
    pendientes: list[str] = field(default_factory=list)

    @property
    def costo_total(self) -> float:
        return self.costo_insumos + self.costo_mano_obra + self.costo_maquina

    @property
    def costo_unitario(self) -> float:
        return self.costo_total / self.cantidad_buena if self.cantidad_buena else 0.0


async def _tarifas_de_centro(session: AsyncSession) -> dict[str, float]:
    filas = (await session.execute(select(CentroTrabajo.nombre, CentroTrabajo.tarifa_hora))).all()
    return {nombre: float(tarifa or 0) for nombre, tarifa in filas}


async def _minutos_de_maquina(session: AsyncSession, proceso: Proceso, cantidad: float) -> float:
    """Costo de máquina de un proceso, a partir de sus operaciones y bachas."""
    total = 0.0
    for operacion in await maquinaria_service.operaciones_de_proceso(session, proceso.id):
        maquina = await maquinaria_service.resolver_maquina(
            session, operacion.maquina_tipo, operacion.capacidad_minima
        )
        if maquina is None:
            continue
        _bachas, minutos = maquinaria_service.minutos_de_operacion(operacion, maquina, cantidad)
        total += minutos / 60 * (maquina.tarifa_hora or 0)
    return total


async def _minutos_operario(session: AsyncSession, proceso: Proceso, cantidad: float) -> float:
    """Minutos de operario del proceso: las etapas con `requiere_operario`.

    Una etapa que ocupa máquina sin operario —la fermentación— suma tiempo de
    máquina y cero de mano de obra. Sin esa distinción el costo de mano de obra
    se infla y la capacidad del día se subestima, las dos cosas a la vez.
    """
    total = 0.0
    for operacion in await maquinaria_service.operaciones_de_proceso(session, proceso.id):
        if not operacion.requiere_operario:
            continue
        maquina = await maquinaria_service.resolver_maquina(
            session, operacion.maquina_tipo, operacion.capacidad_minima
        )
        _bachas, minutos = maquinaria_service.minutos_de_operacion(operacion, maquina, cantidad)
        total += minutos
    return total


async def costo_de_articulo(
    session: AsyncSession, articulo_id: int, _profundidad: int = 0
) -> CostoArticulo:
    """Costo por unidad de un artículo producido, recorriendo el grafo hacia atrás."""
    producto = (
        await session.execute(select(Productos).where(Productos.id == articulo_id))
    ).scalars().first()
    if producto is None:
        return CostoArticulo(articulo_id=articulo_id, nombre="", unidad_base="", pendientes=["No existe"])

    costo = CostoArticulo(
        articulo_id=producto.id, nombre=producto.nombre, unidad_base=producto.unidad_base
    )
    if _profundidad > PROFUNDIDAD_MAXIMA:
        costo.pendientes.append("El grafo encadena más procesos de los que el cálculo recorre")
        return costo

    fila = (
        await session.execute(
            select(Proceso, ProcesoLinea)
            .join(ProcesoLinea, ProcesoLinea.proceso_id == Proceso.id)
            .where(
                ProcesoLinea.producto_id == articulo_id,
                ProcesoLinea.rol.in_(ROLES_SALIDA),
                Proceso.vigente_hasta.is_(None),
            )
        )
    ).first()
    if fila is None:
        costo.pendientes.append(f"'{producto.nombre}' no es salida de ningún proceso vigente")
        return costo
    proceso, salida = fila

    tarifas = await _tarifas_de_centro(session)
    tarifa_centro = tarifas.get(proceso.responsable, 0)

    insumo_ids = [linea.insumo_id for linea in proceso.lineas if linea.rol == "ENTRADA" and linea.insumo_id]
    precios = {}
    if insumo_ids:
        precios = {
            i.id: (i.nombre, float(i.precio or 0))
            for i in (
                await session.execute(select(Insumos).where(Insumos.id.in_(insumo_ids)))
            ).scalars().all()
        }

    for linea in proceso.lineas:
        if linea.rol != "ENTRADA":
            continue
        if linea.insumo_id:
            nombre, precio = precios.get(linea.insumo_id, ("", 0.0))
            importe = linea.cantidad * precio
            costo.costo_insumos += importe
            costo.detalle.append(
                {"tipo": "INSUMO", "nombre": nombre, "cantidad": linea.cantidad, "importe": round(importe, 2)}
            )
        elif linea.producto_id:
            # Un semielaborado: su costo entra ya calculado, no se aplana a
            # insumos. Es lo que hace que cambiar el precio de la harina
            # recostee solo todo lo que consume esa masa.
            interno = await costo_de_articulo(session, linea.producto_id, _profundidad + 1)
            importe = interno.costo_unitario * linea.cantidad
            costo.costo_insumos += importe
            costo.pendientes.extend(interno.pendientes)
            costo.detalle.append(
                {
                    "tipo": "SEMIELABORADO", "nombre": interno.nombre,
                    "cantidad": linea.cantidad, "importe": round(importe, 2),
                }
            )
        costo.costo_mano_obra += (linea.minutos_directos or 0) / 60 * tarifa_centro

    minutos_operario = await _minutos_operario(session, proceso, proceso.lote_referencia)
    costo.costo_mano_obra += minutos_operario / 60 * tarifa_centro
    costo.costo_maquina = await _minutos_de_maquina(session, proceso, proceso.lote_referencia)

    # ── Reparto del costo conjunto (design.md D7) ──────────────────────────
    # El residuo sin valor no recibe costo: su peso se absorbe entre las salidas
    # buenas. Si no, el postre se vería más barato de lo que es.
    salidas = [linea for linea in proceso.lineas if linea.rol in ROLES_SALIDA]
    coproductos = [linea for linea in salidas if linea.rol == "COPRODUCTO"]
    if coproductos:
        peso_util = sum(_peso_de_salida(linea) for linea in salidas)
        peso_propio = _peso_de_salida(salida)
        proporcion = peso_propio / peso_util if peso_util else 0
        costo.costo_insumos *= proporcion
        costo.costo_mano_obra *= proporcion
        costo.costo_maquina *= proporcion

    costo.cantidad_buena = _cantidad_buena(salida, producto, proceso)
    if not costo.cantidad_buena:
        costo.pendientes.append(
            f"No se puede saber cuánto rinde '{producto.nombre}': falta el gramaje o la cantidad de la salida"
        )
    return costo


def _peso_de_salida(linea: ProcesoLinea) -> float:
    """Peso de una salida, para repartir el costo conjunto por peso."""
    if linea.gramaje_g and linea.cantidad:
        return linea.cantidad * linea.gramaje_g / 1000
    return linea.cantidad or 0


def _cantidad_buena(salida: ProcesoLinea, producto: Productos, proceso: Proceso) -> float:
    """Cuánto sale efectivamente de la rama, en la unidad base del artículo."""
    rendimiento = (salida.rendimiento_pct or 100) / 100
    merma = 1 - (salida.merma_pct or 0) / 100
    if salida.cantidad:
        return salida.cantidad * rendimiento * merma
    if salida.gramaje_g:
        # La salida no declara cantidad: se deduce del lote y el gramaje.
        bollos = proceso.lote_referencia * merma / (salida.gramaje_g / 1000)
        if producto.unidad_base == "UN":
            return bollos
        return bollos * salida.gramaje_g / 1000 * rendimiento
    return 0.0


async def costo_de_todos(session: AsyncSession) -> list[CostoArticulo]:
    productos = (
        await session.execute(
            select(Productos).where(
                Productos.naturaleza.in_(("SEMIELABORADO", "TERMINADO")),
                Productos.habilitado.is_(True),
            ).order_by(Productos.nombre)
        )
    ).scalars().all()
    return [await costo_de_articulo(session, p.id) for p in productos]
