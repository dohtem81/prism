import contextvars
import logging
from typing import Any

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "n/a"
        return True


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s correlation_id=%(correlation_id)s %(message)s",
    )

    root_logger = logging.getLogger()
    if not any(isinstance(handler, CorrelationIdFilter) for handler in root_logger.filters):
        root_logger.addFilter(CorrelationIdFilter())


def set_correlation_id(correlation_id: str | None) -> contextvars.Token[str | None]:
    return _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    _correlation_id_var.reset(token)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    logger = logging.getLogger(name)
    logger.propagate = True
    if not any(isinstance(filter_obj, CorrelationIdFilter) for filter_obj in logger.filters):
        logger.addFilter(CorrelationIdFilter())
    return logger


def log_event(level: int, message: str, **context: Any) -> None:
    logger = get_logger("prism")
    extra = {"correlation_id": get_correlation_id() or "n/a"}
    extra.update(context)
    logger.log(level, message, extra=extra)
