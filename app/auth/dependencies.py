from fastapi import HTTPException, status

from app.auth import passport
from app.models.user import User


def require_role(*roles: str):
    def check(current_user: User = passport.authenticate("jwt")) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return current_user

    return check


def require_authenticated():
    """Any valid JWT is accepted regardless of its `role` claim.

    Used by the CRM routers, which used to be gated by `require_role(*CRM_ROLES)`
    — that role restriction was explicitly removed while keeping the JWT
    requirement itself, per a follow-up request (see
    openspec/changes/crm-comercial-integrado/tasks.md).
    """

    def check(current_user: User = passport.authenticate("jwt")) -> User:
        return current_user

    return check
