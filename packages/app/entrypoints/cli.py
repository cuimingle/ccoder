"""CLI entrypoint — injects global state before any other imports."""
from __future__ import annotations
import asyncio
import sys


def main() -> None:
    """Main entry point for the claude-code CLI."""
    # Import here to ensure bootstrap state is initialized first
    from app.main import cli
    cli()


if __name__ == "__main__":
    main()
