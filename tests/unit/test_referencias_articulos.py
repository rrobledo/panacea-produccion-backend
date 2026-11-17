import pytest_asyncio
from sqlalchemy import select, text

from app.models.productos import Productos, ProductosRef

# (idarticulo, nombre, categoria, precio, activo)
ARTICULOS = [
    (100, "Medialuna", "Facturas", 500, 1),
    (101, "Coca Cola", "Otros", 1200, 1),
    (150, "Promo docena surtida", "Facturas", 5000, 1),
    (160, "Articulo viejo", "Facturas", 100, 0),
    (2100, "Medialuna CP", "Facturas", 550, 1),
    (2200, "Pan CP", "Panaderia", 900, 1),
    (4100, "Medialuna CBA", "Facturas", 600, 1),
]


@pytest_asyncio.fixture
async def articulos(session):
    """Siembra `articulos_final` sin tocar la base compartida.

    En una base sembrada desde producción `articulos_final` es la VIEW real
    (UNION sobre las tablas de caja, con datos que el fixture no trunca), y en
    una base inicializada con docker/init-db es una tabla. Una tabla temporal
    con el mismo nombre tapa a cualquiera de las dos (pg_temp va primero en el
    search_path) y sólo existe en la conexión del test, que es la misma que
    usa el cliente vía el override de `get_session`.
    """
    await session.execute(
        text(
            "CREATE TEMP TABLE articulos_final ("
            " idarticulo integer, nombre varchar(50), idcategoria integer,"
            " categoria varchar, precio numeric(100, 4), activo integer)"
        )
    )
    for idarticulo, nombre, categoria, precio, activo in ARTICULOS:
        await session.execute(
            text(
                "INSERT INTO articulos_final (idarticulo, nombre, categoria, precio, activo)"
                " VALUES (:i, :n, :c, :p, :a)"
            ),
            {"i": idarticulo, "n": nombre, "c": categoria, "p": precio, "a": activo},
        )
    await session.commit()


async def _producto(session, nombre, codigo):
    producto = Productos(
        codigo=codigo,
        nombre=nombre,
        utilidad=30,
        precio_actual=100,
        lote_produccion=10,
    )
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


@pytest_asyncio.fixture
async def productos(session, articulos):
    medialuna = await _producto(session, "Medialuna", "MED")
    vigilante = await _producto(session, "Vigilante", "VIG")
    canoncito = await _producto(session, "Cañoncito", "CAN")
    session.add_all(
        [
            ProductosRef(producto_id=medialuna.id, ref_id="100", unidad_conversion=1),
            ProductosRef(producto_id=medialuna.id, ref_id="150", unidad_conversion=6),
            ProductosRef(producto_id=vigilante.id, ref_id="150", unidad_conversion=6),
            ProductosRef(producto_id=medialuna.id, ref_id="2100", unidad_conversion=1),
            # Filas sucias que ya existen en producción no deben romper nada.
            ProductosRef(producto_id=vigilante.id, ref_id="ABC", unidad_conversion=1),
            ProductosRef(producto_id=vigilante.id, ref_id=None, unidad_conversion=1),
        ]
    )
    await session.commit()
    # Ids planos: los tests hacen `expire_all()` para releer de la base, y un
    # atributo expirado de un ORM se recargaría fuera del contexto async.
    return {"medialuna": medialuna.id, "vigilante": vigilante.id, "canoncito": canoncito.id}


def _ids(body):
    return [i["idarticulo"] for i in body["items"]]


# ── GET ──────────────────────────────────────────────────────────────────────


async def test_default_lista_solo_pendientes(client, productos):
    r = await client.get("/costos/referencias-articulos")
    assert r.status_code == 200
    body = r.json()
    assert _ids(body) == [101, 2200, 4100]
    assert all(i["estado"] == "pendiente" and i["relaciones"] == [] for i in body["items"])


async def test_vinculados_y_promo_en_una_sola_fila(client, productos):
    r = await client.get("/costos/referencias-articulos", params={"estado": "vinculado"})
    body = r.json()
    assert _ids(body) == [100, 150, 2100]
    promo = next(i for i in body["items"] if i["idarticulo"] == 150)
    assert promo["estado"] == "vinculado"
    assert sorted((x["producto_nombre"], x["unidad_conversion"]) for x in promo["relaciones"]) == [
        ("Medialuna", 6),
        ("Vigilante", 6),
    ]


async def test_todos_omite_inactivos(client, productos):
    body = (await client.get("/costos/referencias-articulos", params={"estado": "todos"})).json()
    assert _ids(body) == [100, 101, 150, 2100, 2200, 4100]


async def test_sucursal_por_rango(client, productos):
    body = (await client.get("/costos/referencias-articulos", params={"estado": "todos"})).json()
    sucursales = {i["idarticulo"]: i["sucursal"] for i in body["items"]}
    assert sucursales == {100: "VA", 101: "VA", 150: "VA", 2100: "CP", 2200: "CP", 4100: "CBA"}

    for sucursal, esperado in [("VA", [101]), ("CP", [2200]), ("CBA", [4100])]:
        body = (await client.get("/costos/referencias-articulos", params={"sucursal": sucursal})).json()
        assert _ids(body) == esperado


