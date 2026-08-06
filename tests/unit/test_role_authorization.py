import pytest
from fastapi import HTTPException

from app.auth.dependencies import require_role
from app.models.user import User


def test_require_role_allows_matching_role():
    check = require_role("admin")
    user = User(id=1, email="a@example.com", role="admin")
    assert check(current_user=user) is user


def test_require_role_rejects_non_matching_role():
    check = require_role("admin")
    user = User(id=1, email="u@example.com", role="user")
    with pytest.raises(HTTPException) as exc_info:
        check(current_user=user)
    assert exc_info.value.status_code == 403


def test_require_role_accepts_multiple_roles():
    check = require_role("admin", "user")
    admin = User(id=1, email="a@example.com", role="admin")
    regular = User(id=2, email="u@example.com", role="user")
    assert check(current_user=admin) is admin
    assert check(current_user=regular) is regular


def test_require_role_accepts_commercial_roles():
    check = require_role("vendedor", "supervisor_comercial", "marketing", "gerencia")
    vendedor = User(id=1, email="v@example.com", role="vendedor")
    marketing = User(id=2, email="m@example.com", role="marketing")
    assert check(current_user=vendedor) is vendedor
    assert check(current_user=marketing) is marketing


def test_require_role_rejects_non_commercial_role_on_crm_endpoint():
    check = require_role("marketing", "gerencia", "admin")
    user = User(id=1, email="u@example.com", role="user")
    with pytest.raises(HTTPException) as exc_info:
        check(current_user=user)
    assert exc_info.value.status_code == 403
