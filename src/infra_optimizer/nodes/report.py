"""Nœud 6 — Génération du rapport final + synthèse exécutive.

Combine toutes les sorties en un objet `InfrastructureReport` structuré
et demande à Mistral une synthèse en langage naturel pour le CTO.
"""

from datetime import datetime

from loguru import logger

from infra_optimizer.llm.client import MistralClient
from infra_optimizer.models import (
    InfrastructureReport,
    PipelineState,
)
from infra_optimizer.prompts.mistral_prompts import (
    EXECUTIVE_SUMMARY_SYSTEM,
    EXECUTIVE_SUMMARY_USER_TEMPLATE,
)


def report_node(state: PipelineState) -> PipelineState:
    """Génère la synthèse exécutive et finalise l'état."""
    if not state.period_summary:
        logger.error("Pas de résumé de période — rapport impossible")
        return state

    client = MistralClient()

    if client.is_available() and state.anomalies:
        top_anomalies = "\n".join(
            f"- [{a.severity.value}] {a.metric} {a.value} : {a.description}"
            for a in state.anomalies[:10]
        )
        top_recs = "\n".join(
            f"- [{r.priority.value}] {r.title}" for r in state.recommendations[:5]
        )
        period_str = (
            f"{state.period_summary.period_start.isoformat()} → "
            f"{state.period_summary.period_end.isoformat()} "
            f"({state.period_summary.total_snapshots} snapshots)"
        )
        user_prompt = EXECUTIVE_SUMMARY_USER_TEMPLATE.format(
            period=period_str,
            top_anomalies=top_anomalies,
            top_recommendations=top_recs,
        )
        state.executive_summary = client.chat_text(
            system=EXECUTIVE_SUMMARY_SYSTEM,
            user=user_prompt,
            temperature=0.3,
        )
    else:
        # Fallback : synthèse générée mécaniquement
        state.executive_summary = _fallback_summary(state)

    logger.info("Rapport finalisé")
    return state


def _fallback_summary(state: PipelineState) -> str:
    """Synthèse mécanique si le LLM est indisponible."""
    if not state.period_summary:
        return "Rapport indisponible."
    n_anomalies = len(state.anomalies)
    n_recs = len(state.recommendations)
    return (
        f"Période analysée : {state.period_summary.period_start.date()} → "
        f"{state.period_summary.period_end.date()}. "
        f"{state.period_summary.total_snapshots} snapshots traités. "
        f"{n_anomalies} anomalies détectées, {n_recs} recommandations générées. "
        f"Voir le rapport JSON détaillé pour les actions à entreprendre."
    )


def build_report(state: PipelineState) -> InfrastructureReport:
    """Construit l'objet `InfrastructureReport` final depuis l'état du pipeline."""
    assert state.period_summary is not None, "period_summary doit être présent"
    return InfrastructureReport(
        generated_at=datetime.now(),
        period_summary=state.period_summary,
        anomalies=state.anomalies,
        recommendations=state.recommendations,
        executive_summary=state.executive_summary,
    )
