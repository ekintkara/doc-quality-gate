from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.config import load_app_config
from app.orchestrator import Orchestrator
from app.utils.logging import setup_logging
from app.web.log_stream import LogBroadcaster

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

app = typer.Typer(
    name="dqg",
    help="Doc Quality Gate - Review, validate, revise, and score implementation documents",
    add_completion=False,
)
console = Console()


def _ensure_env():
    candidates = [Path(".env"), _PROJECT_ROOT / ".env"]
    for env_file in candidates:
        if env_file.exists():
            from dotenv import load_dotenv

            load_dotenv(env_file)
            return


def _enable_web_bridge(app_config) -> None:
    setup_logging(app_config.log_level, enable_websocket=True, log_dir=app_config.log_dir)
    broadcaster = LogBroadcaster.get()
    if broadcaster.enable_http_forward():
        console.print("[dim]Web UI bridge active — http://localhost:8080/dashboard[/dim]\n")


@app.command()
def review(
    file: str = typer.Argument(..., help="Path to the document to review"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="Document type (auto-detected if not specified)"),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Path to project directory for cross-reference analysis"
    ),
    context_path: Optional[str] = typer.Option(
        None,
        "--context-path",
        "--cp",
        help="Path to structured domain context directory (e.g. context/). "
        "Overrides auto-discovery. Contains architecture.md, conventions.md, domain/ etc.",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Pipeline profile: fast_track, standard, deep, auto (default: auto)",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Run the full document quality gate pipeline."""
    _ensure_env()
    app_config = load_app_config(config)
    _enable_web_bridge(app_config)

    console.print("\n[bold blue]Doc Quality Gate[/bold blue]")
    console.print(f"File: {file}")
    console.print(f"Type: {type or 'auto-detect'}")
    console.print(f"Profile: {profile or 'auto'}")

    if not project and context_path:
        project = str(Path.cwd())

    if project:
        console.print(f"Project: {project}")
    if context_path:
        console.print(f"Context: {context_path}")
    console.print()

    try:
        orch = Orchestrator(app_config)
        artifacts = orch.run(file, type, project_path=project, context_path=context_path, profile=profile)

        scorecard = artifacts.scorecard
        if scorecard:
            status = "[bold green]PASS[/bold green]" if scorecard.passed else "[bold red]FAIL[/bold red]"
            console.print(
                Panel(
                    f"Score: {scorecard.overall_score}/10 | {status}\n"
                    f"Action: {scorecard.recommended_next_action.value}",
                    title="Gate Decision",
                )
            )

            dim_table = Table(title="Dimension Scores")
            dim_table.add_column("Dimension")
            dim_table.add_column("Score", justify="right")
            for dim, score in scorecard.dimension_scores.model_dump().items():
                color = "green" if score >= 8 else ("yellow" if score >= 6 else "red")
                dim_table.add_row(dim.replace("_", " ").title(), f"[{color}]{score}[/{color}]")
            console.print(dim_table)

        console.print(f"\nArtifacts saved to: {artifacts.output_dir}")
        console.print("  - original.md")
        console.print("  - revised.md")
        console.print("  - issues.json")
        console.print("  - validations.json")
        console.print("  - scorecard.json")
        console.print("  - report.md")
        console.print("  - report.html")
        console.print("  - metadata.json")
        if project:
            console.print("  - domain_context.md")
            console.print("  - domain_analysis.md")
            console.print("  - codebase_context.md")
        if artifacts.fact_check:
            console.print("  - fact_check.json")
            console.print("  - fact_check.md")

        LogBroadcaster.get().stop_http_forward()

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        LogBroadcaster.get().stop_http_forward()
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        LogBroadcaster.get().stop_http_forward()
        raise typer.Exit(1)


@app.command(name="fact-check")
def fact_check_cmd(
    run_id: str = typer.Argument(..., help="Run ID to fact-check"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Run fact-check on an existing run to verify which issues are real."""
    _ensure_env()
    app_config = load_app_config(config)
    setup_logging(app_config.log_level, log_dir=app_config.log_dir)

    console.print("\n[bold blue]Doc Quality Gate - Fact Check[/bold blue]")
    console.print(f"Run ID: {run_id}\n")

    try:
        orch = Orchestrator(app_config)
        artifacts = orch.run_fact_check_only(run_id)

        fc = artifacts.fact_check
        if fc:
            table = Table(title="Sorun Gerçeklik Değerlendirmesi")
            table.add_column("ID", style="bold")
            table.add_column("Durum")
            table.add_column("Gerçeklik")
            table.add_column("Düzeltme")

            from app.schemas import RealityVerdict

            for item in fc.items:
                if item.reality_verdict == RealityVerdict.CONFIRMED:
                    status = "[green]✅ ONAYLANDI[/green]"
                elif item.reality_verdict == RealityVerdict.REFUTED:
                    status = "[red]❌ ÇÜRÜTÜLDÜ[/red]"
                else:
                    status = "[yellow]❓ BELİRSİZ[/yellow]"

                has_fix = "Var" if item.proposed_fix else "Yok"
                table.add_row(
                    item.issue_id,
                    status,
                    f"{item.reality_score:.0%}",
                    has_fix,
                )

            console.print(table)

            summary_panel = Panel(
                f"Onaylanan: {fc.confirmed_count} | "
                f"Çürütülen: {fc.refuted_count} | "
                f"Belirsiz: {fc.uncertain_count}",
                title="Özet",
            )
            console.print(summary_panel)

            if fc.confirmed_count > 0:
                console.print(
                    "\n[cyan]Düzeltme uygulamak için:[/cyan]\n"
                    "1. Çıktı dizininde [bold]approved_fixes.json[/bold] dosyası oluşturun\n"
                    "2. Onayladığınız sorun ID'lerini ekleyin\n"
                    "3. [bold]dqg apply-fixes " + run_id + "[/bold] komutunu çalıştırın\n"
                )

        console.print(f"\nSonuçlar: {artifacts.output_dir}")
        console.print("  - fact_check.json")
        console.print("  - fact_check.md")

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="apply-fixes")
def apply_fixes_cmd(
    run_id: str = typer.Argument(..., help="Run ID to apply fixes for"),
    fixes: Optional[str] = typer.Option(
        None, "--fixes", "-f",
        help="Comma-separated list of issue IDs to fix (e.g., C-001,C-002). "
             "If not specified, reads from approved_fixes.json in the run directory.",
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Apply approved fixes to the original document."""
    _ensure_env()
    app_config = load_app_config(config)
    setup_logging(app_config.log_level, log_dir=app_config.log_dir)

    console.print("\n[bold blue]Doc Quality Gate - Apply Fixes[/bold blue]")
    console.print(f"Run ID: {run_id}")

    try:
        import json

        run_dir = Path(app_config.output_base_dir) / run_id
        if not run_dir.exists():
            console.print(f"[red]Run directory not found: {run_id}[/red]")
            raise typer.Exit(1)

        approved_fix_ids: list[str] = []

        if fixes:
            approved_fix_ids = [f.strip() for f in fixes.split(",") if f.strip()]
            console.print(f"Fixes (CLI): {', '.join(approved_fix_ids)}")
        else:
            approved_file = run_dir / "approved_fixes.json"
            if not approved_file.exists():
                console.print(
                    "[yellow]approved_fixes.json bulunamadı.[/yellow]\n"
                    "Lütfen run dizininde approved_fixes.json oluşturun veya --fixes parametresi kullanın.\n\n"
                    "Örnek approved_fixes.json:\n"
                    '{\n  "run_id": "' + run_id + '",\n  "approved_fix_ids": ["C-001", "C-002"]\n}'
                )
                raise typer.Exit(1)

            with open(approved_file, encoding="utf-8") as af:
                approved_data = json.load(af)
            approved_fix_ids = approved_data.get("approved_fix_ids", [])
            console.print(f"Fixes (dosyadan): {', '.join(approved_fix_ids)}")

        if not approved_fix_ids:
            console.print("[yellow]Uygulanacak düzeltme bulunamadı.[/yellow]")
            raise typer.Exit(0)

        orch = Orchestrator(app_config)
        fixed_path = orch.run_apply_fixes(run_id, approved_fix_ids)

        console.print(
            Panel(
                f"{len(approved_fix_ids)} düzeltme uygulandı\n"
                f"Düzeltilmiş doküman: {fixed_path}",
                title="[bold green]Düzeltmeler Uygulandı[/bold green]",
            )
        )

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def smoke_test(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Verify LiteLLM Proxy connectivity and Promptfoo integration."""
    _ensure_env()
    app_config = load_app_config(config)
    setup_logging(app_config.log_level, log_dir=app_config.log_dir)

    console.print("\n[bold blue]Doc Quality Gate - Smoke Test[/bold blue]\n")

    try:
        orch = Orchestrator(app_config)
        results = orch.smoke_test()

        table = Table(title="Smoke Test Results")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Details")

        for check_name, result in results.items():
            status = result.get("status", "unknown")
            if status == "ok" or result.get("available", False):
                status_str = "[green]OK[/green]"
            elif status == "error":
                status_str = "[red]ERROR[/red]"
            else:
                status_str = "[yellow]UNKNOWN[/yellow]"

            details = ""
            if "error" in result:
                details = str(result["error"])[:80]
            elif "model" in result:
                details = result.get("model", "")
            elif "version" in result:
                details = f"v{result['version']}" if result.get("version") else "N/A"

            table.add_row(check_name, status_str, details)

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[red]Smoke test failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def demo(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Run a full demo with example documents."""
    _ensure_env()
    app_config = load_app_config(config)
    setup_logging(app_config.log_level, log_dir=app_config.log_dir)

    console.print("\n[bold blue]Doc Quality Gate - Demo[/bold blue]\n")

    examples = {
        "feature_spec": str(_PROJECT_ROOT / "examples" / "feature_spec" / "sample.md"),
        "implementation_plan": str(_PROJECT_ROOT / "examples" / "implementation_plan" / "sample.md"),
        "architecture_change": str(_PROJECT_ROOT / "examples" / "architecture_change" / "sample.md"),
    }

    for doc_type, example_path in examples.items():
        if not Path(example_path).exists():
            console.print(f"[yellow]Example not found: {example_path}[/yellow]")
            continue

        console.print(f"[bold]Running demo: {doc_type}[/bold]")
        console.print(f"File: {example_path}\n")

        try:
            orch = Orchestrator(app_config)
            artifacts = orch.run(example_path, doc_type)

            scorecard = artifacts.scorecard
            if scorecard:
                status = "PASS" if scorecard.passed else "FAIL"
                console.print(f"  Result: {status} (Score: {scorecard.overall_score}/10)")
                console.print(f"  Action: {scorecard.recommended_next_action.value}")
                console.print(f"  Issues found: {len(artifacts.issues)}")
                console.print(f"  Artifacts: {artifacts.output_dir}\n")

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]\n")

    console.print("[bold green]Demo complete![/bold green]")


@app.command()
def eval_only(
    run_id: str = typer.Argument(..., help="Run ID to re-evaluate"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Re-run Promptfoo scoring on an existing run."""
    _ensure_env()
    app_config = load_app_config(config)
    setup_logging(app_config.log_level, log_dir=app_config.log_dir)

    console.print("\n[bold blue]Doc Quality Gate - Eval Only[/bold blue]")
    console.print(f"Run ID: {run_id}\n")

    try:
        orch = Orchestrator(app_config)
        artifacts = orch.run_eval_only(run_id)

        scorecard = artifacts.scorecard
        if scorecard:
            status = "[bold green]PASS[/bold green]" if scorecard.passed else "[bold red]FAIL[/bold red]"
            console.print(
                Panel(
                    f"Score: {scorecard.overall_score}/10 | {status}\n"
                    f"Action: {scorecard.recommended_next_action.value}",
                    title="Re-evaluation Result",
                )
            )

        console.print(f"\nUpdated artifacts: {artifacts.output_dir}")

    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def web(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
):
    """Start the web UI."""
    _ensure_env()
    app_config = load_app_config()
    setup_logging("INFO", enable_websocket=True, log_dir=app_config.log_dir)

    import uvicorn

    console.print("\n[bold blue]Doc Quality Gate Web UI[/bold blue]")
    console.print(f"Opening http://localhost:{port}\n")

    uvicorn.run(
        "app.web.app:app",
        host=host,
        port=port,
        log_level="info",
    )


@app.command(name="from-jira")
def from_jira(
    task_key: str = typer.Argument(..., help="Jira issue key (e.g. PROJ-123)"),
    context_path: Optional[str] = typer.Option(
        None,
        "--context-path",
        "--cp",
        help="Path to structured domain context directory (e.g. C:\\projects\\my-context). "
        "If not set, uses DQG_JIRA_DEFAULT_CONTEXT_PATH from config.",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Path to project directory for cross-reference analysis"
    ),
    generate_only: bool = typer.Option(
        False, "--generate-only", "-g", help="Only generate the implementation document, skip DQG analysis"
    ),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config directory"),
):
    """Fetch a Jira task, generate implementation document, and run DQG analysis."""
    _ensure_env()
    app_config = load_app_config(config)
    _enable_web_bridge(app_config)

    console.print("\n[bold blue]Doc Quality Gate - Jira Task Analysis[/bold blue]")
    console.print(f"Task: {task_key}")

    if context_path:
        console.print(f"Context: {context_path}")
    elif app_config.jira.default_context_path:
        console.print(f"Context: {app_config.jira.default_context_path} (auto)")
    if project:
        console.print(f"Project: {project}")
    if generate_only:
        console.print("[yellow]Mode: Generate only (no DQG analysis)[/yellow]")
    console.print()

    try:
        orch = Orchestrator(app_config)
        artifacts = orch.run_from_jira(
            task_key=task_key,
            context_path=context_path,
            project_path=project,
            generate_only=generate_only,
        )

        from app.schemas import TaskClarityStatus

        if artifacts.task_analysis:
            ta = artifacts.task_analysis
            if ta.clarity_status == TaskClarityStatus.CLEAR:
                clarity_color = "green"
            elif ta.clarity_status == TaskClarityStatus.NEEDS_CLARIFICATION:
                clarity_color = "yellow"
            else:
                clarity_color = "red"
            console.print(Panel(
                f"Task: {ta.task_key}\n"
                f"Clarity: [{clarity_color}]{ta.clarity_status.value}"
                f"[/{clarity_color}] ({ta.clarity_score:.1f}/10)\n"
                f"{'Missing: ' + ', '.join(ta.missing_fields) if ta.missing_fields else 'All fields present'}",
                title="Task Analysis",
            ))

        if generate_only:
            console.print(
                f"\n[green]Document generated:[/green] "
                f"{artifacts.output_dir}"
            )
            console.print("  - original.md (implementation document)")
            console.print("  - task_analysis.json")
            cp_val = context_path or app_config.jira.default_context_path or "PATH"
            console.print("\nTo run DQG analysis on this document:")
            console.print(
                f"  [bold]dqg review "
                f"{artifacts.output_dir}\\original.md "
                f"--cp {cp_val}[/bold]"
            )
        else:
            scorecard = artifacts.scorecard
            if scorecard:
                status = "[bold green]PASS[/bold green]" if scorecard.passed else "[bold red]FAIL[/bold red]"
                console.print(Panel(
                    f"Score: {scorecard.overall_score}/10 | {status}\n"
                    f"Action: {scorecard.recommended_next_action.value}",
                    title="Gate Decision",
                ))

                dim_table = Table(title="Dimension Scores")
                dim_table.add_column("Dimension")
                dim_table.add_column("Score", justify="right")
                for dim, score in scorecard.dimension_scores.model_dump().items():
                    color = "green" if score >= 8 else ("yellow" if score >= 6 else "red")
                    dim_table.add_row(dim.replace("_", " ").title(), f"[{color}]{score}[/{color}]")
                console.print(dim_table)

            console.print(f"\nArtifacts saved to: {artifacts.output_dir}")
            console.print("  - original.md")
            console.print("  - revised.md")
            console.print("  - issues.json")
            console.print("  - scorecard.json")
            console.print("  - task_analysis.json")
            if scorecard and not scorecard.passed:
                cp_val = (
                    context_path
                    or app_config.jira.default_context_path
                    or "PATH"
                )
                console.print(
                    f"\n[yellow]Score {scorecard.overall_score}/10 "
                    f"is below 8.0 threshold.[/yellow]\n"
                    "Review the issues and apply fixes:\n"
                    f"  1. Check [bold]"
                    f"{artifacts.output_dir}\\report.md[/bold] for details\n"
                    "  2. Apply fixes and re-run:\n"
                    f"     [bold]dqg review "
                    f"{artifacts.output_dir}\\original.md "
                    f"--cp {cp_val}[/bold]"
                )

        LogBroadcaster.get().stop_http_forward()

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        LogBroadcaster.get().stop_http_forward()
        raise typer.Exit(1)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        LogBroadcaster.get().stop_http_forward()
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        LogBroadcaster.get().stop_http_forward()
        raise typer.Exit(1)
