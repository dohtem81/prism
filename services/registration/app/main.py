from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.registration.app.api.health import router as health_router
from services.registration.app.api.register import router as register_router
from services.registration.app.infra.settings import settings
from shared.logging_utils import get_logger

logger = get_logger("prism.registration")

app = FastAPI(title=settings.app_name)

# Registration runs on its own origin/port; the webui (served by the api service) calls it directly from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(register_router)
