from fastapi import APIRouter

from app.auth import passport
from app.models.user import User
from app.schemas.profile import ProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfileResponse, summary="Obtener perfil del usuario conectado")
def get_me(current_user: User = passport.authenticate("jwt")):
    return current_user
