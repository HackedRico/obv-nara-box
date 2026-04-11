"""
Agent 1 — Scanner

STUB — Person 4 replaces the body of `run()`. Do not change the signature.

Responsibilities (Person 4):
  - Run Semgrep against target_path
  - Run Bandit against Python files in target_path
  - Collect combined output, pass to LLM to deduplicate and prioritize
  - Return structured findings list

Dependencies available:
  - from nara.utils.llm_client import LLMClient
  - from nara.utils import terminal_ui as ui
"""

from nara.utils import terminal_ui as ui


def run(target_path: str, session: dict) -> list[dict]:
    """
    Scan the target codebase and return structured vulnerability findings.

    Args:
        target_path: Absolute path to the codebase to scan.
        session:     Shared session dict (read/write — store findings here too).

    Returns:
        List of finding dicts:
        [
            {
                "type": str,          # e.g. "Command Injection"
                "file": str,          # relative file path
                "line": int,          # line number
                "severity": str,      # CRITICAL | HIGH | MEDIUM | LOW | INFO
                "description": str,   # human-readable exploit notes
            },
            ...
        ]
    """
    # ── STUB ─────────────────────────────────────────────────────────────
    ui.agent_header("SCANNER")
    ui.print_info("Scanner agent not yet implemented — Person 4's job.")
    ui.print_info(f"Would scan: {target_path}")
    return []
    # ── END STUB ──────────────────────────────────────────────────────────
