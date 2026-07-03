from datetime import datetime, timedelta, timezone

from jose import jwt as jose_jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def signing_key() -> str:
    settings = get_settings()
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY is not configured")
    return settings.secret_key


def create_token(user_id: int, email: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.access_token_expire_days)
    payload = {"sub": str(user_id), "email": email, "role": role, "exp": expire}
    return jose_jwt.encode(payload, signing_key(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jose_jwt.decode(token, signing_key(), algorithms=["HS256"])
