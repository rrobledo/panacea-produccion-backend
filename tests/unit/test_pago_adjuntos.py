from datetime import date


async def _create_pago(client) -> int:
    proveedor = (
        await client.post("/costos/proveedores", json={"nombre": "Pagos Adjuntos SA", "cuit": "20-44444444-4"})
    ).json()
    pago = (
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "importe": 500,
                "medios": [{"tipo": "EFECTIVO", "importe": 500}],
            },
        )
    ).json()
    return pago["id"]


async def test_upload_adjunto_stores_content_in_db(client):
    pago_id = await _create_pago(client)
    response = await client.post(
        f"/costos/pagos/{pago_id}/adjuntos",
        files={"file": ("comprobante.png", b"fake-png-bytes", "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "comprobante.png"
    assert body["tipo"] == "image/png"
    assert "contenido" not in body
    adjunto_id = body["id"]

    detail = await client.get(f"/costos/pagos/{pago_id}")
    assert len(detail.json()["adjuntos"]) == 1
    assert detail.json()["adjuntos"][0]["id"] == adjunto_id

    download = await client.get(f"/costos/pagos/{pago_id}/adjuntos/{adjunto_id}")
    assert download.status_code == 200
    assert download.content == b"fake-png-bytes"
    assert download.headers["content-type"] == "image/png"


async def test_download_adjunto_not_found(client):
    pago_id = await _create_pago(client)
    response = await client.get(f"/costos/pagos/{pago_id}/adjuntos/999999")
    assert response.status_code == 404


async def test_upload_adjunto_pago_not_found(client):
    response = await client.post(
        "/costos/pagos/999999/adjuntos",
        files={"file": ("comprobante.png", b"fake-png-bytes", "image/png")},
    )
    assert response.status_code == 404
