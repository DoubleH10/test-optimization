"""Nœud 1 — Ingestion.

Charge les métriques depuis un fichier JSON, valide chaque entrée via Pydantic.
Les entrées invalides sont loggées mais n'arrêtent pas le pipeline.
"""

import json
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from infra_optimizer.models import MetricSnapshot, PipelineState


def ingestion_node(state: PipelineState, source_path: str) -> PipelineState:
    """Charge et valide les métriques depuis un fichier JSON."""
    path = Path(source_path)
    if not path.exists():
        msg = f"Fichier introuvable : {source_path}"
        logger.error(msg)
        state.errors.append(msg)
        return state

    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        msg = f"JSON invalide dans {source_path} : {e}"
        logger.error(msg)
        state.errors.append(msg)
        return state

    if not isinstance(raw, list):
        msg = "Le fichier doit contenir une liste de snapshots"
        logger.error(msg)
        state.errors.append(msg)
        return state

    snapshots = []
    invalid_count = 0
    for i, entry in enumerate(raw):
        try:
            snapshots.append(MetricSnapshot(**entry))
        except ValidationError as e:
            invalid_count += 1
            logger.warning(f"Snapshot #{i} invalide, ignoré : {e.errors()[0]['msg']}")

    state.raw_snapshots = snapshots
    logger.info(
        f"Ingestion terminée : {len(snapshots)} snapshots valides, {invalid_count} ignorés"
    )
    return state
