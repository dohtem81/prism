from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.registration.app.api.health import router as health_router
from services.registration.app.api.register import router as register_router
from services.registration.app.infra.settings import settings
from shared.logging_utils import get_logger

logger = get_logger("prism.registration")

app = FastAPI(title=settings.app_name)

# Same-origin via the reverse proxy needs no CORS; only explicitly listed origins are allowed otherwise.
if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )

app.include_router(health_router)
app.include_router(register_router)
