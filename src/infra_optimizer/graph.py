"""Pipeline LangGraph — orchestration des nœuds.

Architecture choisie : graphe linéaire séquentiel.
Pourquoi LangGraph plutôt qu'une simple chaîne de fonctions ?
- Chaque nœud devient une unité testable indépendamment.
- L'état partagé est explicite et typé (Pydantic).
- Possible d'ajouter facilement des branches conditionnelles plus tard
  (ex : skip le LLM si trop d'erreurs, exécution parallèle de nœuds).
- Visualisation graphique gratuite via `graph.get_graph().draw_mermaid()`.
"""

from functools import partial

from langgraph.graph import END, StateGraph
from loguru import logger

from infra_optimizer.models import PipelineState
from infra_optimizer.nodes.anomaly_detection import anomaly_detection_node
from infra_optimizer.nodes.ingestion import ingestion_node
from infra_optimizer.nodes.normalization import normalization_node
from infra_optimizer.nodes.recommendation import recommendation_node
from infra_optimizer.nodes.report import build_report, report_node
from infra_optimizer.nodes.service_status import service_status_node


def build_pipeline(source_path: str):
    """Construit et compile le graphe LangGraph."""
    graph = StateGraph(PipelineState)

    graph.add_node("ingestion", partial(ingestion_node, source_path=source_path))
    graph.add_node("normalization", normalization_node)
    graph.add_node("anomaly_detection", anomaly_detection_node)
    graph.add_node("service_status", service_status_node)
    graph.add_node("recommendation", recommendation_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "normalization")
    graph.add_edge("normalization", "anomaly_detection")
    graph.add_edge("anomaly_detection", "service_status")
    graph.add_edge("service_status", "recommendation")
    graph.add_edge("recommendation", "report")
    graph.add_edge("report", END)

    return graph.compile()


def run_pipeline(source_path: str):
    """Exécute le pipeline complet et retourne le rapport final."""
    logger.info(f"Démarrage du pipeline sur {source_path}")
    pipeline = build_pipeline(source_path)
    initial_state = PipelineState()
    final_state_dict = pipeline.invoke(initial_state)

    # LangGraph retourne un dict — on le re-wrappe en PipelineState
    final_state = PipelineState(**final_state_dict)
    report = build_report(final_state)
    logger.info("Pipeline terminé")
    return report
