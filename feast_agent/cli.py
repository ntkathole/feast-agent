"""CLI entry point for the Feast Agent."""

from __future__ import annotations

import json
import textwrap

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from feast_agent.config import AgentConfig

console = Console()

VERBOSITY_INFO = 0
VERBOSITY_VERBOSE = 1
VERBOSITY_DEBUG = 2


@click.group()
@click.option(
    "--repo-path", "-r",
    default=".",
    envvar="FEAST_AGENT_REPO_PATH",
    help="Path to the Feast feature repository.",
)
@click.option(
    "--provider", "-p",
    default=None,
    envvar="FEAST_AGENT_LLM_PROVIDER",
    help="LLM provider: openai, anthropic, or ollama.",
)
@click.option(
    "--model", "-m",
    default=None,
    envvar="FEAST_AGENT_LLM_MODEL",
    help="LLM model name (e.g. gpt-4o, claude-sonnet-4-20250514).",
)
@click.option(
    "--remote-registry", "-R",
    default=None,
    envvar="FEAST_AGENT_REMOTE_REGISTRY_URL",
    help="Remote Feast registry gRPC URL (e.g. feast-registry.example.com:6570).",
)
@click.option(
    "--auth-type",
    default=None,
    envvar="FEAST_AGENT_AUTH_TYPE",
    type=click.Choice(["no_auth", "oidc", "kubernetes"], case_sensitive=False),
    help="Authentication type for the Feast registry.",
)
@click.option(
    "--yaml", "-f",
    default=None,
    envvar="FEAST_AGENT_FEATURE_STORE_YAML",
    help="Explicit path to feature_store.yaml.",
)
@click.option(
    "-v", "--verbose",
    count=True,
    envvar="FEAST_AGENT_VERBOSITY",
    help="Increase output verbosity (-v for tool calls, -vv for full debug).",
)
@click.pass_context
def cli(
    ctx,
    repo_path: str,
    provider: str | None,
    model: str | None,
    remote_registry: str | None,
    auth_type: str | None,
    yaml: str | None,
    verbose: int,
):
    """Feast Agent — manage your feature store with natural language."""
    ctx.ensure_object(dict)
    kwargs: dict = {"repo_path": repo_path}
    if provider:
        kwargs["llm_provider"] = provider
    if model:
        kwargs["llm_model"] = model
    if remote_registry:
        kwargs["remote_registry_url"] = remote_registry
    if auth_type:
        kwargs["auth_type"] = auth_type
    if yaml:
        kwargs["feature_store_yaml"] = yaml
    ctx.obj["config"] = AgentConfig(**kwargs)
    ctx.obj["verbosity"] = verbose


