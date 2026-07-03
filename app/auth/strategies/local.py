from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.strategies.base import BaseStrategy
from app.auth.utils import verify_password
from app.deps import get_session
from app.models.user import User


class LocalStrategy(BaseStrategy):
    def as_dependency(self) -> Callable:
        async def authenticate(
            form: OAuth2PasswordRequestForm = Depends(),
            session: AsyncSession = Depends(get_session),
        ) -> User:
            result = await session.execute(select(User).where(User.email == form.username))
            user = result.scalar_one_or_none()
            if not user or not user.password_hash:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not verify_password(form.password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user

        return authenticate
