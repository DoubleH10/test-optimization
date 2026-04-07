"""Nœud 3 — Détection d'anomalies déterministe.

Choix architectural : on N'utilise PAS de LLM ici. La détection d'anomalies
sur des séries temporelles structurées est un problème statistique classique
que les seuils + z-scores résolvent mieux que n'importe quel LLM (plus rapide,
plus reproductible, plus auditable).

Le LLM intervient dans le nœud suivant pour CONTEXTUALISER les anomalies
trouvées, pas pour les détecter.
"""

import numpy as np
from loguru import logger

from infra_optimizer.config import settings
from infra_optimizer.models import (
    Anomaly,
    AnomalyType,
    MetricSnapshot,
    PipelineState,
    Severity,
)


# ============================================================================
# Règles de seuil par métrique
# ============================================================================

THRESHOLD_RULES = {
    "cpu_usage": {
        "threshold": settings.cpu_threshold,
        "expected": "0-85%",
        "severity_high": 95.0,
        "severity_critical": 98.0,
    },
    "memory_usage": {
        "threshold": settings.memory_threshold,
        "expected": "0-85%",
        "severity_high": 92.0,
        "severity_critical": 97.0,
    },
    "latency_ms": {
        "threshold": settings.latency_threshold_ms,
        "expected": "<300ms",
        "severity_high": 500.0,
        "severity_critical": 1000.0,
    },
    "disk_usage": {
        "threshold": settings.disk_threshold,
        "expected": "0-85%",
        "severity_high": 90.0,
        "severity_critical": 95.0,
    },
    "error_rate": {
        "threshold": settings.error_rate_threshold,
        "expected": "<5%",
        "severity_high": 0.10,
        "severity_critical": 0.20,
    },
    "temperature_celsius": {
        "threshold": settings.temperature_threshold,
        "expected": "<75°C",
        "severity_high": 82.0,
        "severity_critical": 90.0,
    },
    "io_wait": {
        "threshold": settings.io_wait_threshold,
        "expected": "<10",
        "severity_high": 20.0,
        "severity_critical": 35.0,
    },
}


def _classify_severity(value: float, rule: dict) -> Severity:
    if value >= rule.get("severity_critical", float("inf")):
        return Severity.CRITICAL
    if value >= rule.get("severity_high", float("inf")):
        return Severity.HIGH
    return Severity.MEDIUM


def _detect_threshold_anomalies(snapshots: list[MetricSnapshot]) -> list[Anomaly]:
    """Détection par seuils absolus."""
    anomalies = []
    for snap in snapshots:
        for metric, rule in THRESHOLD_RULES.items():
            value = getattr(snap, metric)
            if value > rule["threshold"]:
                anomalies.append(
                    Anomaly(
                        timestamp=snap.timestamp,
                        metric=metric,
                        value=value,
                        expected_range=rule["expected"],
                        anomaly_type=AnomalyType.THRESHOLD,
                        severity=_classify_severity(value, rule),
                        description=(
                            f"{metric} = {value} dépasse le seuil "
                            f"{rule['threshold']} (attendu : {rule['expected']})"
                        ),
                    )
                )
    return anomalies


def _detect_statistical_anomalies(
    snapshots: list[MetricSnapshot], state: PipelineState
) -> list[Anomaly]:
    """Détection par z-score sur les métriques numériques.

    Un z-score élevé indique un point qui s'écarte significativement de la moyenne
    de la période, même si le seuil absolu n'est pas dépassé.
    """
    if not state.period_summary:
        return []

    stats_by_metric = {ms.metric: ms for ms in state.period_summary.metric_stats}
    anomalies = []
    threshold = settings.zscore_threshold

    for metric in ["latency_ms", "error_rate", "io_wait", "active_connections"]:
        if metric not in stats_by_metric:
            continue
        ms = stats_by_metric[metric]
        if ms.std == 0:
            continue
        for snap in snapshots:
            value = getattr(snap, metric)
            zscore = (value - ms.mean) / ms.std
            if zscore > threshold:
                anomalies.append(
                    Anomaly(
                        timestamp=snap.timestamp,
                        metric=metric,
                        value=value,
                        expected_range=f"~{ms.mean:.1f} ± {ms.std:.1f}",
                        anomaly_type=AnomalyType.STATISTICAL,
                        severity=Severity.HIGH if zscore > 4 else Severity.MEDIUM,
                        description=(
                            f"{metric} = {value} avec un z-score de {zscore:.2f} "
                            f"(moyenne période : {ms.mean:.1f})"
                        ),
                    )
                )
    return anomalies


def anomaly_detection_node(state: PipelineState) -> PipelineState:
    """Lance la détection d'anomalies déterministe (seuils + statistiques)."""
    snapshots = state.raw_snapshots
    if not snapshots:
        return state

    threshold_anomalies = _detect_threshold_anomalies(snapshots)
    statistical_anomalies = _detect_statistical_anomalies(snapshots, state)

    state.anomalies.extend(threshold_anomalies)
    state.anomalies.extend(statistical_anomalies)

    logger.info(
        f"Détection d'anomalies : {len(threshold_anomalies)} par seuil, "
        f"{len(statistical_anomalies)} statistiques"
    )
    return state
