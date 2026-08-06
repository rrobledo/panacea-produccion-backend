from app.services import crm_club_socio_service
from app.services.club_socios_client import SocioInfo


async def _create_contacto(client, headers) -> dict:
    response = await client.post("/crm/contactos", json={"tipo": "B2C", "nombre": "Juan"}, headers=headers)
    return response.json()


class _FakeClient:
    def __init__(self, info: SocioInfo | None = None, raises: bool = False):
        self.info = info
        self.raises = raises

    async def fetch_socio(self, socio_id: str) -> SocioInfo | None:
        if self.raises:
            raise RuntimeError("club de socios API is down")
        return self.info


async def test_get_estado_ausente_sin_vinculo(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.get(f"/crm/contactos/{contacto['id']}/club-socio", headers=headers)
    assert response.status_code == 200
    assert response.json() is None


async def test_get_estado_expone_datos_cacheados(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    await client.put(f"/crm/contactos/{contacto['id']}/club-socio", json={"socio_id": "SOC-1"}, headers=headers)

    response = await client.get(f"/crm/contactos/{contacto['id']}/club-socio", headers=headers)
    assert response.status_code == 200
    assert response.json()["socio_id"] == "SOC-1"


async def test_refresh_actualiza_valores(client, auth_header, session):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    await client.put(f"/crm/contactos/{contacto['id']}/club-socio", json={"socio_id": "SOC-2"}, headers=headers)

    fake_client = _FakeClient(info=SocioInfo(categoria="ORO", puntos=500, fecha_alta=None))
    refreshed = await crm_club_socio_service.refresh_all(session, client=fake_client)
    assert refreshed == 1

    response = await client.get(f"/crm/contactos/{contacto['id']}/club-socio", headers=headers)
    assert response.json()["categoria"] == "ORO"
    assert response.json()["puntos"] == 500


async def test_refresh_usa_valor_cacheado_si_cliente_falla(client, auth_header, session):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    await client.put(f"/crm/contactos/{contacto['id']}/club-socio", json={"socio_id": "SOC-3"}, headers=headers)
    await crm_club_socio_service.refresh_all(
        session, client=_FakeClient(info=SocioInfo(categoria="PLATA", puntos=100, fecha_alta=None))
    )

    refreshed = await crm_club_socio_service.refresh_all(session, client=_FakeClient(raises=True))
    assert refreshed == 0

    response = await client.get(f"/crm/contactos/{contacto['id']}/club-socio", headers=headers)
    assert response.json()["categoria"] == "PLATA"


async def test_cron_refresh_club_socios_requires_cron_secret(client):
    response = await client.post("/internal/cron/crm-refresh-club-socios")
    assert response.status_code == 401
