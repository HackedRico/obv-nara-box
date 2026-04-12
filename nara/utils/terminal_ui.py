"""
Rich-based terminal output helpers for NARA.

All agents import from this module for consistent, styled output.

Interface (contractual — do not change signatures):
    agent_header(name: str) -> None
    stream_output(text: str) -> None
    print_finding(vuln: dict) -> None
    print_kill_chain(steps: list[dict]) -> None
"""

import random
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


# ------------------------------------------------------------------ #
# Dramatic hacker-aesthetic effects                                    #
# ------------------------------------------------------------------ #

def print_exploit_start(target: str = "localhost:8080", steps: int = 0) -> None:
    """Print a dramatic attack initiation sequence before the kill chain fires."""
    console.print()
    console.print("  [bold bright_red]>> ATTACK SEQUENCE INITIATED[/bold bright_red]")
    time.sleep(0.15)
    console.print(f"  [dim red]   Target locked  : {target}[/dim red]")
    time.sleep(0.06)
    console.print(f"  [dim red]   Kill chain     : {steps} steps loaded[/dim red]")
    time.sleep(0.06)
    console.print("  [dim red]   Exploit mode   : AUTONOMOUS[/dim red]")
    time.sleep(0.06)
    console.print("  [bold bright_red]>> ENGAGING[/bold bright_red]")
    time.sleep(0.15)
    console.print()


def print_system_compromised() -> None:
    """Dramatic terminal takeover when ransomware deploys — hex dump, PWNED banner, panel."""
    console.print()

    # ── Rapid hex dump scroll — looks like data exfiltration ──────────
    for _ in range(12):
        addr = random.randint(0x400000, 0x7FFFFF)
        hex_bytes = " ".join(f"{random.randint(0, 255):02x}" for _ in range(16))
        ascii_repr = "".join(
            chr(random.randint(33, 126)) if random.random() > 0.3 else "."
            for _ in range(16)
        )
        console.print(
            f"  [dim red]0x{addr:06x}[/dim red]  "
            f"[red]{hex_bytes}[/red]  "
            f"[dim]|{ascii_repr}|[/dim]"
        )
        time.sleep(0.03)

    console.print()

    # ── PWNED ASCII banner — line-by-line reveal ─────────────────────
    _PWNED = (
        "  ██████╗ ██╗    ██╗███╗   ██╗███████╗██████╗ \n"
        "  ██╔══██╗██║    ██║████╗  ██║██╔════╝██╔══██╗\n"
        "  ██████╔╝██║ █╗ ██║██╔██╗ ██║█████╗  ██║  ██║\n"
        "  ██╔═══╝ ██║███╗██║██║╚██╗██║██╔══╝  ██║  ██║\n"
        "  ██║     ╚███╔███╔╝██║ ╚████║███████╗██████╔╝\n"
        "  ╚═╝      ╚══╝╚══╝ ╚═╝  ╚═══╝╚══════╝╚═════╝ "
    )
    for line in _PWNED.splitlines():
        console.print(f"[bold bright_red]{line}[/bold bright_red]")
        time.sleep(0.04)

    console.print()
    console.print(Panel(
        "[bold bright_red]RANSOMWARE DEPLOYED — ALL FILES ENCRYPTED[/bold bright_red]\n\n"
        "[white]Desktop hijacked.  Wallpaper replaced.  Shortcuts locked.[/white]\n"
        "[dim]Security research demonstration — run 'reset' to restore.[/dim]",
        border_style="bright_red",
        title="[bold bright_red][ NARA RANSOMWARE ][/bold bright_red]",
        title_align="center",
        expand=True,
        padding=(1, 4),
    ))
    console.print()


