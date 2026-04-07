"""Nœud 4 — Détection d'incidents de service.

Identifie les snapshots où un service applicatif est en état "degraded" ou "offline",
et calcule la durée de chaque incident.
"""

from loguru import logger

from infra_optimizer.models import (
    Anomaly,
    AnomalyType,
    PipelineState,
    Severity,
)

SERVICES = ["database", "api_gateway", "cache"]


def service_status_node(state: PipelineState) -> PipelineState:
    """Détecte les services dégradés/offline et les ajoute aux anomalies."""
    snapshots = state.raw_snapshots
    if not snapshots:
        return state

    incidents = 0
    for snap in snapshots:
        for svc in SERVICES:
            status = getattr(snap.service_status, svc)
            if status == "offline":
                state.anomalies.append(
                    Anomaly(
                        timestamp=snap.timestamp,
                        metric=f"service.{svc}",
                        value=status,
                        expected_range="online",
                        anomaly_type=AnomalyType.SERVICE,
                        severity=Severity.CRITICAL,
                        description=f"Service {svc} hors ligne",
                    )
                )
                incidents += 1
            elif status == "degraded":
                state.anomalies.append(
                    Anomaly(
                        timestamp=snap.timestamp,
                        metric=f"service.{svc}",
                        value=status,
                        expected_range="online",
                        anomaly_type=AnomalyType.SERVICE,
                        severity=Severity.HIGH,
                        description=f"Service {svc} dégradé",
                    )
                )
                incidents += 1

    if state.period_summary:
        state.period_summary.incidents_count = incidents

    logger.info(f"Statuts de service : {incidents} incidents détectés")
    return state
