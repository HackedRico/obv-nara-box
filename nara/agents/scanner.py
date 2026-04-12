"""
Agent 1 — Scanner

Runs Semgrep and Bandit against a target codebase, then uses the LLM to
deduplicate and prioritize findings into a structured list.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from nara.utils.llm_client import LLMClient
from nara.utils.llm_json import parse_json_array_from_llm
from nara.utils import terminal_ui as ui

_SYSTEM_PROMPT = """You are a senior application security engineer.
You will receive raw output from Semgrep and Bandit static analysis tools.
Your job is to:
1. Deduplicate: at most ONE object per unique (file, line). Merge overlapping rules into one description.
2. Prioritize by exploitability in a web context, not just severity score.
3. Classify `type` from the actual issue (e.g. SQL string building -> SQLi; subprocess/os.system -> CommandInjection; debug=True -> Other or note debugger risk — not generic "Other" unless truly miscellaneous).
4. Return ONLY a JSON array. No explanation. No markdown. Raw JSON only.

Each object must have exactly these keys:
{
  "type": "XSS|SQLi|CommandInjection|FileUpload|SSRF|HardcodedSecret|Other",
  "file": "relative/path/from/project/root.py",
  "line": 42,
  "severity": "critical|high|medium|low",
  "description": "one sentence describing the vulnerability and its impact",
  "exploitability": "one sentence on how an attacker would trigger this"
}

CRITICAL: `file` must be a path relative to the project root (e.g. app.py or src/foo.py). Never use absolute paths like /Users/... or /home/... .

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
        findings = _findings_list_to_dicts(findings)

        # If LLM returned suspiciously few findings, merge in Bandit baseline
        if len(findings) < len(bandit_findings):
            ui.print_info(f"LLM returned {len(findings)} finding(s) but tools found {len(bandit_findings)} — merging.")
            findings = _merge_findings(findings, bandit_findings)
    except (json.JSONDecodeError, RuntimeError, AttributeError, TypeError):
        ui.print_info("LLM triage unavailable — using SAST tool output directly.")
        findings = bandit_findings

    project_root = os.path.abspath(target_path)
    findings = _finalize_findings(findings, project_root)

    session["findings"] = findings
    ui.print_info(f"Scanner complete — {len(findings)} finding(s).")
    return findings


# ------------------------------------------------------------------ #
# SAST output condensers                                                #
# ------------------------------------------------------------------ #

_MAX_RESULTS = 10  # Cap findings sent to LLM — Phi-4-mini has a 4096-token context


def _as_dict(val) -> dict:
    """Semgrep/Bandit JSON occasionally uses wrong types; .get must only run on dicts."""
    return val if isinstance(val, dict) else {}


