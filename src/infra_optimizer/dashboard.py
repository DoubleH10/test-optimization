"""Dashboard Streamlit — interface visuelle pour le pipeline.

Permet à Jean (CTO) d'utiliser l'outil sans passer par la CLI :
- upload d'un fichier JSON de métriques OU sélection d'un fichier existant
- exécution du pipeline en un clic
- affichage : synthèse exécutive, heatmap d'anomalies, tableau de recommandations
- téléchargement du rapport JSON

Lancer avec :
    streamlit run src/infra_optimizer/dashboard.py
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from infra_optimizer.comparison import Direction, compare_reports
from infra_optimizer.graph import run_pipeline
from infra_optimizer.models import InfrastructureReport, Severity

# ============================================================================
# Configuration de la page
# ============================================================================

st.set_page_config(
    page_title="Infra Optimizer — Devoteam",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

SEVERITY_COLORS_HEX = {
    Severity.CRITICAL: "#b91c1c",
    Severity.HIGH: "#ea580c",
    Severity.MEDIUM: "#ca8a04",
    Severity.LOW: "#16a34a",
}

DIRECTION_EMOJI = {
    Direction.IMPROVED: "✅",
    Direction.DEGRADED: "⚠️",
    Direction.STABLE: "➡️",
}


# ============================================================================
# Helpers
# ============================================================================

def _load_existing_reports() -> list[Path]:
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []
    return sorted(reports_dir.glob("*.json"))


def _run_pipeline_on_file(uploaded_file) -> InfrastructureReport:
    """Écrit l'upload dans un fichier temporaire puis lance le pipeline."""
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="wb"
    ) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    return run_pipeline(tmp_path)


def _anomalies_to_dataframe(report: InfrastructureReport) -> pd.DataFrame:
    rows = []
    for a in report.anomalies:
        rows.append({
            "timestamp": a.timestamp,
            "metric": a.metric,
            "value": str(a.value),
            "severity": a.severity.value,
            "type": a.anomaly_type.value,
            "description": a.description,
        })
    return pd.DataFrame(rows)


