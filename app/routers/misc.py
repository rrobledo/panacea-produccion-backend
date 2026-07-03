from fastapi import APIRouter

router = APIRouter(tags=["misc"])

CATEGORIAS = ["Materia Prima", "Honorarios", "Servicios", "Mantenimiento", "Delivery", "Impuestos"]


@router.get("/categorias")
async def list_categorias() -> list[str]:
    return CATEGORIAS
