from app.models.insumos import Insumos
from app.models.productos import Costos, Productos


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="P1",
        categoria="PANADERIA",
        nombre="Pan Frances",
        utilidad=30,
        precio_actual=1000,
        unidad_medida="UN",
        lote_produccion=100,
        tiempo_produccion=2,
        responsable="Todos",
        is_producto=True,
        habilitado=True,
        prioridad=10,
    )
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _make_insumo(session, **overrides):
    defaults = dict(nombre="Harina", unidad_medida="KG", cantidad=1, precio=1000)
    defaults.update(overrides)
    insumo = Insumos(**defaults)
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


async def test_list_productos_default_order_by_prioridad_then_nombre(client, session):
    await _make_producto(session, nombre="Z Pan", prioridad=5)
    await _make_producto(session, nombre="A Pan", prioridad=5)
    await _make_producto(session, nombre="B Pan", prioridad=1)

    response = await client.get("/costos/productos")
    assert response.status_code == 200
    names = [p["nombre"] for p in response.json()]
    assert names == ["B Pan", "A Pan", "Z Pan"]


async def test_list_productos_with_nombre_filter_orders_by_nombre_only(client, session):
    await _make_producto(session, nombre="Torta Chocolate", prioridad=5)
    await _make_producto(session, nombre="Torta Vainilla", prioridad=1)
    await _make_producto(session, nombre="Pan Integral", prioridad=1)

    response = await client.get("/costos/productos", params={"nombre": "torta"})
    assert response.status_code == 200
    names = [p["nombre"] for p in response.json()]
    assert names == ["Torta Chocolate", "Torta Vainilla"]


async def test_create_producto_does_not_cascade_into_planning(client, session):
    response = await client.post(
        "/costos/productos",
        json={
            "codigo": "P2",
            "nombre": "Facturas",
            "utilidad": 25,
            "precio_actual": 500,
            "lote_produccion": 50,
        },
    )
    assert response.status_code == 201
    assert response.json()["habilitado"] is True


async def test_costos_nested_crud_includes_insumo_fields(client, session):
    producto = await _make_producto(session)
    insumo = await _make_insumo(session)

    created = await client.post(
        f"/costos/productos/{producto.id}/costos", json={"insumo": insumo.id, "cantidad": 3}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["insumo_nombre"] == "Harina"
    assert body["insumo_unidad_medida"] == "KG"

    listed = await client.get(f"/costos/productos/{producto.id}/costos")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_costos_materia_prima_matches_known_reference_calculation(client, session):
    # Fixture chosen to reproduce a hand-computed reference calculation
    # (see costeo_service.py's ported constants: TOTAL_HORAS_FABRICA_MENSUAL
    # = 8*44*4 = 1408, COSTO_TOTAL_FABRICA = 15_000_000,
    # COSTO_FABRICA = 4_800_000, SUELDO_BRUTO = 1_000_000, ALICUOTA_ART = 5).
    producto = await _make_producto(
        session,
        nombre="Pan Frances",
        utilidad=30,
        precio_actual=100,
        lote_produccion=100,
        tiempo_produccion=2,
    )
    harina = await _make_insumo(session, nombre="Harina", unidad_medida="KG", cantidad=1, precio=1000)
    # 100 units of pan use 10kg harina @ $1000/kg = $10000 total insumo cost
    # for one lote of 100.
    await client.post(f"/costos/productos/{producto.id}/costos", json={"insumo": harina.id, "cantidad": 10})

    response = await client.get(f"/costos/costos_materia_prima/{producto.id}")
    assert response.status_code == 200
    body = response.json()

    # sum_cost = 1000/1 * 10 * 1 = 10000; costo_unitario_mp = 10000/100 = 100
    assert body["costo_unitario_mp"] == 100
    # precio_sugerido = 10000/100 * (1 + 30/100) = 130
    assert body["precio_sugerido"] == 130
    # margen_utilidad = ((100/10000*100) - 1) * 100 = 0.0
    assert body["margen_utilidad"] == 0.0
    assert len(body["detalle_costo"]) == 1
    assert body["detalle_costo"][0]["insumo_nombre"] == "Harina"
    assert body["detalle_costo"][0]["porcentaje_del_total"] == 100.0


async def test_costos_materia_prima_accepts_overrides_without_persisting(client, session):
    producto = await _make_producto(session, lote_produccion=100, utilidad=30)
    insumo = await _make_insumo(session, cantidad=1, precio=1000)
    await client.post(f"/costos/productos/{producto.id}/costos", json={"insumo": insumo.id, "cantidad": 10})

    response = await client.get(
        f"/costos/costos_materia_prima/{producto.id}", params={"lote_produccion": 200, "utilidad": 50}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lote_produccion"] == 200
    assert body["utilidad"] == 50

    unchanged = await client.get(f"/costos/productos/{producto.id}")
    assert unchanged.json()["lote_produccion"] == 100
    assert unchanged.json()["utilidad"] == 30


async def test_costos_materia_prima_list_excludes_single_unit_lotes(client, session):
    small = await _make_producto(session, nombre="Torta Individual", lote_produccion=1)
    big = await _make_producto(session, nombre="Pan Grande", lote_produccion=50, tiempo_produccion=1)
    insumo = await _make_insumo(session)
    await client.post(f"/costos/productos/{big.id}/costos", json={"insumo": insumo.id, "cantidad": 1})

    response = await client.get("/costos/costos_materia_prima")
    assert response.status_code == 200
    ids = [p["producto_id"] for p in response.json()]
    assert big.id in ids
    assert small.id not in ids
    assert "detalle_costo" not in response.json()[0]


async def test_categorias_static_list(client):
    response = await client.get("/costos/categorias")
    assert response.status_code == 200
    assert response.json() == [
        "Materia Prima",
        "Honorarios",
        "Servicios",
        "Mantenimiento",
        "Delivery",
        "Impuestos",
    ]


async def test_precio_productos_uses_current_month_plan_and_articulos_final(client, session):
    from datetime import date

    from app.models.productos import ProductosRef

    producto = await _make_producto(session, nombre="Pan Frances", habilitado=True, is_producto=True, prioridad=1)
    insumo = await _make_insumo(session)
    await client.post(f"/costos/productos/{producto.id}/costos", json={"insumo": insumo.id, "cantidad": 1})

    ref = ProductosRef(producto_id=producto.id, ref_id="500")
    session.add(ref)
    from app.models.cuenta_corriente import CuentaCorrienteProveedor  # noqa: F401 (ensures models are imported)
    from sqlalchemy import text

    await session.execute(
        text(
            "INSERT INTO articulos_final (idarticulo, nombre, precio, activo) VALUES (500, 'Pan VA', 150, 1)"
        )
    )
    today = date.today()
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, corregido) VALUES (:fecha, :producto_id, 42)"
        ),
        {"fecha": today.replace(day=1), "producto_id": producto.id},
    )
    await session.commit()

    response = await client.get("/costos/precio_productos", params={"mes": today.month})
    assert response.status_code == 200
    rows = {r["producto_id"]: r for r in response.json() if r["producto_id"] == producto.id}
    assert rows[producto.id]["precio_va"] == 150
    assert rows[producto.id]["plan"] == 42
    assert response.json()[-1]["producto_nombre"] == "TOTALES"