def _recommendations_to_dataframe(report: InfrastructureReport) -> pd.DataFrame:
    rows = []
    for r in report.recommendations:
        rows.append({
            "Priorité": r.priority.value.upper(),
            "Catégorie": r.category,
            "Titre": r.title,
            "Description": r.description,
            "Impact attendu": r.expected_impact,
            "Effort": r.estimated_effort,
        })
    return pd.DataFrame(rows)


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.title("🔧 Infra Optimizer")
    st.caption("Pipeline modulaire LangGraph + Mistral — Devoteam")

    page = st.radio(
        "Mode",
        ["Analyse", "Comparaison", "À propos"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("**Stack**")
    st.caption("- LangGraph")
    st.caption("- Mistral Large")
    st.caption("- Pydantic v2")
    st.caption("- Pipeline 7 nœuds déterministes + LLM")


# ============================================================================
# Page Analyse
# ============================================================================

if page == "Analyse":
    st.title("Analyse d'infrastructure")
    st.markdown(
        "Ingère des métriques d'infrastructure, détecte des anomalies, "
        "et génère des recommandations actionnables via **Mistral**."
    )

    # Source selection via radio — plus stable que des boutons séparés
    source_mode = st.radio(
        "Source des données",
        ["Dataset fourni (data/infrastructure_metrics.json)", "Uploader un fichier"],
        horizontal=True,
    )

    uploaded = None
    if source_mode == "Uploader un fichier":
        uploaded = st.file_uploader(
            "Fichier JSON de métriques",
            type=["json"],
            help="Format : liste de snapshots (cf. `data/infrastructure_metrics.json`)",
        )
        ready = uploaded is not None
    else:
        sample_path = Path("data/infrastructure_metrics.json")
        if sample_path.exists():
            st.success(f"✓ Dataset trouvé : {sample_path} ({sample_path.stat().st_size // 1024} KB)")
            ready = True
        else:
            st.error(f"✗ Dataset introuvable : {sample_path}")
            ready = False

    run_clicked = st.button(
        "▶️ Lancer l'analyse", type="primary", disabled=not ready, use_container_width=True
    )

    if run_clicked:
        with st.spinner("Pipeline en cours — ingestion, détection, LLM..."):
            if uploaded is not None:
                report = _run_pipeline_on_file(uploaded)
            else:
                report = run_pipeline("data/infrastructure_metrics.json")
        st.session_state["last_report"] = report
        st.success(
            f"✓ Pipeline terminé — {len(report.anomalies)} anomalies, "
            f"{len(report.recommendations)} recommandations"
        )

    # Affichage du rapport
    if "last_report" in st.session_state:
        report: InfrastructureReport = st.session_state["last_report"]

        st.divider()

        # Synthèse exécutive
        st.subheader("📋 Synthèse exécutive")
        st.info(report.executive_summary)

        # Métriques clés en KPIs
        ps = report.period_summary
        kpi_cols = st.columns(5)
        kpi_cols[0].metric("Snapshots", ps.total_snapshots)
        kpi_cols[1].metric("Anomalies", len(report.anomalies))
        kpi_cols[2].metric("Recommandations", len(report.recommendations))
        kpi_cols[3].metric("Incidents services", ps.incidents_count)
        critical_count = sum(1 for a in report.anomalies if a.severity == Severity.CRITICAL)
        kpi_cols[4].metric("Critiques", critical_count, delta_color="inverse")

        # Uptime par service
        st.subheader("🌐 Uptime des services")
        uptime_cols = st.columns(len(ps.service_uptime))
        for i, (svc, pct) in enumerate(ps.service_uptime.items()):
            color = "normal" if pct > 95 else "inverse"
            uptime_cols[i].metric(svc.replace("_", " ").title(), f"{pct}%", delta_color=color)

        # Heatmap anomalies par métrique × sévérité (rendu Streamlit natif, pas de matplotlib)
        st.subheader("🔥 Heatmap des anomalies")
        df_anom = _anomalies_to_dataframe(report)
        if not df_anom.empty:
            pivot = df_anom.pivot_table(
                index="metric",
                columns="severity",
                values="timestamp",
                aggfunc="count",
                fill_value=0,
            )
            col_order = [s for s in ["critical", "high", "medium", "low"] if s in pivot.columns]
            pivot = pivot[col_order]
            # Utilise column_config avec ProgressColumn pour une heatmap visuelle sans matplotlib
            max_val = int(pivot.to_numpy().max()) if pivot.size > 0 else 1
            column_config = {
                col: st.column_config.ProgressColumn(
                    col.upper(),
                    format="%d",
                    min_value=0,
                    max_value=max_val,
                )
                for col in pivot.columns
            }
            st.dataframe(
                pivot,
                use_container_width=True,
                column_config=column_config,
            )
        else:
            st.info("Aucune anomalie détectée.")

        # Timeline des métriques clés
        st.subheader("📈 Statistiques par métrique")
        stats_data = []
        for ms in ps.metric_stats:
            stats_data.append({
                "Métrique": ms.metric,
                "Moyenne": round(ms.mean, 2),
                "Médiane": round(ms.median, 2),
                "p95": round(ms.p95, 2),
                "p99": round(ms.p99, 2),
                "Max": round(ms.max, 2),
                "Écart-type": round(ms.std, 2),
            })
        st.dataframe(pd.DataFrame(stats_data), use_container_width=True, hide_index=True)

        # Recommandations détaillées
        st.subheader(f"💡 Recommandations ({len(report.recommendations)})")
        if report.recommendations:
            for i, rec in enumerate(report.recommendations, 1):
                priority_color = SEVERITY_COLORS_HEX[rec.priority]
                with st.expander(
                    f"**{i}. [{rec.priority.value.upper()}] {rec.title}** — {rec.category} ({rec.estimated_effort} effort)"
                ):
                    st.markdown(f"**Description :** {rec.description}")
                    st.markdown(f"**Impact attendu :** {rec.expected_impact}")
                    st.markdown(f"**Anomalies adressées :**")
                    for ra in rec.related_anomalies:
                        st.markdown(f"- {ra}")
        else:
            st.info("Aucune recommandation générée.")

        # Tableau complet des anomalies
        with st.expander(f"📋 Voir toutes les anomalies ({len(report.anomalies)})"):
            if not df_anom.empty:
                st.dataframe(df_anom, use_container_width=True, hide_index=True)

        # Download
        st.divider()
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "⬇️ Télécharger le rapport JSON",
                data=report.model_dump_json(indent=2),
                file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
            )
        with col_dl2:
            # Sauvegarder dans reports/ pour comparaison ultérieure
            if st.button("💾 Sauvegarder dans reports/", use_container_width=True):
                reports_dir = Path("reports")
                reports_dir.mkdir(exist_ok=True)
                fname = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                (reports_dir / fname).write_text(
                    report.model_dump_json(indent=2), encoding="utf-8"
                )
                st.success(f"Sauvegardé : reports/{fname}")


# ============================================================================
# Page Comparaison
# ============================================================================

elif page == "Comparaison":
    st.title("Comparaison de rapports")
    st.markdown("Compare deux rapports pour identifier les tendances période vs période.")

    existing = _load_existing_reports()
    if len(existing) < 2:
        st.warning(
            "Pas assez de rapports dans `reports/` pour comparer. "
            "Lance au moins 2 analyses et sauvegarde-les pour utiliser ce mode."
        )
    else:
        col1, col2 = st.columns(2)
        with col1:
            before = st.selectbox(
                "Rapport avant",
                existing,
                format_func=lambda p: p.name,
                index=0,
            )
        with col2:
            after = st.selectbox(
                "Rapport après",
                existing,
                format_func=lambda p: p.name,
                index=len(existing) - 1,
            )

        if st.button("▶️ Comparer", type="primary"):
            result = compare_reports(before, after)

            # Headline
            if "Dégradation" in result.headline:
                st.error(result.headline)
            elif "Amélioration" in result.headline:
                st.success(result.headline)
            else:
                st.info(result.headline)

            kpi_cols = st.columns(3)
            kpi_cols[0].metric(
                "Anomalies avant", result.total_anomalies_before
            )
            kpi_cols[1].metric(
                "Anomalies après", result.total_anomalies_after
            )
            kpi_cols[2].metric(
                "Δ",
                result.total_anomalies_after - result.total_anomalies_before,
                delta_color="inverse",
            )

            # Métriques
            st.subheader("Évolution des métriques")
            metric_rows = []
            for m in result.metric_deltas:
                metric_rows.append({
                    "Métrique": m.metric,
                    "Moy. avant": m.before_mean,
                    "Moy. après": m.after_mean,
                    "p95 après": m.after_p95,
                    "Δ %": f"{m.delta_pct:+.1f}%",
                    "Direction": f"{DIRECTION_EMOJI[m.direction]} {m.direction.value}",
                })
            st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)

            # Services
            st.subheader("Évolution de l'uptime services")
            svc_rows = []
            for s in result.service_deltas:
                svc_rows.append({
                    "Service": s.service,
                    "Uptime avant": f"{s.before_uptime}%",
                    "Uptime après": f"{s.after_uptime}%",
                    "Δ (pp)": f"{s.delta_pp:+.2f}",
                    "Direction": f"{DIRECTION_EMOJI[s.direction]} {s.direction.value}",
                })
            st.dataframe(pd.DataFrame(svc_rows), use_container_width=True, hide_index=True)

            # Sévérité
            st.subheader("Évolution par sévérité")
            sev_rows = []
            for s in result.severity_deltas:
                sev_rows.append({
                    "Sévérité": s.severity.value.upper(),
                    "Avant": s.before_count,
                    "Après": s.after_count,
                    "Δ": f"{s.delta:+d}",
                    "Direction": f"{DIRECTION_EMOJI[s.direction]} {s.direction.value}",
                })
            st.dataframe(pd.DataFrame(sev_rows), use_container_width=True, hide_index=True)


