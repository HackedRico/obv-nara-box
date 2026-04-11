"""
Rich-based terminal output helpers for NARA.

All agents import from this module for consistent, styled output.

Interface (contractual — do not change signatures):
    agent_header(name: str) -> None
    stream_output(text: str) -> None
    print_finding(vuln: dict) -> None
    print_kill_chain(steps: list[dict]) -> None
"""

import time
from contextlib import contextmanager
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from rich.spinner import Spinner
from rich.live import Live

console = Console()

_AGENT_COLORS = {
    "SCANNER":   "bright_cyan",
    "PLANNER":   "bright_yellow",
    "EXPLOITER": "bright_red",
    "RANSOMWARE": "red",
    "NARA":      "bright_green",
}

_BANNER = r"""
 ███╗   ██╗ █████╗ ██████╗  █████╗
 ████╗  ██║██╔══██╗██╔══██╗██╔══██╗
 ██╔██╗ ██║███████║██████╔╝███████║
 ██║╚██╗██║██╔══██║██╔══██╗██╔══██║
 ██║ ╚████║██║  ██║██║  ██║██║  ██║
 ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
"""


def print_banner() -> None:
    """Print the NARA ASCII art header on startup."""
    console.print(Text(_BANNER, style="bold bright_red"))
    console.print(
        Panel(
            "[bold white]Autonomous Red Team Platform[/bold white]\n"
            "[dim]Bitcamp 2026 · Cybersecurity Track[/dim]",
            border_style="bright_red",
            expand=False,
        )
    )
    console.print()


def agent_header(name: str) -> None:
    """
    Print a colored panel header for an agent.

    Args:
        name: Agent name — one of SCANNER, PLANNER, EXPLOITER, RANSOMWARE
    """
    color = _AGENT_COLORS.get(name.upper(), "white")
    console.print(
        Panel(
            f"[bold {color}][ {name.upper()} ][/bold {color}]",
            border_style=color,
            expand=False,
            padding=(0, 2),
        )
    )


def stream_output(text: str) -> None:
    """
    Print text line by line, simulating streaming output.

    Args:
        text: Full text to stream to terminal.
    """
    for line in text.splitlines():
        console.print(f"  [dim]│[/dim] {line}")


def print_finding(vuln: dict) -> None:
    """
    Print a single vulnerability finding in a formatted panel.

    Args:
        vuln: Dict with keys: type, file, line, severity, description
              All keys optional — missing keys render as 'unknown'.
    """
    severity = vuln.get("severity", "UNKNOWN").upper()
    color = {
        "CRITICAL": "bold red",
        "HIGH":     "red",
        "MEDIUM":   "yellow",
        "LOW":      "green",
        "INFO":     "dim",
    }.get(severity, "white")

    content = (
        f"[{color}]{severity}[/{color}]  "
        f"[bold]{vuln.get('type', 'Unknown')}[/bold]\n"
        f"[dim]File:[/dim]  {vuln.get('file', 'unknown')}:{vuln.get('line', '?')}\n"
        f"[dim]Info:[/dim]  {vuln.get('description', '')}"
    )
    console.print(Panel(content, border_style=color.split()[-1], expand=False))


def print_kill_chain(steps: list[dict]) -> None:
    """
    Print the kill chain as a numbered step list.

    Args:
        steps: List of dicts with keys: step, command, expected_outcome
    """
    table = Table(
        show_header=True,
        header_style="bold bright_yellow",
        box=box.SIMPLE_HEAVY,
        expand=False,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Step", style="bold white")
    table.add_column("Command", style="bright_cyan")
    table.add_column("Expected Outcome", style="dim")

    for i, step in enumerate(steps, 1):
        table.add_row(
            str(i),
            step.get("step", ""),
            step.get("command", ""),
            step.get("expected_outcome", ""),
        )

    console.print(table)


@contextmanager
def spinner(message: str):
    """
    Context manager that shows a spinner while work is being done.

    Usage:
        with spinner("Running Semgrep..."):
            do_slow_thing()
    """
    with Live(
        Spinner("dots", text=f"[dim]{message}[/dim]"),
        console=console,
        refresh_per_second=10,
        transient=True,
    ):
        yield


def print_error(msg: str) -> None:
    """Print a red error panel."""
    console.print(Panel(f"[bold red]{msg}[/bold red]", border_style="red", expand=False))


def print_success(msg: str) -> None:
    """Print a green success panel."""
    console.print(Panel(f"[bold green]{msg}[/bold green]", border_style="green", expand=False))


def print_info(msg: str) -> None:
    """Print a plain info line."""
    console.print(f"[dim cyan]→[/dim cyan] {msg}")
