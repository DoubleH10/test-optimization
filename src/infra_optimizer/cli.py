"""CLI Typer — point d'entrée de l'application."""

import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from infra_optimizer.comparison import Direction, compare_reports
from infra_optimizer.config import settings
from infra_optimizer.graph import run_pipeline
from infra_optimizer.models import Severity

app = typer.Typer(
    name="optimizer",
    help="Pipeline modulaire d'optimisation d'infrastructure pour PME",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()


BANNER = r"""
 ___        __              ___        _   _           _
|_ _|_ __  / _|_ __ __ _   / _ \ _ __ | |_(_)_ __ ___ (_)_______ _ __
 | || '_ \| |_| '__/ _` | | | | | '_ \| __| | '_ ` _ \| |_  / _ \ '__|
 | || | | |  _| | | (_| | | |_| | |_) | |_| | | | | | | |/ /  __/ |
|___|_| |_|_| |_|  \__,_|  \___/| .__/ \__|_|_| |_| |_|_/___\___|_|
                                |_|
"""


def _print_banner():
    """Affiche la bannière et le sous-titre."""
    banner_text = Text(BANNER, style="bold cyan")
    subtitle = Text(
        "Pipeline modulaire LangGraph + Mistral — Test Devoteam",
        style="dim italic",
        justify="center",
    )
    console.print(Align.center(banner_text))
    console.print(Align.center(subtitle))
    console.print()


def _print_menu():
    """Affiche le menu principal avec les commandes disponibles."""
    _print_banner()

    table = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        title="[bold]Commandes disponibles[/bold]",
        title_style="bold white",
        expand=False,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Commande", style="bold cyan", width=14)
    table.add_column("Description", style="white")
    table.add_column("Exemple", style="dim italic")

    rows = [
        (
            "1",
            "analyze",
            "Analyser un fichier de métriques\n[dim]ingestion → stats → détection → recommandations[/dim]",
            "optimizer analyze data/infrastructure_metrics.json",
        ),
        (
            "2",
            "compare",
            "Comparer deux rapports période vs période\n[dim]headline + deltas métriques + services + sévérité[/dim]",
            "optimizer compare reports/sem1.json reports/sem2.json",
        ),
        (
            "3",
            "graph",
            "Afficher le diagramme Mermaid du pipeline\n[dim]visualisation des 7 nœuds LangGraph[/dim]",
            "optimizer graph",
        ),
        (
            "4",
            "dashboard",
            "Lancer le dashboard web Streamlit\n[dim]interface visuelle : upload, analyse, comparaison[/dim]",
            "optimizer dashboard",
        ),
        (
            "5",
            "menu",
            "Ouvrir ce menu interactif\n[dim]navigation par numéro[/dim]",
            "optimizer menu",
        ),
    ]
    for row in rows:
        table.add_row(*row)

    console.print(Align.center(table))
    console.print()

    # Status panel
    has_key = bool(settings.mistral_api_key)
    key_status = (
        "[green]✓ Configurée[/green]"
        if has_key
        else "[red]✗ Manquante — mode dégradé[/red]"
    )
    model_status = settings.mistral_model if has_key else "n/a"
    data_exists = Path("data/infrastructure_metrics.json").exists()
    data_status = (
        "[green]✓ 500 snapshots disponibles[/green]"
        if data_exists
        else "[red]✗ data/infrastructure_metrics.json introuvable[/red]"
    )

    status_lines = [
        f"[dim]Clé Mistral    [/dim] {key_status}",
        f"[dim]Modèle         [/dim] {model_status}",
        f"[dim]Dataset        [/dim] {data_status}",
        f"[dim]Architecture   [/dim] 7 nœuds LangGraph (5 déterministes, 2 LLM)",
    ]
    status = Panel(
        "\n".join(status_lines),
        title="[bold]État du système[/bold]",
        border_style="cyan",
        expand=False,
    )
    console.print(Align.center(status))
    console.print()

    console.print(
        Align.center(
            Text(
                "Astuce : tapez `optimizer <commande> --help` pour plus de détails",
                style="dim italic",
            )
        )
    )


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


DIRECTION_EMOJI = {
    Direction.IMPROVED: "✅",
    Direction.DEGRADED: "⚠️ ",
    Direction.STABLE: "➡️ ",
}
DIRECTION_COLOR = {
    Direction.IMPROVED: "green",
    Direction.DEGRADED: "red",
    Direction.STABLE: "yellow",
}


@app.command()
def compare(
    before: Path = typer.Argument(..., help="Rapport JSON de la période précédente"),
    after: Path = typer.Argument(..., help="Rapport JSON de la période actuelle"),
):
    """Compare deux rapports et produit un diff structuré."""
    if not before.exists() or not after.exists():
        console.print(f"[red]✗[/red] Un des rapports est introuvable")
        raise typer.Exit(code=1)

    result = compare_reports(before, after)

    console.print()
    console.print(
        Panel(
            f"[bold]{result.headline}[/bold]\n\n"
            f"Période avant : {result.before_period}\n"
            f"Période après : {result.after_period}\n"
            f"Anomalies : {result.total_anomalies_before} → {result.total_anomalies_after}",
            title="[bold]Comparaison de rapports[/bold]",
            border_style="cyan",
        )
    )

    # Tableau métriques
    metric_table = Table(title="Évolution des métriques", show_header=True, header_style="bold")
    metric_table.add_column("Métrique")
    metric_table.add_column("Moy. avant", justify="right")
    metric_table.add_column("Moy. après", justify="right")
    metric_table.add_column("p95 après", justify="right")
    metric_table.add_column("Δ %", justify="right")
    metric_table.add_column("Direction")
    for m in result.metric_deltas[:10]:
        color = DIRECTION_COLOR[m.direction]
        metric_table.add_row(
            m.metric,
            f"{m.before_mean:.1f}",
            f"{m.after_mean:.1f}",
            f"{m.after_p95:.1f}",
            f"[{color}]{m.delta_pct:+.1f}%[/{color}]",
            f"{DIRECTION_EMOJI[m.direction]} [{color}]{m.direction.value}[/{color}]",
        )
    console.print(metric_table)

    # Tableau services
    if result.service_deltas:
        svc_table = Table(title="Évolution de l'uptime services", show_header=True, header_style="bold")
        svc_table.add_column("Service")
        svc_table.add_column("Avant", justify="right")
        svc_table.add_column("Après", justify="right")
        svc_table.add_column("Δ pp", justify="right")
        svc_table.add_column("Direction")
        for s in result.service_deltas:
            color = DIRECTION_COLOR[s.direction]
            svc_table.add_row(
                s.service,
                f"{s.before_uptime}%",
                f"{s.after_uptime}%",
                f"[{color}]{s.delta_pp:+.2f}[/{color}]",
                f"{DIRECTION_EMOJI[s.direction]} [{color}]{s.direction.value}[/{color}]",
            )
        console.print(svc_table)

    # Tableau sévérité
    if result.severity_deltas:
        sev_table = Table(title="Évolution des anomalies par sévérité", show_header=True, header_style="bold")
        sev_table.add_column("Sévérité")
        sev_table.add_column("Avant", justify="right")
        sev_table.add_column("Après", justify="right")
        sev_table.add_column("Δ", justify="right")
        for s in result.severity_deltas:
            color = DIRECTION_COLOR[s.direction]
            sev_table.add_row(
                f"[{SEVERITY_COLORS[s.severity]}]{s.severity.value.upper()}[/{SEVERITY_COLORS[s.severity]}]",
                str(s.before_count),
                str(s.after_count),
                f"[{color}]{s.delta:+d}[/{color}]",
            )
        console.print(sev_table)


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p", help="Port du serveur Streamlit"),
):
    """Lance le dashboard web Streamlit."""
    console.print(
        Panel.fit(
            f"[bold cyan]Lancement du dashboard[/bold cyan]\n\n"
            f"URL locale : [link]http://localhost:{port}[/link]\n"
            f"Ctrl+C pour arrêter",
            border_style="cyan",
        )
    )
    dashboard_path = Path(__file__).parent / "dashboard.py"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(dashboard_path),
            "--server.port",
            str(port),
        ]
    )


