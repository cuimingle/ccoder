"""Main CLI logic — command definitions, pipe mode, REPL launcher."""
from __future__ import annotations
import asyncio
import os
import sys
import click

from app.query_engine import QueryEngine


@click.group(invoke_without_command=True)
@click.option("-p", "--print", "print_mode", is_flag=True, help="Non-interactive pipe mode")
@click.option("--api-key", envvar="ANTHROPIC_API_KEY", default=None, help="API key (or set ANTHROPIC_API_KEY)")
@click.option("--api-base", envvar="ANTHROPIC_BASE_URL", default=None, help="Custom API base URL (or set ANTHROPIC_BASE_URL)")
@click.option("--model", default="claude-opus-4-6", help="Model name to use")
@click.argument("prompt", required=False)
@click.pass_context
def cli(ctx: click.Context, print_mode: bool, api_key: str | None, api_base: str | None, model: str, prompt: str | None) -> None:
    """Claude Code — AI coding assistant in the terminal."""
    if ctx.invoked_subcommand is not None:
        return
    
    cwd = os.getcwd()

    if print_mode or not sys.stdin.isatty():
        # Pipe mode: read from argument or stdin
        if prompt is None:
            prompt = sys.stdin.read().strip()
        if not prompt:
            click.echo("Error: no prompt provided.", err=True)
            sys.exit(1)
        asyncio.run(run_pipe_mode(prompt=prompt, cwd=cwd, api_key=api_key, api_base=api_base, model=model))
    else:
        # Interactive REPL mode
        from app.screens.repl import ClaudeCodeApp
        from app.state.app_state import AppState

        state = AppState(cwd=cwd, model=model, permission_mode="manual")
        app = ClaudeCodeApp(
            engine=QueryEngine(
                cwd=cwd,
                api_key=api_key,
                base_url=api_base,
                model=model,
                permission_mode="manual",
                permission_callback=None,  # wired below
            ),
            state=state,
        )
        # Wire the permission callback from the app to the engine's executor
        app.engine._tool_executor._permission_callback = app.permission_callback
        app.run()


async def run_pipe_mode(prompt: str, cwd: str, api_key: str | None = None, api_base: str | None = None, model: str = "claude-opus-4-6") -> None:
    """Run a single query in non-interactive pipe mode."""
    engine = QueryEngine(cwd=cwd, api_key=api_key, base_url=api_base, model=model)
    result = await engine.run_turn(prompt)
    print(result.response_text)