def _condense_semgrep(raw: str) -> str:
    """Extract just the results from Semgrep JSON, trimmed for LLM context."""
    try:
        data = json.loads(raw)
        results = data.get("results", [])[:_MAX_RESULTS]
        condensed = []
        for r in results:
            ex = _as_dict(r.get("extra"))
            st = _as_dict(r.get("start"))
            lines_val = ex.get("lines", "")
            if not isinstance(lines_val, str):
                lines_val = str(lines_val) if lines_val is not None else ""
            condensed.append({
                "rule": r.get("check_id", ""),
                "file": r.get("path", ""),
                "line": st.get("line", 0),
                "message": (ex.get("message") or "")[:200],
                "severity": ex.get("severity", ""),
                "code_snippet": lines_val[:200],
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


def _findings_list_to_dicts(findings: list) -> list[dict]:
    """
    LLMs sometimes emit JSON arrays with strings or other junk mixed in.
    Keep only dict rows; coerce bare strings into minimal finding objects.
    """
    out: list[dict] = []
    for i, f in enumerate(findings):
        if isinstance(f, dict):
            out.append(_normalize_finding(f))
        elif isinstance(f, str) and f.strip():
            out.append(_normalize_finding({
                "type": "Other",
                "description": f.strip(),
                "exploitability": "LLM returned a text row instead of an object.",
            }))
        else:
            ui.print_info(f"Skipping invalid finding[{i}] ({type(f).__name__})")
    return out


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
    # Coerce line to int for stable dedupe keys
    try:
        normalized["line"] = int(normalized["line"]) if normalized.get("line") not in (None, "") else 0
    except (TypeError, ValueError):
        normalized["line"] = 0
    return normalized


def _finalize_findings(findings: list[dict], project_root: str) -> list[dict]:
    """Strip absolute paths to project-relative; collapse duplicate file+line rows."""
    rel = [_relativize_finding_paths(f, project_root) for f in findings]
    return _dedupe_by_location(rel)


def _relativize_finding_paths(f: dict, project_root: str) -> dict:
    """Replace host-absolute paths with paths relative to the scanned tree."""
    project_root = os.path.normpath(os.path.abspath(project_root))
    raw = (f.get("file") or "").strip()
    if not raw or raw == "unknown":
        return f
    out = dict(f)
    try:
        if os.path.isabs(raw):
            ar = os.path.normpath(raw)
            if ar == project_root:
                out["file"] = "."
            elif ar.startswith(project_root + os.sep):
                out["file"] = os.path.relpath(ar, project_root)
            else:
                out["file"] = os.path.basename(ar)
        else:
            out["file"] = raw.replace("\\", "/").lstrip("./")
    except (OSError, ValueError):
        pass
    return out


_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _dedupe_by_location(findings: list[dict]) -> list[dict]:
    """Keep one finding per (file, line); merge text from duplicate LLM/SAST rows."""
    buckets: dict[tuple[str, int], list[dict]] = {}
    for f in findings:
        fp = f.get("file", "unknown") or "unknown"
        try:
            ln = int(f.get("line", 0) or 0)
        except (TypeError, ValueError):
            ln = 0
        buckets.setdefault((fp, ln), []).append(f)

    merged: list[dict] = []
    for _key, group in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        if len(group) == 1:
            merged.append(group[0])
            continue
        acc = group[0]
        for g in group[1:]:
            acc = _merge_two_findings(acc, g)
        merged.append(acc)
    return merged


def _merge_two_findings(a: dict, b: dict) -> dict:
    ra = _SEVERITY_RANK.get(str(a.get("severity", "")).lower(), 0)
    rb = _SEVERITY_RANK.get(str(b.get("severity", "")).lower(), 0)
    primary, secondary = (a, b) if ra >= rb else (b, a)

    ta = str(primary.get("type") or "Other")
    tb = str(secondary.get("type") or "Other")
    typ = ta if ta != "Other" else tb

    da = (primary.get("description") or "").strip()
    db = (secondary.get("description") or "").strip()
    if db and db.lower() not in da.lower():
        desc = f"{da} Also: {db}" if da else db
    else:
        desc = da or db

    ea = (primary.get("exploitability") or "").strip()
    eb = (secondary.get("exploitability") or "").strip()
    if eb and eb.lower() not in ea.lower():
        exploitability = f"{ea} {eb}".strip() if ea else eb
    else:
        exploitability = ea or eb

    sev = primary.get("severity") if ra >= rb else secondary.get("severity")

    return {
        "type": typ,
        "file": primary.get("file"),
        "line": primary.get("line"),
        "severity": sev,
        "description": desc,
        "exploitability": exploitability,
    }


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


def _resolve_tool(name: str) -> str | None:
    """Resolve semgrep/bandit: PATH first, then the venv bin next to ``sys.executable``."""
    p = shutil.which(name)
    if p:
        return p
    # Do not resolve() sys.executable — on macOS venv it points into Homebrew and loses .venv/bin.
    sibling = Path(sys.executable).parent / name
    if sibling.is_file():
        return str(sibling)
    return None


def _run_semgrep(target_path: str) -> str:
    """Run semgrep and return raw JSON output string, or empty string on failure."""
    semgrep = _resolve_tool("semgrep")
    if not semgrep:
        ui.print_info("Semgrep not found — skipping. Install: pip install semgrep")
        return ""
    try:
        cmd = [
            semgrep, "--config", "auto", target_path, "--json",
            "--no-rewrite-rule-ids", "--quiet",
        ]
        for d in _EXCLUDE_DIRS:
            cmd.extend(["--exclude", d])
        ui.print_info("Running Semgrep...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.stdout or ""
    except FileNotFoundError:
        ui.print_info("Semgrep binary missing — skipping. Install: pip install semgrep")
        return ""
    except subprocess.TimeoutExpired:
        ui.print_info("Semgrep timed out after 120s — partial results may be missing.")
        return ""
    except Exception as e:
        ui.print_info(f"Semgrep error: {e}")
        return ""


def _run_bandit(target_path: str) -> str:
    """Run bandit and return raw JSON output string, or empty string on failure."""
    bandit = _resolve_tool("bandit")
    if not bandit:
        ui.print_info("Bandit not found — skipping. Install: pip install bandit")
        return ""
    try:
        exclude = ",".join(
            os.path.join(target_path, d) for d in _EXCLUDE_DIRS
        )
        ui.print_info("Running Bandit...")
        result = subprocess.run(
            [bandit, "-r", target_path, "-f", "json", "-q", "--exclude", exclude],
            capture_output=True, text=True, timeout=60
        )
        # Bandit exits non-zero when it finds issues — that's normal
        return result.stdout or ""
    except FileNotFoundError:
        ui.print_info("Bandit binary missing — skipping. Install: pip install bandit")
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