def _truncate(text: str, limit: int = 300) -> str:
    """Truncate long strings for debug display."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _chat_info(verbosity: int) -> str:
    """Return a verbosity-level hint for the banner."""
    if verbosity >= VERBOSITY_DEBUG:
        return "debug"
    if verbosity >= VERBOSITY_VERBOSE:
        return "verbose"
    return "info"


def _handle_turn_info(agent, message: str) -> str:
    """Default (info) mode: spinner while agent works, print final answer."""
    with console.status("[bold blue]Thinking…[/bold blue]"):
        return agent.invoke(message)


def _handle_turn_verbose(agent, message: str) -> None:
    """Verbose (-v): show tool call names, then final answer."""
    console.print("  [dim]Thinking…[/dim]")
    response_text = ""

    for kind, payload in agent.stream_events(message):
        if kind == "tool_start":
            console.print(f"  [dim]↳ calling [bold]{payload['name']}[/bold]…[/dim]")
        elif kind == "tool_end":
            pass
        elif kind == "response":
            response_text = payload

    if response_text:
        console.print("[bold blue]Agent:[/bold blue]", Markdown(response_text))
    else:
        console.print("  [dim](no response)[/dim]")


def _handle_turn_debug(agent, message: str) -> None:
    """Debug (-vv): show tool names, args, results, then final answer."""
    console.print("  [dim]Thinking…[/dim]")
    response_text = ""

    for kind, payload in agent.stream_events(message):
        if kind == "tool_start":
            name = payload["name"]
            args = payload.get("args", {})
            console.print(f"  [dim]↳ calling [bold]{name}[/bold][/dim]")
            if args:
                formatted = json.dumps(args, indent=2, default=str)
                for line in formatted.splitlines():
                    console.print(f"  [dim]    {line}[/dim]")
        elif kind == "tool_end":
            name = payload["name"]
            result = payload.get("result", "")
            preview = _truncate(str(result))
            console.print(f"  [dim]  ← {name} returned:[/dim]")
            for line in textwrap.wrap(preview, width=90):
                console.print(f"  [dim]    {line}[/dim]")
        elif kind == "response":
            response_text = payload

    if response_text:
        console.print("[bold blue]Agent:[/bold blue]", Markdown(response_text))
    else:
        console.print("  [dim](no response)[/dim]")


@cli.command()
@click.pass_context
def chat(ctx):
    """Start an interactive chat session with the Feast Agent."""
    config: AgentConfig = ctx.obj["config"]
    verbosity: int = ctx.obj["verbosity"]

    conn_info = f"Repo: {config.resolved_repo_path}"
    if config.is_remote:
        conn_info = f"Remote: {config.remote_registry_url}"
    auth_info = f"Auth: {config.auth_type}"

    console.print(
        Panel(
            "[bold]Feast Agent[/bold]\n"
            f"{conn_info}\n"
            f"{auth_info}\n"
            f"LLM:  {config.llm_provider}/{config.llm_model}\n"
            f"Log:  {_chat_info(verbosity)}\n\n"
            "Type your request in natural language. Type 'exit' or 'quit' to leave.",
            title="feast-agent",
            border_style="blue",
        )
    )

    from feast_agent.agent import create_agent

    agent = create_agent(config=config)

    while True:
        try:
            user_input = console.input("[bold green]You:[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        stripped = user_input.strip()
        if not stripped:
            continue
        if stripped.lower() in ("exit", "quit", "q"):
            console.print("Goodbye!")
            break

        try:
            if verbosity >= VERBOSITY_DEBUG:
                _handle_turn_debug(agent, stripped)
            elif verbosity >= VERBOSITY_VERBOSE:
                _handle_turn_verbose(agent, stripped)
            else:
                response = _handle_turn_info(agent, stripped)
                console.print("[bold blue]Agent:[/bold blue]", Markdown(response))
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            continue


@cli.command()
@click.argument("message")
@click.pass_context
def run(ctx, message: str):
    """Execute a single command and print the result.

    MESSAGE is the natural language instruction to execute.
    """
    config: AgentConfig = ctx.obj["config"]

    from feast_agent.agent import create_agent

    agent = create_agent(config=config)

    with console.status("[bold blue]Thinking...[/bold blue]"):
        try:
            response = agent.invoke(message)
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise SystemExit(1)

    console.print(Markdown(response))


@cli.command()
@click.pass_context
def status(ctx):
    """Show the current state of the Feast feature store (no LLM needed)."""
    config: AgentConfig = ctx.obj["config"]

    try:
        store = config.build_feature_store()
    except Exception as e:
        console.print(f"[bold red]Error connecting to Feast:[/bold red] {e}")
        raise SystemExit(1)

    ds = store.list_data_sources()
    ent = store.list_entities()
    fv = store.list_feature_views()
    odfv = store.list_on_demand_feature_views()
    sfv = store.list_stream_feature_views()
    fs = store.list_feature_services()

    table_data = [
        ("Data Sources", len(ds), ", ".join(d.name for d in ds) or "—"),
        ("Entities", len(ent), ", ".join(e.name for e in ent) or "—"),
        ("Feature Views", len(fv), ", ".join(v.name for v in fv) or "—"),
        ("On-Demand FVs", len(odfv), ", ".join(v.name for v in odfv) or "—"),
        ("Stream FVs", len(sfv), ", ".join(v.name for v in sfv) or "—"),
        ("Feature Services", len(fs), ", ".join(s.name for s in fs) or "—"),
    ]

    from rich.table import Table

    table = Table(title="Feast Feature Store Status", border_style="blue")
    table.add_column("Object Type", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Names")

    for obj_type, count, names in table_data:
        table.add_row(obj_type, str(count), names)

    console.print(table)


if __name__ == "__main__":
    cli()
