from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.strategies.base import BaseStrategy
from app.auth.utils import decode_token
from app.deps import get_session
from app.models.user import User

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class JWTStrategy(BaseStrategy):
    def as_dependency(self) -> Callable:
        async def authenticate(
            token: str = Depends(_oauth2_scheme),
            session: AsyncSession = Depends(get_session),
        ) -> User:
            try:
                payload = decode_token(token)
            except ExpiredSignatureError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="token expired",
                    headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
                )
            except JWTError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user = await session.get(User, int(payload["sub"]))
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="user not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user

        return authenticate
