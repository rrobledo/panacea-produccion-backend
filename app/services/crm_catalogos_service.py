from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_catalogos import CrmCiudad, CrmOrigen, CrmRubro
from app.schemas.crm_catalogos import CrmCatalogoCreate


async def list_rubros(session: AsyncSession) -> list[CrmRubro]:
    result = await session.execute(select(CrmRubro).order_by(CrmRubro.nombre))
    return list(result.scalars().all())


async def create_rubro(session: AsyncSession, payload: CrmCatalogoCreate) -> CrmRubro:
    rubro = CrmRubro(nombre=payload.nombre)
    session.add(rubro)
    await session.commit()
    await session.refresh(rubro)
    return rubro


async def list_ciudades(session: AsyncSession) -> list[CrmCiudad]:
    result = await session.execute(select(CrmCiudad).order_by(CrmCiudad.nombre))
    return list(result.scalars().all())


async def create_ciudad(session: AsyncSession, payload: CrmCatalogoCreate) -> CrmCiudad:
    ciudad = CrmCiudad(nombre=payload.nombre)
    session.add(ciudad)
    await session.commit()
    await session.refresh(ciudad)
    return ciudad


async def list_origenes(session: AsyncSession) -> list[CrmOrigen]:
    result = await session.execute(select(CrmOrigen).order_by(CrmOrigen.nombre))
    return list(result.scalars().all())


async def create_origen(session: AsyncSession, payload: CrmCatalogoCreate) -> CrmOrigen:
    origen = CrmOrigen(nombre=payload.nombre)
    session.add(origen)
    await session.commit()
    await session.refresh(origen)
    return origen
