"""CLI Typer — point d'entrée de l'application."""

import json
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from infra_optimizer.config import settings
from infra_optimizer.graph import run_pipeline
from infra_optimizer.models import Severity

app = typer.Typer(
    name="optimizer",
    help="Pipeline modulaire d'optimisation d'infrastructure pour PME",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool):
    logger.remove()
    level = "DEBUG" if verbose else settings.log_level
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    )


SEVERITY_COLORS = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "green",
}


@app.command()
def analyze(
    source: Path = typer.Argument(..., help="Chemin vers le fichier JSON de métriques"),
    output: Path = typer.Option(
        Path("reports/output.json"), "--output", "-o", help="Chemin du rapport JSON"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Logs détaillés"),
):
    """Analyse un fichier de métriques et génère un rapport d'optimisation."""
    _setup_logging(verbose)

    if not source.exists():
        console.print(f"[red]✗[/red] Fichier introuvable : {source}")
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold cyan]Pipeline d'optimisation infra[/bold cyan]\n"
            f"Source : {source}\n"
            f"Sortie : {output}",
            border_style="cyan",
        )
    )

    report = run_pipeline(str(source))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _print_summary(report)
    console.print(f"\n[green]✓[/green] Rapport complet sauvegardé : {output}")


def _print_summary(report):
    """Affiche un résumé visuel dans la console."""
    console.print()
    console.print(
        Panel(
            report.executive_summary,
            title="[bold]Synthèse exécutive[/bold]",
            border_style="cyan",
        )
    )

    # Tableau des anomalies par sévérité
    severity_count: dict[Severity, int] = {}
    for a in report.anomalies:
        severity_count[a.severity] = severity_count.get(a.severity, 0) + 1

    if severity_count:
        table = Table(title="Anomalies détectées", show_header=True, header_style="bold")
        table.add_column("Sévérité")
        table.add_column("Nombre", justify="right")
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            count = severity_count.get(sev, 0)
            if count:
                table.add_row(
                    f"[{SEVERITY_COLORS[sev]}]{sev.value.upper()}[/{SEVERITY_COLORS[sev]}]",
                    str(count),
                )
        console.print(table)

    # Tableau des recommandations
    if report.recommendations:
        rec_table = Table(
            title=f"Recommandations ({len(report.recommendations)})",
            show_header=True,
            header_style="bold",
        )
        rec_table.add_column("Priorité")
        rec_table.add_column("Catégorie")
        rec_table.add_column("Titre")
        rec_table.add_column("Effort")
        for rec in report.recommendations:
            color = SEVERITY_COLORS.get(rec.priority, "white")
            rec_table.add_row(
                f"[{color}]{rec.priority.value.upper()}[/{color}]",
                rec.category,
                rec.title,
                rec.estimated_effort,
            )
        console.print(rec_table)


@app.command()
def graph():
    """Affiche le diagramme du pipeline LangGraph (Mermaid)."""
    from infra_optimizer.graph import build_pipeline

    pipeline = build_pipeline("dummy")
    mermaid = pipeline.get_graph().draw_mermaid()
    console.print("[bold]Diagramme Mermaid du pipeline :[/bold]\n")
    console.print(mermaid)


if __name__ == "__main__":
    app()
