import uuid

from fastapi import FastAPI, Request

from services.api.app.api.admin import router as admin_router
from services.api.app.api.health import router as health_router
from services.api.app.api.messages import router as messages_router
from services.api.app.api.rooms import router as rooms_router
from services.api.app.api.users import router as users_router
from services.api.app.infra.settings import settings
from services.api.app.realtime.websocket_gateway import router as websocket_router
from services.api.app.ui import router as ui_router
from shared.logging_utils import get_logger, reset_correlation_id, set_correlation_id

logger = get_logger("prism.api")

app = FastAPI(title=settings.app_name)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    token = set_correlation_id(correlation_id)
    request.state.correlation_id = correlation_id
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        reset_correlation_id(token)


@app.middleware("http")
async def access_logging_middleware(request: Request, call_next):
    logger.info("request_started", extra={"route": str(request.url.path), "method": request.method})
    try:
        response = await call_next(request)
        logger.info(
            "request_completed",
            extra={"route": str(request.url.path), "method": request.method, "status_code": response.status_code},
        )
        return response
    except Exception:
        logger.exception("request_failed", extra={"route": str(request.url.path), "method": request.method})
        raise


app.include_router(health_router)
app.include_router(messages_router)
app.include_router(rooms_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(websocket_router)
app.include_router(ui_router)
