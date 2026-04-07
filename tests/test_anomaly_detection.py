"""Tests du nœud de détection d'anomalies."""

from datetime import datetime

from infra_optimizer.models import (
    MetricSnapshot,
    PipelineState,
    ServiceStatus,
    Severity,
)
from infra_optimizer.nodes.anomaly_detection import anomaly_detection_node
from infra_optimizer.nodes.normalization import normalization_node
from infra_optimizer.nodes.service_status import service_status_node


def _make_snapshot(**overrides) -> MetricSnapshot:
    base = {
        "timestamp": datetime(2023, 10, 1, 12, 0, 0),
        "cpu_usage": 50.0,
        "memory_usage": 50.0,
        "latency_ms": 100.0,
        "disk_usage": 50.0,
        "network_in_kbps": 1000.0,
        "network_out_kbps": 1000.0,
        "io_wait": 3.0,
        "thread_count": 100,
        "active_connections": 30,
        "error_rate": 0.01,
        "uptime_seconds": 100000,
        "temperature_celsius": 60.0,
        "power_consumption_watts": 200.0,
        "service_status": ServiceStatus(
            database="online", api_gateway="online", cache="online"
        ),
    }
    base.update(overrides)
    return MetricSnapshot(**base)


def test_detects_cpu_threshold_anomaly():
    state = PipelineState(
        raw_snapshots=[
            _make_snapshot(),
            _make_snapshot(cpu_usage=95.0),
        ]
    )
    state = normalization_node(state)
    state = anomaly_detection_node(state)

    cpu_anomalies = [a for a in state.anomalies if a.metric == "cpu_usage"]
    assert len(cpu_anomalies) == 1
    assert cpu_anomalies[0].severity in (Severity.HIGH, Severity.MEDIUM)


def test_detects_critical_cpu():
    state = PipelineState(raw_snapshots=[_make_snapshot(cpu_usage=99.0)])
    state = normalization_node(state)
    state = anomaly_detection_node(state)

    assert any(a.severity == Severity.CRITICAL for a in state.anomalies)


def test_detects_service_offline():
    state = PipelineState(
        raw_snapshots=[
            _make_snapshot(
                service_status=ServiceStatus(
                    database="offline", api_gateway="online", cache="online"
                )
            )
        ]
    )
    state = normalization_node(state)
    state = service_status_node(state)

    service_anomalies = [a for a in state.anomalies if a.metric == "service.database"]
    assert len(service_anomalies) == 1
    assert service_anomalies[0].severity == Severity.CRITICAL


def test_no_anomalies_on_clean_data():
    state = PipelineState(raw_snapshots=[_make_snapshot() for _ in range(10)])
    state = normalization_node(state)
    state = anomaly_detection_node(state)
    state = service_status_node(state)

    assert state.anomalies == []
