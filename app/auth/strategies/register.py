from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.strategies.base import BaseStrategy
from app.auth.utils import hash_password
from app.deps import get_session
from app.models.user import User
from app.schemas.auth import RegisterRequest


class RegisterStrategy(BaseStrategy):
    def as_dependency(self) -> Callable:
        async def authenticate(
            body: RegisterRequest,
            session: AsyncSession = Depends(get_session),
        ) -> User:
            user = User(
                email=body.email,
                password_hash=hash_password(body.password),
                role="user",
                email_verified=False,
            )
            session.add(user)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="email already registered",
                )
            await session.refresh(user)
            return user

        return authenticate
