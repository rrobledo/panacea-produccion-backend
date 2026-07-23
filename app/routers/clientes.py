from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.clientes import Clientes
from app.schemas.clientes import ClienteCreate, ClienteRead

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("", response_model=list[ClienteRead])
async def list_clientes(
    nombre: str | None = None,
    q: str | None = None,
    limit: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    busqueda = nombre or q
    stmt = select(Clientes).order_by(Clientes.nom1)
    if busqueda:
        pattern = f"%{busqueda}%"
        stmt = stmt.where(or_(Clientes.nom1.ilike(pattern), Clientes.nom2.ilike(pattern)))
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return [ClienteRead.from_orm_row(row) for row in result.scalars().all()]


@router.post("", response_model=ClienteRead, status_code=status.HTTP_201_CREATED)
async def create_cliente(payload: ClienteCreate, session: AsyncSession = Depends(get_session)):
    cliente = Clientes(**payload.model_dump())
    session.add(cliente)
    await session.commit()
    await session.refresh(cliente)
    return ClienteRead.from_orm_row(cliente)


async def _get_cliente_or_404(session: AsyncSession, cliente_id: int) -> Clientes:
    cliente = await session.get(Clientes, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente not found")
    return cliente


@router.get("/{cliente_id}", response_model=ClienteRead)
async def get_cliente(cliente_id: int, session: AsyncSession = Depends(get_session)):
    return ClienteRead.from_orm_row(await _get_cliente_or_404(session, cliente_id))


@router.put("/{cliente_id}", response_model=ClienteRead)
async def update_cliente(cliente_id: int, payload: ClienteCreate, session: AsyncSession = Depends(get_session)):
    cliente = await _get_cliente_or_404(session, cliente_id)
    for field, value in payload.model_dump().items():
        setattr(cliente, field, value)
    await session.commit()
    await session.refresh(cliente)
    return ClienteRead.from_orm_row(cliente)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cliente(cliente_id: int, session: AsyncSession = Depends(get_session)):
    cliente = await _get_cliente_or_404(session, cliente_id)
    await session.delete(cliente)
    await session.commit()
