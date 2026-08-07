from datetime import date

from sqlalchemy import select

from app.models.crm_auditoria import CrmAuditoria


async def _create_contacto(client, headers) -> dict:
    response = await client.post("/crm/contactos", json={"tipo": "B2B", "nombre": "Juan"}, headers=headers)
    return response.json()


async def _create_vendedor(client, headers) -> dict:
    response = await client.post("/crm/vendedores", json={"nombre": "Carlos"}, headers=headers)
    return response.json()


async def test_create_visita(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    vendedor = await _create_vendedor(client, headers)

    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["contacto_id"] == contacto["id"]


async def test_create_visita_contacto_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    vendedor = await _create_vendedor(client, headers)

    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": 999999, "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 400


async def test_create_visita_vendedor_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": 999999, "fecha": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 400


async def test_create_visita_queda_auditada(client, auth_header, session):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    vendedor = await _create_vendedor(client, headers)

    await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )

    result = await session.execute(select(CrmAuditoria).where(CrmAuditoria.entidad == "Visita"))
    assert result.scalar_one() is not None


async def _create_visita(client, headers) -> dict:
    contacto = await _create_contacto(client, headers)
    vendedor = await _create_vendedor(client, headers)
    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )
    return response.json()


async def test_upload_adjunto_stores_content_in_db(client, auth_header):
    headers = await auth_header("vendedor")
    visita = await _create_visita(client, headers)

    response = await client.post(
        f"/crm/visitas/{visita['id']}/adjuntos",
        files={"file": ("nota.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "nota.jpg"
    assert body["tipo"] == "image/jpeg"
    assert "contenido" not in body
    adjunto_id = body["id"]

    listed = await client.get(f"/crm/visitas/{visita['id']}/adjuntos", headers=headers)
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == adjunto_id

    download = await client.get(f"/crm/visitas/{visita['id']}/adjuntos/{adjunto_id}", headers=headers)
    assert download.status_code == 200
    assert download.content == b"fake-image-bytes"
    assert download.headers["content-type"] == "image/jpeg"


async def test_upload_adjunto_accepts_audio_and_video(client, auth_header):
    headers = await auth_header("vendedor")
    visita = await _create_visita(client, headers)

    audio = await client.post(
        f"/crm/visitas/{visita['id']}/adjuntos",
        files={"file": ("nota.mp3", b"fake-audio", "audio/mpeg")},
        headers=headers,
    )
    assert audio.status_code == 201

    video = await client.post(
        f"/crm/visitas/{visita['id']}/adjuntos",
        files={"file": ("nota.mp4", b"fake-video", "video/mp4")},
        headers=headers,
    )
    assert video.status_code == 201


async def test_upload_adjunto_rejects_unsupported_type(client, auth_header):
    headers = await auth_header("vendedor")
    visita = await _create_visita(client, headers)

    response = await client.post(
        f"/crm/visitas/{visita['id']}/adjuntos",
        files={"file": ("nota.pdf", b"fake-pdf", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 400


async def test_upload_adjunto_visita_not_found(client, auth_header):
    headers = await auth_header("vendedor")
    response = await client.post(
        "/crm/visitas/999999/adjuntos",
        files={"file": ("nota.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 404


async def test_download_adjunto_not_found(client, auth_header):
    headers = await auth_header("vendedor")
    visita = await _create_visita(client, headers)
    response = await client.get(f"/crm/visitas/{visita['id']}/adjuntos/999999", headers=headers)
    assert response.status_code == 404