def print_exploit_report(session: dict, results: list[dict]) -> None:
    """Render a professional penetration test report after exploitation."""
    from datetime import datetime

    findings = session.get("findings", [])
    kill_chain = session.get("kill_chain", [])
    target = session.get("target_repo", session.get("scan_path", "unknown"))

    total = len(results)
    succeeded = sum(1 for r in results if r["status"] == "success")

    # ── Header ────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "[bold bright_white]NARA EXPLOITATION REPORT[/bold bright_white]",
        border_style="bright_red",
        expand=True,
        padding=(0, 2),
    ))

    # ── Target ────────────────────────────────────────────────────────
    console.print(f"\n  [bold bright_red]── TARGET ─────────────────────────────────[/bold bright_red]")
    console.print(f"  [dim]Date:[/dim]       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  [dim]Target:[/dim]     {target}")
    if session.get("scan_path") and session.get("scan_path") != target:
        console.print(f"  [dim]Scan path:[/dim]  {session['scan_path']}")

    # ── Vulnerabilities ───────────────────────────────────────────────
    if findings:
        console.print(f"\n  [bold bright_red]── VULNERABILITIES DISCOVERED ({len(findings)}) ────────[/bold bright_red]")
        vuln_table = Table(box=box.SIMPLE, expand=False, padding=(0, 2))
        vuln_table.add_column("#", style="dim", width=3)
        vuln_table.add_column("Severity", width=10)
        vuln_table.add_column("Type", style="bold white")
        vuln_table.add_column("Location", style="dim")
        vuln_table.add_column("Description", style="dim", max_width=40)

        sev_colors = {"CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}
        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "?").upper()
            vuln_table.add_row(
                str(i),
                f"[{sev_colors.get(sev, 'white')}]{sev}[/{sev_colors.get(sev, 'white')}]",
                f.get("type", "Unknown"),
                f"{f.get('file', '?')}:{f.get('line', '?')}",
                (f.get("description", "") or "")[:60],
            )
        console.print(vuln_table)

    # ── Kill chain ────────────────────────────────────────────────────
    console.print(f"\n  [bold bright_red]── KILL CHAIN EXECUTION ────────────────────[/bold bright_red]")
    chain_table = Table(box=box.SIMPLE, expand=False, padding=(0, 2))
    chain_table.add_column("#", style="dim", width=3)
    chain_table.add_column("Step", style="bold white")
    chain_table.add_column("MITRE ATT&CK TTP", style="dim")
    chain_table.add_column("Status")

    status_display = {
        "success": "[bold green]✓ SUCCESS[/bold green]",
        "failed":  "[bold red]✗ FAILED[/bold red]",
        "aborted": "[yellow]⊘ ABORTED[/yellow]",
    }
    for i, r in enumerate(results, 1):
        mitre = kill_chain[i - 1].get("mitre_tactic", "") if i <= len(kill_chain) else ""
        chain_table.add_row(
            str(i), r["step"], mitre,
            status_display.get(r["status"], r["status"]),
        )
    console.print(chain_table)

    # ── Assessment ────────────────────────────────────────────────────
    rate = (succeeded / total * 100) if total else 0
    if succeeded == total:
        impact, impact_style, impact_msg = "CRITICAL", "bold red", "Full system compromise achieved"
    elif succeeded > 0:
        impact, impact_style, impact_msg = "HIGH", "red", "Partial system compromise"
    else:
        impact, impact_style, impact_msg = "LOW", "yellow", "Exploitation unsuccessful"

    console.print(f"\n  [bold bright_red]── ASSESSMENT ─────────────────────────────[/bold bright_red]")
    console.print(f"  Steps executed : {succeeded}/{total}")
    console.print(f"  Success rate   : {rate:.0f}%")
    console.print(f"  Impact         : [{impact_style}]{impact} — {impact_msg}[/{impact_style}]")

    # ── Recommendations ───────────────────────────────────────────────
    if findings:
        recs: set[str] = set()
        for f in findings:
            vt = (f.get("type") or "").lower()
            if "command" in vt or "injection" in vt and "sql" not in vt:
                recs.add("Sanitize all user input passed to os.system() / subprocess")
            if "sql" in vt:
                recs.add("Use parameterized queries — never concatenate user input into SQL")
            if "xss" in vt:
                recs.add("Escape user-controlled output in HTML templates")
            if "upload" in vt or "file" in vt:
                recs.add("Validate file types and restrict upload directories")
            if "ssrf" in vt:
                recs.add("Restrict outbound requests to allowlisted hosts")
            if "secret" in vt or "hardcoded" in vt:
                recs.add("Move secrets to environment variables or a vault")
        if not recs:
            recs.add("Review and remediate all identified vulnerabilities")

        console.print(f"\n  [bold bright_red]── RECOMMENDATIONS ────────────────────────[/bold bright_red]")
        for rec in sorted(recs):
            console.print(f"  [dim]•[/dim] {rec}")

    console.print()
    console.print(Panel(
        "[dim]NARA Autonomous Red Team Platform — Bitcamp 2026[/dim]",
        border_style="dim red",
        expand=True,
    ))
    console.print()
