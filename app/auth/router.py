from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.auth import passport
from app.auth.state import generate_state, verify_state
from app.auth.utils import create_token
from app.config import get_settings
from app.models.user import User
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


def _validate_redirect_uri(redirect_uri: str | None) -> str | None:
    if redirect_uri is None:
        return None
    settings = get_settings()
    normalized = redirect_uri.rstrip("/")
    if normalized not in settings.frontend_urls_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri not in allowed list",
        )
    return normalized


def _finish(user: User, redirect_uri: str | None = None) -> TokenResponse | RedirectResponse:
    settings = get_settings()
    token = create_token(user.id, user.email, user.role)
    target = redirect_uri or (next(iter(settings.frontend_urls_set), None))
    if target:
        return RedirectResponse(f"{target}?token={token}&user_id={user.id}")
    return TokenResponse(access_token=token, user_id=user.id, role=user.role)


@router.post("/register", response_model=TokenResponse, status_code=201, summary="Register with email + password")
def register(user: User = passport.authenticate("register")):
    return TokenResponse(access_token=create_token(user.id, user.email, user.role), user_id=user.id, role=user.role)


@router.post("/token", response_model=TokenResponse, summary="Login with email + password (OAuth2 password grant)")
def login_local(user: User = passport.authenticate("local")):
    return TokenResponse(access_token=create_token(user.id, user.email, user.role), user_id=user.id, role=user.role)


# ── Google ────────────────────────────────────────────────────────────────────

@router.get("/google", summary="Initiate Google Authorization Code flow", include_in_schema=True)
def google_initiate(redirect_uri: str | None = Query(None)):
    settings = get_settings()
    validated = _validate_redirect_uri(redirect_uri)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.base_url}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": generate_state(validated),
        "access_type": "online",
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@router.get("/google/callback", response_model=TokenResponse, summary="Google OAuth2 callback")
def google_callback(
    state: str | None = Query(None),
    user: User = passport.authenticate("google"),
):
    redirect_uri = verify_state(state) if state else None
    return _finish(user, redirect_uri)
