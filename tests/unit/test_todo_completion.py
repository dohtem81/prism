from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.api.app.analytics.metrics import build_room_metrics_summary
from scripts.bootstrap_dev import seed_demo_data
from shared.metrics import get_metrics_snapshot, record_translation_metric


def test_metrics_snapshot_records_delay_and_latency() -> None:
    record_translation_metric("queue_delay_ms", 120)
    record_translation_metric("provider_latency_ms", 230)
    record_translation_metric("end_to_end_delay_ms", 400)

    snapshot = get_metrics_snapshot()

    assert snapshot["queue_delay_ms"]["count"] == 1
    assert snapshot["queue_delay_ms"]["avg"] == 120.0
    assert snapshot["provider_latency_ms"]["count"] == 1
    assert snapshot["end_to_end_delay_ms"]["max"] == 400


def test_build_room_metrics_summary_uses_translation_telemetry() -> None:
    telemetry_rows = [
        MagicMock(room_id="room_1", target_lang="fr", status="success", queue_delay_ms=150, provider_latency_ms=100, end_to_end_delay_ms=300, estimated_cost_usd=0.0012),
        MagicMock(room_id="room_1", target_lang="de", status="failed", queue_delay_ms=250, provider_latency_ms=130, end_to_end_delay_ms=500, estimated_cost_usd=0.0009),
    ]

    summary = build_room_metrics_summary(room_id="room_1", telemetry_rows=telemetry_rows, window_hours=24)

    assert summary["room_id"] == "room_1"
    assert summary["total_messages"] == 2
    assert summary["success_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["estimated_cost_usd"] == 0.0021
    assert summary["queue_delay_ms"]["p95"] >= 250
    assert summary["language_breakdown"]["fr"]["success_count"] == 1


def test_seed_demo_data_creates_users_and_room() -> None:
    db = MagicMock()

    created = seed_demo_data(db)

    assert created["users"] >= 1
    assert created["room_id"]
    assert db.add.call_count >= 3