async def test_categoria_y_busqueda(client, productos):
    body = (
        await client.get("/costos/referencias-articulos", params={"estado": "todos", "categoria": "Facturas"})
    ).json()
    assert _ids(body) == [100, 150, 2100, 4100]

    body = (await client.get("/costos/referencias-articulos", params={"estado": "todos", "q": "medialuna"})).json()
    assert _ids(body) == [100, 2100, 4100]


async def test_ref_id_invalido_no_se_asocia(client, productos):
    body = (await client.get("/costos/referencias-articulos", params={"estado": "todos"})).json()
    ref_ids = [x["id"] for i in body["items"] for x in i["relaciones"]]
    assert len(ref_ids) == 4  # las filas 'ABC' y NULL no aparecen en ningún artículo


async def test_resumen_respeta_solo_sucursal(client, productos):
    body = (
        await client.get(
            "/costos/referencias-articulos", params={"estado": "vinculado", "categoria": "Otros", "q": "zzz"}
        )
    ).json()
    assert body["items"] == []
    assert body["resumen"] == {"total": 6, "vinculados": 3, "pendientes": 3}

    body = (await client.get("/costos/referencias-articulos", params={"sucursal": "CP"})).json()
    assert body["resumen"] == {"total": 2, "vinculados": 1, "pendientes": 1}


async def test_parametro_invalido(client, productos):
    r = await client.get("/costos/referencias-articulos", params={"sucursal": "XX"})
    assert r.status_code == 400


# ── PUT ──────────────────────────────────────────────────────────────────────


async def _refs_de(session, ref_id):
    rows = (
        await session.execute(select(ProductosRef).where(ProductosRef.ref_id == ref_id))
    ).scalars().all()
    return sorted((r.producto_id, r.unidad_conversion) for r in rows)


async def test_vincular_pendiente(client, session, productos):
    m = productos["medialuna"]
    r = await client.put(
        "/costos/referencias-articulos/4100", json={"relaciones": [{"producto_id": m, "unidad_conversion": 1}]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["estado"] == "vinculado"
    assert body["sucursal"] == "CBA"
    assert [(x["producto_id"], x["unidad_conversion"]) for x in body["relaciones"]] == [(m, 1)]
    session.expire_all()
    assert await _refs_de(session, "4100") == [(m, 1)]

    pendientes = (await client.get("/costos/referencias-articulos")).json()
    assert 4100 not in _ids(pendientes)


async def test_reemplazar_promo(client, session, productos):
    m, c = productos["medialuna"], productos["canoncito"]
    r = await client.put(
        "/costos/referencias-articulos/150",
        json={
            "relaciones": [
                {"producto_id": m, "unidad_conversion": 4},
                {"producto_id": c, "unidad_conversion": 2},
            ]
        },
    )
    assert r.status_code == 200
    session.expire_all()
    assert await _refs_de(session, "150") == sorted([(m, 4), (c, 2)])
    # El resto de los artículos queda intacto.
    assert await _refs_de(session, "100") == [(m, 1)]


async def test_reemplazo_borra_variantes_con_espacios(client, session, productos):
    m = productos["medialuna"]
    session.add(ProductosRef(producto_id=m, ref_id=" 2200 ", unidad_conversion=3))
    await session.commit()
    r = await client.put(
        "/costos/referencias-articulos/2200", json={"relaciones": [{"producto_id": m, "unidad_conversion": 1}]}
    )
    assert r.status_code == 200
    session.expire_all()
    assert await _refs_de(session, " 2200 ") == []
    assert await _refs_de(session, "2200") == [(m, 1)]


async def test_lista_vacia_deja_pendiente(client, session, productos):
    r = await client.put("/costos/referencias-articulos/150", json={"relaciones": []})
    assert r.status_code == 200
    assert r.json()["estado"] == "pendiente"
    assert r.json()["relaciones"] == []
    session.expire_all()
    assert await _refs_de(session, "150") == []


async def test_producto_inexistente_no_toca_nada(client, session, productos):
    m = productos["medialuna"]
    r = await client.put(
        "/costos/referencias-articulos/150",
        json={
            "relaciones": [
                {"producto_id": m, "unidad_conversion": 2},
                {"producto_id": 999999, "unidad_conversion": 1},
            ]
        },
    )
    assert r.status_code == 422
    assert "999999" in r.json()["detail"]
    session.expire_all()
    assert await _refs_de(session, "150") == sorted([(m, 6), (productos["vigilante"], 6)])


async def test_cantidad_invalida_y_repetido(client, session, productos):
    m = productos["medialuna"]
    r = await client.put(
        "/costos/referencias-articulos/100", json={"relaciones": [{"producto_id": m, "unidad_conversion": 0}]}
    )
    assert r.status_code == 422

    r = await client.put(
        "/costos/referencias-articulos/100",
        json={
            "relaciones": [
                {"producto_id": m, "unidad_conversion": 1},
                {"producto_id": m, "unidad_conversion": 2},
            ]
        },
    )
    assert r.status_code == 422
    session.expire_all()
    assert await _refs_de(session, "100") == [(m, 1)]


async def test_articulo_inactivo_o_inexistente(client, session, productos):
    m = productos["medialuna"]
    payload = {"relaciones": [{"producto_id": m, "unidad_conversion": 1}]}
    assert (await client.put("/costos/referencias-articulos/160", json=payload)).status_code == 404
    assert (await client.put("/costos/referencias-articulos/9999", json=payload)).status_code == 404
    session.expire_all()
    assert await _refs_de(session, "160") == []
