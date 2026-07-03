from fastapi import HTTPException, status

from app.auth import passport
from app.models.user import User


def require_role(*roles: str):
    def check(current_user: User = passport.authenticate("jwt")) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return current_user

    return check