@app.command()
def menu():
    """Menu interactif — navigation par numéro."""
    while True:
        console.clear()
        _print_menu()
        console.print()
        choice = Prompt.ask(
            "[bold cyan]Choix[/bold cyan]",
            choices=["1", "2", "3", "4", "q"],
            default="q",
            show_choices=False,
            show_default=False,
        )
        console.print()

        if choice == "q":
            console.print("[dim]Au revoir.[/dim]")
            break
        elif choice == "1":
            source = Prompt.ask(
                "Chemin du fichier JSON",
                default="data/infrastructure_metrics.json",
            )
            output = Prompt.ask("Chemin du rapport", default="reports/output.json")
            analyze(Path(source), Path(output), verbose=False)
            Prompt.ask("\n[dim]Appuyez sur Entrée pour revenir au menu[/dim]", default="")
        elif choice == "2":
            before = Prompt.ask("Rapport avant", default="reports/week1.json")
            after = Prompt.ask("Rapport après", default="reports/week2.json")
            compare(Path(before), Path(after))
            Prompt.ask("\n[dim]Appuyez sur Entrée pour revenir au menu[/dim]", default="")
        elif choice == "3":
            graph()
            Prompt.ask("\n[dim]Appuyez sur Entrée pour revenir au menu[/dim]", default="")
        elif choice == "4":
            dashboard(port=8501)
            break


@app.callback()
def main(ctx: typer.Context):
    """Pipeline modulaire d'optimisation d'infrastructure pour PME."""
    if ctx.invoked_subcommand is None:
        _print_menu()


if __name__ == "__main__":
    app()
