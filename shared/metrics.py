from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict

_METRICS: DefaultDict[str, list[float]] = defaultdict(list)


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = max(0, min(len(ordered) - 1, int((pct / 100) * len(ordered))))
    return float(ordered[rank])


def record_translation_metric(name: str, value: int | float) -> None:
    _METRICS[name].append(float(value))


def get_metrics_snapshot() -> dict[str, dict[str, float | int]]:
    snapshot: dict[str, dict[str, float | int]] = {}
    for metric_name, values in sorted(_METRICS.items()):
        if not values:
            snapshot[metric_name] = {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0, "sum": 0.0}
            continue

        total = sum(values)
        count = len(values)
        snapshot[metric_name] = {
            "count": count,
            "avg": round(total / count, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "p95": round(_percentile(values, 95), 4),
            "sum": round(total, 4),
        }
    return snapshot


def clear_metrics() -> None:
    _METRICS.clear()
