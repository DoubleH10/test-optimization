"""Nœud 2 — Normalisation et calcul de statistiques de référence.

Construit un résumé de la période : moyennes, médianes, percentiles, écarts-types.
Ces stats serviront ensuite à la détection statistique d'anomalies (z-score).
"""

import numpy as np
from loguru import logger

from infra_optimizer.models import MetricStats, PeriodSummary, PipelineState

METRICS_TO_TRACK = [
    "cpu_usage",
    "memory_usage",
    "latency_ms",
    "disk_usage",
    "network_in_kbps",
    "network_out_kbps",
    "io_wait",
    "thread_count",
    "active_connections",
    "error_rate",
    "temperature_celsius",
    "power_consumption_watts",
]


def normalization_node(state: PipelineState) -> PipelineState:
    """Calcule les statistiques descriptives sur l'ensemble des snapshots."""
    snapshots = state.raw_snapshots
    if not snapshots:
        logger.warning("Aucun snapshot à normaliser")
        return state

    metric_stats = []
    for metric in METRICS_TO_TRACK:
        values = np.array([getattr(s, metric) for s in snapshots], dtype=float)
        metric_stats.append(
            MetricStats(
                metric=metric,
                mean=float(np.mean(values)),
                median=float(np.median(values)),
                p95=float(np.percentile(values, 95)),
                p99=float(np.percentile(values, 99)),
                max=float(np.max(values)),
                min=float(np.min(values)),
                std=float(np.std(values)),
            )
        )

    # Calcul de l'uptime par service (pourcentage de snapshots où le service est "online")
    services = ["database", "api_gateway", "cache"]
    service_uptime = {}
    for svc in services:
        online_count = sum(
            1 for s in snapshots if getattr(s.service_status, svc) == "online"
        )
        service_uptime[svc] = round(100 * online_count / len(snapshots), 2)

    state.period_summary = PeriodSummary(
        period_start=min(s.timestamp for s in snapshots),
        period_end=max(s.timestamp for s in snapshots),
        total_snapshots=len(snapshots),
        metric_stats=metric_stats,
        service_uptime=service_uptime,
        incidents_count=0,  # rempli par le nœud service_status
    )
    logger.info(f"Normalisation terminée — {len(metric_stats)} métriques agrégées")
    return state
