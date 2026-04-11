"""
Agent 1 — Scanner

Runs Semgrep and Bandit against a target codebase, then uses the LLM to
deduplicate and prioritize findings into a structured list.
"""

import json
import os
import subprocess
import sys
from nara.utils.llm_client import LLMClient
from nara.utils.llm_json import parse_json_array_from_llm
from nara.utils import terminal_ui as ui

_SYSTEM_PROMPT = """You are a senior application security engineer.
You will receive raw output from Semgrep and Bandit static analysis tools.
Your job is to:
1. Deduplicate findings (same vulnerability reported by both tools = one entry)
2. Prioritize by exploitability, not just severity score
3. For each finding, assess whether it is actually exploitable in a web context
4. Return ONLY a JSON array. No explanation. No markdown. Raw JSON only.

Each object must have exactly these keys:
{
  "type": "XSS|SQLi|CommandInjection|FileUpload|SSRF|HardcodedSecret|Other",
  "file": "relative/path/to/file.py",
  "line": 42,
  "severity": "critical|high|medium|low",
  "description": "one sentence describing the vulnerability and its impact",
  "exploitability": "one sentence on how an attacker would trigger this"
}

If there are no real findings, return an empty array: []"""


def run(target_path: str, session: dict) -> list[dict]:
    """
    Scan the target codebase and return structured vulnerability findings.

    Args:
        target_path: Absolute or relative path to the codebase to scan.
        session:     Shared session dict (findings written back here too).

    Returns:
        List of finding dicts with keys: type, file, line, severity,
        description, exploitability.
    """
    ui.agent_header("SCANNER")

    semgrep_out = _run_semgrep(target_path)
    bandit_out = _run_bandit(target_path)

    if not semgrep_out and not bandit_out:
        ui.print_error("Both Semgrep and Bandit failed or produced no output. Cannot scan.")
        return []

    ui.print_info("Sending findings to LLM for triage and deduplication...")

    llm = LLMClient()
    messages = [{
        "role": "user",
        "content": (
            f"Semgrep output:\n{semgrep_out or '(no output — tool not available)'}\n\n"
            f"Bandit output:\n{bandit_out or '(no output — tool not available)'}\n\n"
            f"Target path: {target_path}"
        )
    }]

    try:
        with ui.spinner("LLM triaging findings..."):
            raw = llm.chat(messages, system=_SYSTEM_PROMPT, ollama_json=True)
        findings = parse_json_array_from_llm(raw)
    except (json.JSONDecodeError, RuntimeError) as e:
        ui.print_error(f"LLM triage failed: {e}")
        ui.print_info("Falling back to raw tool output parsing.")
        findings = _parse_bandit_fallback(bandit_out)

    session["findings"] = findings
    ui.print_info(f"Scanner complete — {len(findings)} finding(s).")
    return findings


# ------------------------------------------------------------------ #
# Tool runners                                                         #
# ------------------------------------------------------------------ #

_EXCLUDE_DIRS = [".venv", "venv", "__pycache__", ".git", "node_modules", ".egg-info", "build", "dist"]


def _run_semgrep(target_path: str) -> str:
    """Run semgrep and return raw JSON output string, or empty string on failure."""
    try:
        cmd = [
            "semgrep", "--config", "auto", target_path, "--json",
            "--no-rewrite-rule-ids", "--quiet",
        ]
        for d in _EXCLUDE_DIRS:
            cmd.extend(["--exclude", d])
        ui.print_info("Running Semgrep...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.stdout or ""
    except FileNotFoundError:
        ui.print_info("Semgrep not found — skipping. Install: pip install semgrep")
        return ""
    except subprocess.TimeoutExpired:
        ui.print_info("Semgrep timed out after 120s — partial results may be missing.")
        return ""
    except Exception as e:
        ui.print_info(f"Semgrep error: {e}")
        return ""


def _run_bandit(target_path: str) -> str:
    """Run bandit and return raw JSON output string, or empty string on failure."""
    try:
        exclude = ",".join(
            os.path.join(target_path, d) for d in _EXCLUDE_DIRS
        )
        ui.print_info("Running Bandit...")
        result = subprocess.run(
            ["bandit", "-r", target_path, "-f", "json", "-q", "--exclude", exclude],
            capture_output=True, text=True, timeout=60
        )
        # Bandit exits non-zero when it finds issues — that's normal
        return result.stdout or ""
    except FileNotFoundError:
        ui.print_info("Bandit not found — skipping. Install: pip install bandit")
        return ""
    except subprocess.TimeoutExpired:
        ui.print_info("Bandit timed out after 60s.")
        return ""
    except Exception as e:
        ui.print_info(f"Bandit error: {e}")
        return ""


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _parse_bandit_fallback(bandit_out: str) -> list[dict]:
    """
    Best-effort parse of raw bandit JSON into our finding format.
    Used only when LLM triage fails.
    """
    if not bandit_out:
        return []
    try:
        data = json.loads(bandit_out)
        results = data.get("results", [])
        findings = []
        for r in results[:10]:  # Cap at 10 raw results
            findings.append({
                "type": r.get("test_name", "Unknown"),
                "file": r.get("filename", "unknown"),
                "line": r.get("line_number", 0),
                "severity": r.get("issue_severity", "medium").lower(),
                "description": r.get("issue_text", ""),
                "exploitability": "See Bandit output for details.",
            })
        return findings
    except Exception:
        return []
