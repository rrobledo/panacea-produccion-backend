from datetime import date


async def _create_compra(client) -> int:
    proveedor = (
        await client.post("/costos/proveedores", json={"nombre": "Adjuntos SA", "cuit": "20-55555555-5"})
    ).json()
    compra = (
        await client.post(
            "/costos/compras",
            json={
                "proveedor_id": proveedor["id"],
                "tipo_comprobante": "TICKET",
                "numero": "1",
                "fecha": date.today().isoformat(),
            },
        )
    ).json()
    return compra["id"]


async def test_upload_adjunto_stores_content_in_db(client):
    compra_id = await _create_compra(client)
    response = await client.post(
        f"/costos/compras/{compra_id}/adjuntos",
        files={"file": ("recibo.jpg", b"fake-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "recibo.jpg"
    assert body["tipo"] == "image/jpeg"
    assert "contenido" not in body
    adjunto_id = body["id"]

    detail = await client.get(f"/costos/compras/{compra_id}")
    assert len(detail.json()["adjuntos"]) == 1
    assert detail.json()["adjuntos"][0]["id"] == adjunto_id

    download = await client.get(f"/costos/compras/{compra_id}/adjuntos/{adjunto_id}")
    assert download.status_code == 200
    assert download.content == b"fake-image-bytes"
    assert download.headers["content-type"] == "image/jpeg"


async def test_download_adjunto_not_found(client):
    compra_id = await _create_compra(client)
    response = await client.get(f"/costos/compras/{compra_id}/adjuntos/999999")
    assert response.status_code == 404


async def test_upload_adjunto_compra_not_found(client):
    response = await client.post(
        "/costos/compras/999999/adjuntos",
        files={"file": ("recibo.jpg", b"fake-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 404
