"""
Agent 2 — Planner

STUB — Person 4 replaces the body of `run()`. Do not change the signature.

Responsibilities (Person 4):
  - Take Scanner findings as input
  - Use LLM (system prompt: red team kill chain architect) to design ordered attack sequence
  - Always include ransomware deployment as the final step
  - Return kill chain as ordered steps

Dependencies available:
  - from nara.utils.llm_client import LLMClient
  - from nara.utils import terminal_ui as ui
"""

from nara.utils import terminal_ui as ui


def run(findings: list[dict], session: dict) -> list[dict]:
    """
    Design an ordered kill chain from scanner findings.

    Args:
        findings: Output from scanner.run() — list of finding dicts.
        session:  Shared session dict (read/write — store kill_chain here too).

    Returns:
        Kill chain as ordered steps:
        [
            {
                "step": str,              # human-readable step name
                "command": str,           # exact command or payload to run
                "expected_outcome": str,  # what success looks like
            },
            ...
        ]
        Final step should always be ransomware deployment.
    """
    # ── STUB ─────────────────────────────────────────────────────────────
    ui.agent_header("PLANNER")
    ui.print_info("Planner agent not yet implemented — Person 4's job.")
    ui.print_info(f"Would plan against {len(findings)} finding(s).")
    return []
    # ── END STUB ──────────────────────────────────────────────────────────
