"""Tests du nœud d'ingestion."""

import json

from infra_optimizer.models import PipelineState
from infra_optimizer.nodes.ingestion import ingestion_node


def test_ingestion_loads_valid_data(tmp_path):
    sample = [
        {
            "timestamp": "2023-10-01T12:00:00Z",
            "cpu_usage": 85.0,
            "memory_usage": 70.0,
            "latency_ms": 250.0,
            "disk_usage": 65.0,
            "network_in_kbps": 1200.0,
            "network_out_kbps": 900.0,
            "io_wait": 5.0,
            "thread_count": 150,
            "active_connections": 45,
            "error_rate": 0.02,
            "uptime_seconds": 360000,
            "temperature_celsius": 65.0,
            "power_consumption_watts": 250.0,
            "service_status": {
                "database": "online",
                "api_gateway": "degraded",
                "cache": "online",
            },
        }
    ]
    file_path = tmp_path / "metrics.json"
    file_path.write_text(json.dumps(sample))

    state = PipelineState()
    new_state = ingestion_node(state, str(file_path))

    assert len(new_state.raw_snapshots) == 1
    assert new_state.raw_snapshots[0].cpu_usage == 85.0
    assert new_state.raw_snapshots[0].service_status.api_gateway == "degraded"
    assert new_state.errors == []


def test_ingestion_handles_missing_file():
    state = PipelineState()
    new_state = ingestion_node(state, "/nonexistent/path.json")

    assert new_state.raw_snapshots == []
    assert len(new_state.errors) == 1
    assert "introuvable" in new_state.errors[0]


def test_ingestion_skips_invalid_entries(tmp_path):
    sample = [
        {
            "timestamp": "2023-10-01T12:00:00Z",
            "cpu_usage": 85.0,
            "memory_usage": 70.0,
            "latency_ms": 250.0,
            "disk_usage": 65.0,
            "network_in_kbps": 1200.0,
            "network_out_kbps": 900.0,
            "io_wait": 5.0,
            "thread_count": 150,
            "active_connections": 45,
            "error_rate": 0.02,
            "uptime_seconds": 360000,
            "temperature_celsius": 65.0,
            "power_consumption_watts": 250.0,
            "service_status": {
                "database": "online",
                "api_gateway": "online",
                "cache": "online",
            },
        },
        {"timestamp": "broken"},  # entrée invalide
    ]
    file_path = tmp_path / "metrics.json"
    file_path.write_text(json.dumps(sample))

    state = PipelineState()
    new_state = ingestion_node(state, str(file_path))

    assert len(new_state.raw_snapshots) == 1