# ============================================================================
# Page À propos
# ============================================================================

else:
    st.title("À propos")
    st.markdown("""
### Infra Optimizer — Test Technique Devoteam

Pipeline modulaire qui résout le besoin de Jean (CTO d'une PME française) :
**comprendre l'état de son infrastructure et recevoir des recommandations actionnables** sans analyser manuellement des milliers de points de données.

### Architecture

Pipeline en **7 nœuds** orchestré par LangGraph :

1. **Ingestion** — charge et valide le JSON via Pydantic
2. **Normalisation** — calcule stats descriptives (moy, p95, p99, écart-type)
3. **Détection d'anomalies** — seuils absolus + z-scores statistiques
4. **Statut des services** — identifie les services dégradés/offline
5. **Détection de tendances** — régression linéaire sur fenêtre glissante pour capturer les dégradations progressives
6. **Recommandations** — Mistral génère des actions contextualisées
7. **Rapport** — Mistral rédige la synthèse exécutive

### Choix clés

- **LangGraph** pour l'orchestration (suggéré par l'énoncé)
- **Mistral** comme LLM principal (souveraineté EU, RGPD natif)
- **Hybride déterministe + LLM** : stats pour ce que les stats font bien, LLM pour le raisonnement métier
- **Mode dégradé** fonctionnel sans clé API
- **Pydantic** partout pour la validation stricte

### Équipe

Solution développée pour le test technique Devoteam — avril 2026.
""")
