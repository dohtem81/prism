from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from shared.logging_utils import get_logger

logger = get_logger("prism.tracing")

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("span_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def get_span_id() -> str | None:
    return _span_id_var.get()


def set_trace_context(trace_id: str | None, span_id: str | None = None) -> tuple[contextvars.Token, contextvars.Token]:
    """Adopt an inbound trace context (e.g. from an HTTP header or Celery task kwarg)."""
    return _trace_id_var.set(trace_id), _span_id_var.set(span_id)


def reset_trace_context(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    trace_token, span_token = tokens
    _trace_id_var.reset(trace_token)
    _span_id_var.reset(span_token)


@contextmanager
def start_span(name: str, **attributes: Any) -> Iterator[str]:
    """Start a lightweight trace span, propagated via contextvars and emitted as structured logs."""
    trace_id = get_trace_id() or new_trace_id()
    parent_span_id = get_span_id()
    span_id = new_span_id()
    tokens = (_trace_id_var.set(trace_id), _span_id_var.set(span_id))

    base_fields = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "span_name": name,
    }
    logger.info("span_started", extra={**base_fields, **attributes})
    started_at = time.perf_counter()
    try:
        yield span_id
    except Exception as exc:
        logger.warning(
            "span_failed",
            extra={
                **base_fields,
                **attributes,
                "duration_ms": int((time.perf_counter() - started_at) * 1000),
                "error_type": type(exc).__name__,
            },
        )
        raise
    else:
        logger.info(
            "span_completed",
            extra={**base_fields, **attributes, "duration_ms": int((time.perf_counter() - started_at) * 1000)},
        )
    finally:
        reset_trace_context(tokens)
