"""Test d'intégration du pipeline complet (sans LLM)."""

import json
from pathlib import Path

from infra_optimizer.graph import run_pipeline


def test_pipeline_end_to_end_on_real_data():
    """Le pipeline doit traiter le dataset réel sans crasher.

    Tourne sans clé Mistral (mode dégradé avec fallback recommandations).
    """
    source = Path(__file__).parent.parent / "data" / "infrastructure_metrics.json"
    if not source.exists():
        return  # skip si le dataset n'est pas dispo

    report = run_pipeline(str(source))

    assert report.period_summary is not None
    assert report.period_summary.total_snapshots > 0
    # Le dataset contient des anomalies évidentes (CPU 93+, latency >300, etc.)
    assert len(report.anomalies) > 0
    # Avec ou sans LLM, on doit avoir au moins quelques recommandations
    assert len(report.recommendations) > 0
    # JSON sérialisable
    json.loads(report.model_dump_json())
