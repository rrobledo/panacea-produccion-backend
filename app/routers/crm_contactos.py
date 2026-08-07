from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_catalogos import CrmCatalogoCreate, CrmCatalogoRead
from app.schemas.crm_contacto import CrmContactoCreate, CrmContactoRead, CrmContactoUpdate, CrmErpLinkRequest
from app.schemas.crm_empresa import CrmEmpresaCreate, CrmEmpresaRead, CrmEmpresaUpdate
from app.schemas.crm_vendedor import CrmVendedorCreate, CrmVendedorRead, CrmVendedorUpdate
from app.services import (
    crm_catalogos_service,
    crm_contacto_service,
    crm_empresa_service,
    crm_erp_integration_service,
    crm_vendedor_service,
)

contacto_router = APIRouter(prefix="/crm/contactos", tags=["crm-contactos"])
empresa_router = APIRouter(prefix="/crm/empresas", tags=["crm-contactos"])
catalogos_router = APIRouter(prefix="/crm/catalogos", tags=["crm-contactos"])
vendedor_router = APIRouter(prefix="/crm/vendedores", tags=["crm-contactos"])


@contacto_router.get("", response_model=list[CrmContactoRead])
async def list_contactos(
    empresa_id: int | None = None,
    tipo: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_contacto_service.list_contactos(session, empresa_id=empresa_id, tipo=tipo, q=q)


@contacto_router.post("", response_model=CrmContactoRead, status_code=201)
async def create_contacto(
    payload: CrmContactoCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_contacto_service.create_contacto(session, payload, usuario_id=current_user.id)


@contacto_router.get("/{contacto_id}", response_model=CrmContactoRead)
async def get_contacto(
    contacto_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_contacto_service.get_contacto(session, contacto_id)


@contacto_router.put("/{contacto_id}", response_model=CrmContactoRead)
async def update_contacto(
    contacto_id: int,
    payload: CrmContactoUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_contacto_service.update_contacto(session, contacto_id, payload, usuario_id=current_user.id)


@empresa_router.get("", response_model=list[CrmEmpresaRead])
async def list_empresas(
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_empresa_service.list_empresas(session, q=q)


@empresa_router.post("", response_model=CrmEmpresaRead, status_code=201)
async def create_empresa(
    payload: CrmEmpresaCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_empresa_service.create_empresa(session, payload)


@empresa_router.get("/{empresa_id}", response_model=CrmEmpresaRead)
async def get_empresa(
    empresa_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_empresa_service.get_empresa(session, empresa_id)


@empresa_router.put("/{empresa_id}", response_model=CrmEmpresaRead)
async def update_empresa(
    empresa_id: int,
    payload: CrmEmpresaUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_empresa_service.update_empresa(session, empresa_id, payload)


@catalogos_router.get("/rubros", response_model=list[CrmCatalogoRead])
async def list_rubros(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_authenticated())
):
    return await crm_catalogos_service.list_rubros(session)


@catalogos_router.post("/rubros", response_model=CrmCatalogoRead, status_code=201)
async def create_rubro(
    payload: CrmCatalogoCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_catalogos_service.create_rubro(session, payload)


@catalogos_router.get("/ciudades", response_model=list[CrmCatalogoRead])
async def list_ciudades(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_authenticated())
):
    return await crm_catalogos_service.list_ciudades(session)


@catalogos_router.post("/ciudades", response_model=CrmCatalogoRead, status_code=201)
async def create_ciudad(
    payload: CrmCatalogoCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_catalogos_service.create_ciudad(session, payload)


@catalogos_router.get("/origenes", response_model=list[CrmCatalogoRead])
async def list_origenes(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_authenticated())
):
    return await crm_catalogos_service.list_origenes(session)


@catalogos_router.post("/origenes", response_model=CrmCatalogoRead, status_code=201)
async def create_origen(
    payload: CrmCatalogoCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_catalogos_service.create_origen(session, payload)


@vendedor_router.get("", response_model=list[CrmVendedorRead])
async def list_vendedores(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_authenticated())
):
    return await crm_vendedor_service.list_vendedores(session)


@vendedor_router.post("", response_model=CrmVendedorRead, status_code=201)
async def create_vendedor(
    payload: CrmVendedorCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_vendedor_service.create_vendedor(session, payload)


@vendedor_router.get("/{vendedor_id}", response_model=CrmVendedorRead)
async def get_vendedor(
    vendedor_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_vendedor_service.get_vendedor(session, vendedor_id)


@vendedor_router.put("/{vendedor_id}", response_model=CrmVendedorRead)
async def update_vendedor(
    vendedor_id: int,
    payload: CrmVendedorUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_vendedor_service.update_vendedor(session, vendedor_id, payload)


@contacto_router.put("/{contacto_id}/erp-cliente", response_model=CrmContactoRead)
async def link_erp_cliente(
    contacto_id: int,
    payload: CrmErpLinkRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    await crm_erp_integration_service.link_erp_cliente(
        session, contacto_id, payload.erp_cliente_id, usuario_id=current_user.id
    )
    return await crm_contacto_service.get_contacto(session, contacto_id)


@contacto_router.get("/{contacto_id}/compras")
async def get_historial_compras(
    contacto_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_erp_integration_service.get_historial_compras(session, contacto_id)


@contacto_router.get("/{contacto_id}/productos-mas-consumidos")
async def get_productos_mas_consumidos(
    contacto_id: int,
    limite: int = 5,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_erp_integration_service.get_productos_mas_consumidos(session, contacto_id, limite)


@contacto_router.post("/autovincular-erp")
async def autovincular_erp(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    vinculados = await crm_erp_integration_service.autovincular_por_email(session)
    return {"contactos_vinculados": vinculados}
