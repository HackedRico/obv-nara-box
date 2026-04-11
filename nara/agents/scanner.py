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

    # Condense raw SAST output so it fits in the LLM context window.
    # Semgrep JSON can be huge; extract just the results array.
    semgrep_condensed = _condense_semgrep(semgrep_out) if semgrep_out else "(no output — tool not available)"
    bandit_condensed = _condense_bandit(bandit_out) if bandit_out else "(no output — tool not available)"

    ui.print_info("Sending findings to LLM for triage and deduplication...")

    llm = LLMClient()
    messages = [{
        "role": "user",
        "content": (
            f"Semgrep results:\n{semgrep_condensed}\n\n"
            f"Bandit results:\n{bandit_condensed}\n\n"
            f"Target path: {target_path}"
        )
    }]

    # Parse Bandit findings as a baseline (always available)
    bandit_findings = _parse_bandit_fallback(bandit_out)

    raw = None
    try:
        with ui.spinner("LLM triaging findings..."):
            raw = llm.chat(messages, system=_SYSTEM_PROMPT, ollama_json=True)
        findings = parse_json_array_from_llm(raw)
        findings = [_normalize_finding(f) for f in findings]

        # If LLM returned suspiciously few findings, merge in Bandit baseline
        if len(findings) < len(bandit_findings):
            ui.print_info(f"LLM returned {len(findings)} finding(s) but tools found {len(bandit_findings)} — merging.")
            findings = _merge_findings(findings, bandit_findings)
    except (json.JSONDecodeError, RuntimeError) as e:
        ui.print_error(f"LLM triage failed: {e}")
        if raw:
            ui.print_info(f"Raw LLM response (first 500 chars): {raw[:500]}")
        ui.print_info("Falling back to raw tool output parsing.")
        findings = bandit_findings

    session["findings"] = findings
    ui.print_info(f"Scanner complete — {len(findings)} finding(s).")
    return findings


# ------------------------------------------------------------------ #
# SAST output condensers                                                #
# ------------------------------------------------------------------ #

_MAX_RESULTS = 20  # Cap findings sent to LLM to keep context small


def _condense_semgrep(raw: str) -> str:
    """Extract just the results from Semgrep JSON, trimmed for LLM context."""
    try:
        data = json.loads(raw)
        results = data.get("results", [])[:_MAX_RESULTS]
        condensed = []
        for r in results:
            condensed.append({
                "rule": r.get("check_id", ""),
                "file": r.get("path", ""),
                "line": r.get("start", {}).get("line", 0),
                "message": r.get("extra", {}).get("message", "")[:200],
                "severity": r.get("extra", {}).get("severity", ""),
                "code_snippet": r.get("extra", {}).get("lines", "")[:200],
            })
        return json.dumps(condensed, indent=2) if condensed else "(no results)"
    except (json.JSONDecodeError, KeyError):
        return raw[:4000]


def _condense_bandit(raw: str) -> str:
    """Extract just the results from Bandit JSON, trimmed for LLM context."""
    try:
        data = json.loads(raw)
        results = data.get("results", [])[:_MAX_RESULTS]
        condensed = []
        for r in results:
            condensed.append({
                "test_id": r.get("test_id", ""),
                "test_name": r.get("test_name", ""),
                "file": r.get("filename", ""),
                "line": r.get("line_number", 0),
                "issue": r.get("issue_text", "")[:200],
                "severity": r.get("issue_severity", ""),
                "confidence": r.get("issue_confidence", ""),
                "code_snippet": r.get("code", "")[:200],
            })
        return json.dumps(condensed, indent=2) if condensed else "(no results)"
    except (json.JSONDecodeError, KeyError):
        return raw[:4000]


def _normalize_finding(f: dict) -> dict:
    """Ensure every finding dict has the expected keys, mapping common alternatives."""
    # Map alternative key names the LLM might use
    _ALT = {
        "type": ["vulnerability_type", "vuln_type", "category", "kind", "test_name", "check_id", "rule"],
        "file": ["filename", "path", "filepath", "file_path", "source_file"],
        "line": ["line_number", "lineno", "start_line", "line_no"],
        "severity": ["issue_severity", "risk", "level", "priority"],
        "description": ["issue_text", "message", "desc", "summary", "detail", "issue"],
        "exploitability": ["exploit", "attack_vector", "exploitation", "how_to_exploit"],
    }
    normalized = {}
    for key, alts in _ALT.items():
        val = f.get(key)
        if not val or val == "":
            for alt in alts:
                val = f.get(alt)
                if val and val != "":
                    break
        normalized[key] = val or ("Other" if key == "type" else "unknown" if key == "file" else 0 if key == "line" else "medium" if key == "severity" else "")
    return normalized


def _merge_findings(llm_findings: list[dict], bandit_findings: list[dict]) -> list[dict]:
    """Merge LLM-triaged findings with Bandit baseline, deduplicating by file+line."""
    seen = set()
    merged = []
    # LLM findings take priority (better descriptions)
    for f in llm_findings:
        key = (f.get("file", ""), f.get("line", 0))
        seen.add(key)
        merged.append(f)
    # Add Bandit findings not already covered
    for f in bandit_findings:
        key = (f.get("file", ""), f.get("line", 0))
        if key not in seen:
            seen.add(key)
            merged.append(f)
    return merged


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
        _TYPE_MAP = {
            "B102": "CommandInjection", "B602": "CommandInjection",
            "B603": "CommandInjection", "B604": "CommandInjection",
            "B608": "SQLi", "B610": "SQLi", "B611": "SQLi",
            "B301": "Other", "B303": "Other", "B501": "Other",
            "B201": "CommandInjection",
        }
        for r in results[:_MAX_RESULTS]:
            test_id = r.get("test_id", "")
            findings.append({
                "type": _TYPE_MAP.get(test_id, r.get("test_name", "Other")),
                "file": r.get("filename", "unknown"),
                "line": r.get("line_number", 0),
                "severity": r.get("issue_severity", "medium").lower(),
                "description": r.get("issue_text", ""),
                "exploitability": f"Bandit {test_id}: {r.get('issue_confidence', 'MEDIUM')} confidence.",
            })
        return findings
    except Exception:
        return []
