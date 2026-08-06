from fastapi import FastAPI

from services.api.app.api.health import router as health_router
from services.api.app.api.messages import router as messages_router
from services.api.app.infra.settings import settings
from services.api.app.realtime.websocket_gateway import router as websocket_router

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(messages_router)
app.include_router(websocket_router)
