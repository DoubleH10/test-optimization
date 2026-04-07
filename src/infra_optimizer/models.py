"""Schémas Pydantic — définition stricte des données qui circulent dans le pipeline."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ============================================================================
# Données d'entrée — métriques brutes
# ============================================================================

class ServiceStatus(BaseModel):
    """État des services applicatifs à un instant T."""
    database: Literal["online", "degraded", "offline"]
    api_gateway: Literal["online", "degraded", "offline"]
    cache: Literal["online", "degraded", "offline"]


class MetricSnapshot(BaseModel):
    """Snapshot de métriques d'infrastructure à un instant donné."""
    timestamp: datetime
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    latency_ms: float = Field(ge=0)
    disk_usage: float = Field(ge=0, le=100)
    network_in_kbps: float = Field(ge=0)
    network_out_kbps: float = Field(ge=0)
    io_wait: float = Field(ge=0)
    thread_count: int = Field(ge=0)
    active_connections: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    uptime_seconds: int = Field(ge=0)
    temperature_celsius: float
    power_consumption_watts: float = Field(ge=0)
    service_status: ServiceStatus


# ============================================================================
# Anomalies détectées par les nœuds statistiques
# ============================================================================

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    THRESHOLD = "threshold"          # Dépassement de seuil absolu
    STATISTICAL = "statistical"      # Z-score / écart à la moyenne
    SERVICE = "service"              # État de service dégradé/offline
    TREND = "trend"                  # Tendance suspecte (montée continue)


class Anomaly(BaseModel):
    """Anomalie détectée de manière déterministe (stats, seuils, statuts)."""
    timestamp: datetime
    metric: str
    value: float | str
    expected_range: str
    anomaly_type: AnomalyType
    severity: Severity
    description: str


# ============================================================================
# Statistiques agrégées sur la période
# ============================================================================

class MetricStats(BaseModel):
    """Statistiques descriptives pour une métrique."""
    metric: str
    mean: float
    median: float
    p95: float
    p99: float
    max: float
    min: float
    std: float


class PeriodSummary(BaseModel):
    """Résumé global de la période analysée."""
    period_start: datetime
    period_end: datetime
    total_snapshots: int
    metric_stats: list[MetricStats]
    service_uptime: dict[str, float]  # % uptime par service
    incidents_count: int


# ============================================================================
# Sortie LLM — recommandations contextualisées
# ============================================================================

class Recommendation(BaseModel):
    """Recommandation actionnable produite par le LLM, ancrée dans une anomalie."""
    title: str
    related_anomalies: list[str] = Field(
        description="Identifiants ou descriptions courtes des anomalies adressées"
    )
    priority: Severity
    category: Literal[
        "scaling",
        "load_balancing",
        "monitoring",
        "configuration",
        "infrastructure",
        "security",
        "incident_response",
    ]
    description: str
    expected_impact: str
    estimated_effort: Literal["low", "medium", "high"]


class InfrastructureReport(BaseModel):
    """Rapport final structuré, livrable principal du pipeline."""
    generated_at: datetime
    period_summary: PeriodSummary
    anomalies: list[Anomaly]
    recommendations: list[Recommendation]
    executive_summary: str = Field(description="Synthèse en français pour le CTO")


# ============================================================================
# État du graphe LangGraph (passé entre les nœuds)
# ============================================================================

class PipelineState(BaseModel):
    """État partagé entre tous les nœuds du pipeline LangGraph."""
    raw_snapshots: list[MetricSnapshot] = Field(default_factory=list)
    period_summary: PeriodSummary | None = None
    anomalies: list[Anomaly] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    executive_summary: str = ""
    errors: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
