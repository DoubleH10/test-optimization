"""Nœud 5 — Génération de recommandations par LLM (Mistral).

Le LLM reçoit les anomalies détectées par les nœuds déterministes
et génère des recommandations actionnables.

Choix : LLM uniquement pour la couche "raisonnement métier", pas pour la détection.
- Détection = stats (rapide, reproductible, pas cher)
- Recommandations = LLM (créatif, contextuel, naturel à lire)
"""

import json

from loguru import logger
from pydantic import ValidationError

from infra_optimizer.llm.client import MistralClient
from infra_optimizer.models import (
    Anomaly,
    PipelineState,
    Recommendation,
    Severity,
)
from infra_optimizer.prompts.mistral_prompts import (
    RECOMMENDATION_SYSTEM,
    RECOMMENDATION_USER_TEMPLATE,
)


def _summarize_anomalies(anomalies: list[Anomaly]) -> str:
    """Compresse les anomalies en agrégats par métrique + sévérité.

    On NE passe PAS chaque anomalie individuellement au LLM (trop verbeux,
    inutile pour générer des recommandations stratégiques). On donne plutôt
    des compteurs et des exemples représentatifs.
    """
    if not anomalies:
        return "Aucune anomalie."

    # Agrégation : (metric, severity) -> {count, max_value, sample_description}
    buckets: dict[tuple[str, str], dict] = {}
    for a in anomalies:
        key = (a.metric, a.severity.value)
        if key not in buckets:
            buckets[key] = {
                "count": 0,
                "max_value": a.value if isinstance(a.value, (int, float)) else None,
                "sample": a.description,
                "first_seen": a.timestamp.isoformat(),
            }
        buckets[key]["count"] += 1
        if isinstance(a.value, (int, float)) and buckets[key]["max_value"] is not None:
            if a.value > buckets[key]["max_value"]:
                buckets[key]["max_value"] = a.value

    # Tri par sévérité décroissante puis count décroissant
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_keys = sorted(
        buckets.keys(),
        key=lambda k: (severity_rank[k[1]], -buckets[k]["count"]),
    )

    lines = []
    for metric, sev in sorted_keys:
        b = buckets[(metric, sev)]
        max_str = f", max={b['max_value']}" if b["max_value"] is not None else ""
        lines.append(
            f"- [{sev.upper()}] {metric}: {b['count']} occurrences{max_str} "
            f"(ex: {b['sample']})"
        )
    return "\n".join(lines)


def _summarize_stats(state: PipelineState) -> str:
    if not state.period_summary:
        return "Pas de statistiques."
    lines = []
    for ms in state.period_summary.metric_stats:
        lines.append(
            f"- {ms.metric}: moy={ms.mean:.1f} med={ms.median:.1f} "
            f"p95={ms.p95:.1f} p99={ms.p99:.1f} max={ms.max:.1f}"
        )
    lines.append("\nUptime services :")
    for svc, pct in state.period_summary.service_uptime.items():
        lines.append(f"  - {svc}: {pct}%")
    return "\n".join(lines)


def _summarize_service_incidents(state: PipelineState) -> str:
    service_anomalies = [a for a in state.anomalies if a.metric.startswith("service.")]
    if not service_anomalies:
        return "Aucun incident service."
    counts: dict[str, int] = {}
    for a in service_anomalies:
        counts[a.metric] = counts.get(a.metric, 0) + 1
    return "\n".join(f"- {svc} : {count} occurrences" for svc, count in counts.items())


def recommendation_node(state: PipelineState) -> PipelineState:
    """Demande à Mistral de générer des recommandations contextualisées."""
    if not state.anomalies:
        logger.info("Aucune anomalie — pas de recommandations à générer")
        return state

    client = MistralClient()
    if not client.is_available():
        logger.warning("Mistral non disponible — fallback sur recommandations basiques")
        state.recommendations = _fallback_recommendations(state)
        return state

    user_prompt = RECOMMENDATION_USER_TEMPLATE.format(
        stats=_summarize_stats(state),
        anomalies=_summarize_anomalies(state.anomalies),
        service_incidents=_summarize_service_incidents(state),
    )

    response = client.chat_json(
        system=RECOMMENDATION_SYSTEM,
        user=user_prompt,
        temperature=0.2,
    )

    raw_recs = response.get("recommendations", [])
    if not raw_recs:
        logger.warning("Mistral n'a renvoyé aucune recommandation — fallback")
        state.recommendations = _fallback_recommendations(state)
        return state

    parsed = []
    for raw in raw_recs:
        try:
            parsed.append(Recommendation(**raw))
        except ValidationError as e:
            logger.warning(f"Recommandation invalide ignorée : {e}")

    state.recommendations = parsed
    logger.info(f"Recommandations générées : {len(parsed)}")
    return state


def _fallback_recommendations(state: PipelineState) -> list[Recommendation]:
    """Recommandations déterministes si le LLM est indisponible.

    Garantit que le pipeline produit toujours une sortie utile, même offline.
    """
    recs = []
    metrics_seen = {a.metric for a in state.anomalies}

    if "cpu_usage" in metrics_seen:
        recs.append(
            Recommendation(
                title="Mettre en place un autoscaling CPU",
                related_anomalies=["Pics CPU > 85%"],
                priority=Severity.HIGH,
                category="scaling",
                description=(
                    "Configurer une politique d'autoscaling horizontal basée sur le CPU "
                    "(ex : ajouter une instance dès que le CPU dépasse 80% pendant 5 minutes)."
                ),
                expected_impact="Réduction des pics de charge et de la latence associée.",
                estimated_effort="medium",
            )
        )

    if "latency_ms" in metrics_seen:
        recs.append(
            Recommendation(
                title="Investiguer la cause des pics de latence",
                related_anomalies=["latency_ms > 300ms"],
                priority=Severity.HIGH,
                category="monitoring",
                description=(
                    "Activer un APM (ex : OpenTelemetry + Grafana Tempo) pour tracer "
                    "les requêtes lentes et identifier les goulots d'étranglement."
                ),
                expected_impact="Visibilité sur les requêtes lentes et chemin critique.",
                estimated_effort="medium",
            )
        )

    if any(m.startswith("service.") for m in metrics_seen):
        recs.append(
            Recommendation(
                title="Mettre en place une alerte sur les états de service",
                related_anomalies=["Services dégradés/offline"],
                priority=Severity.CRITICAL,
                category="incident_response",
                description=(
                    "Configurer Alertmanager (ou équivalent) pour notifier l'équipe "
                    "dès qu'un service passe en dégradé ou offline."
                ),
                expected_impact="Détection en temps réel des incidents.",
                estimated_effort="low",
            )
        )

    return recs
