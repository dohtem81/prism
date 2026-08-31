from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = max(0, min(len(ordered) - 1, int((pct / 100) * len(ordered))))
    return float(ordered[idx])


def build_room_metrics_summary(
    room_id: str,
    telemetry_rows: Iterable[Any],
    window_hours: int = 24,
) -> dict[str, Any]:
    rows = list(telemetry_rows)
    total_messages = len(rows)
    success_count = sum(1 for row in rows if getattr(row, "status", "") == "success")
    failed_count = total_messages - success_count

    queue_values = [float(row.queue_delay_ms) for row in rows if getattr(row, "queue_delay_ms", None) is not None]
    provider_values = [float(row.provider_latency_ms) for row in rows if getattr(row, "provider_latency_ms", None) is not None]
    end_to_end_values = [float(row.end_to_end_delay_ms) for row in rows if getattr(row, "end_to_end_delay_ms", None) is not None]
    cost_values = [float(row.estimated_cost_usd or 0) for row in rows if getattr(row, "estimated_cost_usd", None) is not None]

    language_breakdown: dict[str, dict[str, int | float]] = {}
    for row in rows:
        lang = getattr(row, "target_lang", "unknown")
        summary = language_breakdown.setdefault(lang, {"total": 0, "success_count": 0, "failed_count": 0, "estimated_cost_usd": 0.0})
        summary["total"] = int(summary["total"]) + 1
        if getattr(row, "status", "") == "success":
            summary["success_count"] = int(summary["success_count"]) + 1
        else:
            summary["failed_count"] = int(summary["failed_count"]) + 1
        summary["estimated_cost_usd"] = float(summary["estimated_cost_usd"]) + float(getattr(row, "estimated_cost_usd", 0) or 0)

    return {
        "room_id": room_id,
        "window_hours": window_hours,
        "total_messages": total_messages,
        "success_count": success_count,
        "failed_count": failed_count,
        "estimated_cost_usd": round(sum(cost_values), 6),
        "queue_delay_ms": {
            "p50": round(_percentile(queue_values, 50), 4) if queue_values else 0,
            "p95": round(_percentile(queue_values, 95), 4) if queue_values else 0,
            "avg": round(sum(queue_values) / len(queue_values), 4) if queue_values else 0,
        },
        "provider_latency_ms": {
            "p50": round(_percentile(provider_values, 50), 4) if provider_values else 0,
            "p95": round(_percentile(provider_values, 95), 4) if provider_values else 0,
            "avg": round(sum(provider_values) / len(provider_values), 4) if provider_values else 0,
        },
        "end_to_end_delay_ms": {
            "p50": round(_percentile(end_to_end_values, 50), 4) if end_to_end_values else 0,
            "p95": round(_percentile(end_to_end_values, 95), 4) if end_to_end_values else 0,
            "avg": round(sum(end_to_end_values) / len(end_to_end_values), 4) if end_to_end_values else 0,
        },
        "language_breakdown": {
            lang: {
                "total": int(details["total"]),
                "success_count": int(details["success_count"]),
                "failed_count": int(details["failed_count"]),
                "estimated_cost_usd": round(float(details["estimated_cost_usd"]), 6),
            }
            for lang, details in sorted(language_breakdown.items())
        },
    }
