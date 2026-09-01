from fastapi import FastAPI

from services.registration.app.api.health import router as health_router
from services.registration.app.api.register import router as register_router
from services.registration.app.infra.settings import settings
from shared.logging_utils import get_logger

logger = get_logger("prism.registration")

app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(register_router)
