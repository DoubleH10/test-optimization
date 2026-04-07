"""Comparaison entre deux rapports — tendance période vs période.

Répond à la question qu'un CTO pose vraiment :
"Est-ce qu'on va mieux ou moins bien que la semaine dernière ?"

Charge deux rapports JSON et produit un diff structuré :
- évolution des métriques clés (p95, moyenne)
- évolution du nombre d'anomalies par sévérité
- évolution de l'uptime par service
- nouvelles anomalies / anomalies résolues
"""

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from infra_optimizer.models import InfrastructureReport, Severity


class Direction(str, Enum):
    IMPROVED = "improved"
    DEGRADED = "degraded"
    STABLE = "stable"


class MetricDelta(BaseModel):
    metric: str
    before_mean: float
    after_mean: float
    before_p95: float
    after_p95: float
    delta_pct: float
    direction: Direction


class ServiceDelta(BaseModel):
    service: str
    before_uptime: float
    after_uptime: float
    delta_pp: float  # points de pourcentage
    direction: Direction


class SeverityDelta(BaseModel):
    severity: Severity
    before_count: int
    after_count: int
    delta: int
    direction: Direction


class ComparisonReport(BaseModel):
    before_period: str
    after_period: str
    metric_deltas: list[MetricDelta] = Field(default_factory=list)
    service_deltas: list[ServiceDelta] = Field(default_factory=list)
    severity_deltas: list[SeverityDelta] = Field(default_factory=list)
    total_anomalies_before: int
    total_anomalies_after: int
    headline: str


def _load_report(path: Path) -> InfrastructureReport:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return InfrastructureReport(**data)


def _classify(delta: float, lower_is_better: bool = True) -> Direction:
    """Classe une évolution en improved/degraded/stable."""
    if abs(delta) < 2.0:  # seuil de bruit : ±2%
        return Direction.STABLE
    if lower_is_better:
        return Direction.IMPROVED if delta < 0 else Direction.DEGRADED
    return Direction.IMPROVED if delta > 0 else Direction.DEGRADED


# Métriques où "plus bas" = mieux
LOWER_IS_BETTER = {
    "cpu_usage",
    "memory_usage",
    "latency_ms",
    "disk_usage",
    "error_rate",
    "io_wait",
    "temperature_celsius",
    "power_consumption_watts",
}


def compare_reports(before_path: Path, after_path: Path) -> ComparisonReport:
    """Charge deux rapports et produit un diff structuré."""
    before = _load_report(before_path)
    after = _load_report(after_path)

    # Deltas par métrique
    before_stats = {ms.metric: ms for ms in before.period_summary.metric_stats}
    after_stats = {ms.metric: ms for ms in after.period_summary.metric_stats}

    metric_deltas = []
    for metric in before_stats.keys() & after_stats.keys():
        b = before_stats[metric]
        a = after_stats[metric]
        if b.mean == 0:
            delta_pct = 0.0
        else:
            delta_pct = ((a.mean - b.mean) / b.mean) * 100

        metric_deltas.append(
            MetricDelta(
                metric=metric,
                before_mean=round(b.mean, 2),
                after_mean=round(a.mean, 2),
                before_p95=round(b.p95, 2),
                after_p95=round(a.p95, 2),
                delta_pct=round(delta_pct, 1),
                direction=_classify(delta_pct, lower_is_better=metric in LOWER_IS_BETTER),
            )
        )
    metric_deltas.sort(key=lambda m: abs(m.delta_pct), reverse=True)

    # Deltas par service
    service_deltas = []
    for svc in before.period_summary.service_uptime.keys():
        b_up = before.period_summary.service_uptime[svc]
        a_up = after.period_summary.service_uptime.get(svc, b_up)
        delta_pp = round(a_up - b_up, 2)
        service_deltas.append(
            ServiceDelta(
                service=svc,
                before_uptime=b_up,
                after_uptime=a_up,
                delta_pp=delta_pp,
                # Uptime : plus haut = mieux, donc lower_is_better=False
                direction=_classify(delta_pp, lower_is_better=False),
            )
        )

    # Deltas par sévérité
    def count_by_severity(report: InfrastructureReport) -> dict[Severity, int]:
        counts: dict[Severity, int] = {}
        for a in report.anomalies:
            counts[a.severity] = counts.get(a.severity, 0) + 1
        return counts

    before_counts = count_by_severity(before)
    after_counts = count_by_severity(after)
    severity_deltas = []
    for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        b_c = before_counts.get(sev, 0)
        a_c = after_counts.get(sev, 0)
        delta = a_c - b_c
        if b_c == 0 and a_c == 0:
            continue
        severity_deltas.append(
            SeverityDelta(
                severity=sev,
                before_count=b_c,
                after_count=a_c,
                delta=delta,
                direction=(
                    Direction.IMPROVED
                    if delta < 0
                    else Direction.DEGRADED
                    if delta > 0
                    else Direction.STABLE
                ),
            )
        )

    # Headline
    improved = sum(1 for m in metric_deltas if m.direction == Direction.IMPROVED)
    degraded = sum(1 for m in metric_deltas if m.direction == Direction.DEGRADED)
    if degraded > improved:
        headline = f"⚠️ Dégradation globale : {degraded} métriques en baisse vs {improved} en hausse."
    elif improved > degraded:
        headline = f"✅ Amélioration globale : {improved} métriques en hausse vs {degraded} en baisse."
    else:
        headline = "➡️ Situation stable : autant d'améliorations que de dégradations."

    return ComparisonReport(
        before_period=(
            f"{before.period_summary.period_start.date()} → "
            f"{before.period_summary.period_end.date()}"
        ),
        after_period=(
            f"{after.period_summary.period_start.date()} → "
            f"{after.period_summary.period_end.date()}"
        ),
        metric_deltas=metric_deltas,
        service_deltas=service_deltas,
        severity_deltas=severity_deltas,
        total_anomalies_before=len(before.anomalies),
        total_anomalies_after=len(after.anomalies),
        headline=headline,
    )
