"""Nœud 5 — Détection de tendances (séries temporelles).

Complémentaire à la détection ponctuelle : identifie les métriques qui
se dégradent PROGRESSIVEMENT sur plusieurs snapshots consécutifs.

Pourquoi c'est important : un CTO ne veut pas seulement savoir "il y a eu
un pic à 14h", il veut savoir "mon disque se remplit de 2% par jour et
sera saturé dans 4 jours".

Algorithme : pente de régression linéaire sur une fenêtre glissante.
Si la pente dépasse un seuil et que le coefficient de corrélation est fort,
on flag une tendance.
"""

from datetime import datetime

import numpy as np
from loguru import logger

from infra_optimizer.models import (
    Anomaly,
    AnomalyType,
    MetricSnapshot,
    PipelineState,
    Severity,
)

# Métriques où une tendance croissante est problématique
GROWTH_METRICS = {
    "cpu_usage": {"unit": "%", "threshold_slope": 0.5, "name": "CPU"},
    "memory_usage": {"unit": "%", "threshold_slope": 0.4, "name": "mémoire"},
    "disk_usage": {"unit": "%", "threshold_slope": 0.3, "name": "disque"},
    "latency_ms": {"unit": "ms", "threshold_slope": 2.0, "name": "latence"},
    "error_rate": {"unit": "", "threshold_slope": 0.002, "name": "taux d'erreur"},
    "temperature_celsius": {"unit": "°C", "threshold_slope": 0.3, "name": "température"},
}

WINDOW_SIZE = 10  # Nombre de snapshots dans la fenêtre glissante
CORRELATION_THRESHOLD = 0.75  # Force minimale de la corrélation pour flagger


def _linear_regression(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Calcule la pente et le coefficient de corrélation (Pearson)."""
    if len(x) < 2 or np.std(y) == 0:
        return 0.0, 0.0
    slope = float(np.polyfit(x, y, 1)[0])
    correlation = float(np.corrcoef(x, y)[0, 1])
    return slope, correlation


def _detect_metric_trend(
    snapshots: list[MetricSnapshot], metric: str, config: dict
) -> list[Anomaly]:
    """Détecte les tendances de dégradation sur une métrique donnée."""
    if len(snapshots) < WINDOW_SIZE:
        return []

    values = np.array([getattr(s, metric) for s in snapshots], dtype=float)
    anomalies = []

    # Fenêtre glissante
    for i in range(len(values) - WINDOW_SIZE + 1):
        window = values[i : i + WINDOW_SIZE]
        x = np.arange(WINDOW_SIZE, dtype=float)
        slope, corr = _linear_regression(x, window)

        # On flag si la pente monte ET la corrélation est forte
        if slope > config["threshold_slope"] and corr > CORRELATION_THRESHOLD:
            start_snap = snapshots[i]
            end_snap = snapshots[i + WINDOW_SIZE - 1]
            delta = window[-1] - window[0]

            severity = (
                Severity.HIGH
                if delta > window[0] * 0.3  # +30% sur la fenêtre
                else Severity.MEDIUM
            )

            anomalies.append(
                Anomaly(
                    timestamp=end_snap.timestamp,
                    metric=metric,
                    value=round(float(window[-1]), 2),
                    expected_range=f"stable ~{window[0]:.1f}{config['unit']}",
                    anomaly_type=AnomalyType.TREND,
                    severity=severity,
                    description=(
                        f"Tendance croissante de {config['name']} : "
                        f"+{delta:.1f}{config['unit']} sur {WINDOW_SIZE} snapshots "
                        f"(pente {slope:.2f}/snap, r={corr:.2f})"
                    ),
                )
            )
            # Ne pas flagger toutes les fenêtres qui se chevauchent — on saute
            # jusqu'à la fin de cette tendance
            break

    return anomalies


def trend_detection_node(state: PipelineState) -> PipelineState:
    """Détecte les tendances de dégradation sur chaque métrique."""
    snapshots = state.raw_snapshots
    if len(snapshots) < WINDOW_SIZE:
        logger.info(f"Pas assez de snapshots pour la détection de tendances (< {WINDOW_SIZE})")
        return state

    # Trier par timestamp pour garantir l'ordre chronologique
    sorted_snaps = sorted(snapshots, key=lambda s: s.timestamp)

    trend_anomalies = []
    for metric, config in GROWTH_METRICS.items():
        trend_anomalies.extend(_detect_metric_trend(sorted_snaps, metric, config))

    state.anomalies.extend(trend_anomalies)
    logger.info(f"Détection de tendances : {len(trend_anomalies)} tendances identifiées")
    return state
