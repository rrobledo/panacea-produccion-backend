import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.auth.router import router as auth_router
from app.config import get_settings
from app.routers import (
    clientes,
    costeo,
    cron,
    cuenta_corriente,
    insumos,
    misc,
    planning,
    produccion_stats,
    productos,
    profile,
    programacion,
    proveedores,
    remitos,
    ventas,
)

logger = logging.getLogger("panacea_produccion_backend")

app = FastAPI(
    title="Panacea Producción Backend",
    description="Costing/production API — FastAPI port of panacea-backend's costos domain.",
    version="0.1.0",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    # Log the exception server-side only — never echo DB errors (which can
    # include connection strings/credentials) back to the client.
    logger.exception("Database error handling %s %s", request.method, request.url.path)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"})


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Mounted under /costos to match panacea-front's existing base URL
# (`<host>/costos/...`), so only the host needs to change for ported routes.
app.include_router(insumos.router, prefix="/costos")
app.include_router(proveedores.router, prefix="/costos")
app.include_router(cuenta_corriente.router, prefix="/costos")
app.include_router(cuenta_corriente.resumen_router, prefix="/costos")
app.include_router(productos.router, prefix="/costos")
app.include_router(costeo.router, prefix="/costos")
app.include_router(misc.router, prefix="/costos")
app.include_router(clientes.router, prefix="/costos")
app.include_router(remitos.router, prefix="/costos")
app.include_router(produccion_stats.router, prefix="/costos")
app.include_router(ventas.router, prefix="/costos")
app.include_router(planning.router, prefix="/costos")
app.include_router(programacion.router, prefix="/costos")
app.include_router(cron.router)
app.include_router(auth_router)
app.include_router(profile.router)
