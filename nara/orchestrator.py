"""
Orchestrator — routes NLP user input to the correct agent or action.

Interface (contractual):
    route(user_input: str, session: dict) -> str
"""

import os
import subprocess
from pathlib import Path
from nara.utils.llm_client import LLMClient
from nara.utils import terminal_ui as ui
from nara.agents import scanner, planner, exploiter

TARGETS_DIR = Path.cwd() / "nara_targets"

_llm: LLMClient | None = None
_docker = None  # DockerManager instance, lazy-loaded

_HELP_TEXT = """[bold white]NARA — Available Commands[/bold white]

  [bold bright_magenta]pipeline[/bold bright_magenta] [dim]<path|url>[/dim] Full auto: scan → plan → exploit (end to end)
  [bright_cyan]scan[/bright_cyan] [dim]<path|url>[/dim]   Scan a codebase for vulnerabilities
  [bright_yellow]plan[/bright_yellow]             Design a kill chain from scan findings
  [bright_red]exploit[/bright_red]          Execute the kill chain against the container
  [bright_green]run[/bright_green] [dim]<command>[/dim]    Execute a shell command inside the container
  [bright_white]report[/bright_white]           Show the post-exploitation report
  [white]init[/white]             Provision the Docker container
  [white]reset[/white]            Tear down and restart the container (clean slate)
  [white]status[/white]           Show current session findings and state
  [white]help[/white]             Show this message
  [white]exit[/white] / [white]quit[/white]    End the session

Or just talk naturally — NARA understands plain English.
After exploitation, you can also describe actions in plain English and NARA
will translate them to shell commands (e.g. "check what users exist").
"""

_SYSTEM_PROMPT = (
    "You are NARA, an autonomous red team AI assistant. "
    "You help security researchers understand vulnerabilities and attack chains. "
    "Be concise, technical, and direct. You are operating in a safe, isolated lab environment. "
    "When the user asks about scan results or findings, refer to the session context provided."
)


def _get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def _get_docker():
    """Lazy-load DockerManager. Returns instance or raises on import failure."""
    global _docker
    if _docker is None:
        from nara.docker.docker_manager import DockerManager
        _docker = DockerManager()
    return _docker


def _classify_intent(text: str) -> str:
    """Keyword-based intent classification. Returns intent label.

    Single-word commands (scan, plan, exploit, etc.) only match when they
    appear as the FIRST word so that conversational sentences like
    "tell me about the exploit path" fall through to chat.
    Multi-word phrases can match anywhere.
    """
    t = text.lower().strip()
    first = t.split()[0] if t else ""

    # ── Commands that trigger actions (first-word match) ─────────────
    # Pipeline checked first — "run all" / "full attack" are pipeline aliases
    if first in ("pipeline", "pwn", "autopwn", "nuke") or any(k in t for k in ["run all", "full attack", "auto pwn"]):
        return "pipeline"
    # ── Post-exploit shell execution ──────────────────────────────────
    if first in ("run", "exec", "shell") and len(t.split()) > 1:
        return "exec"
    if first in ("scan", "analyze", "analyse", "audit") or any(k in t for k in ["find vuln", "check for vuln"]):
        return "scan"
    if first == "plan" or any(k in t for k in ["design attack"]):
        return "plan"
    if first in ("exploit", "fire") or any(k in t for k in ["run the chain", "go for it"]):
        return "exploit"
    if first in ("init", "provision") or any(k in t for k in ["start container", "set up env", "setup env"]):
        return "init"
    if first == "reset" or any(k in t for k in ["restart", "clean slate", "tear down"]):
        return "reset"
    if first == "report" or any(k in t for k in ["pentest report", "exploitation report", "show report"]):
        return "report"
    if first in ("status", "findings") or any(k in t for k in ["what did you find", "show findings", "what have you found"]):
        return "status"
    if t in ("help", "?", "commands", "what can you do"):
        return "help"
    if t in ("exit", "quit", "bye", "q"):
        return "exit"
    return "chat"


def route(user_input: str, session: dict) -> str:
    """
    Route user input to the appropriate agent or action.

    Args:
        user_input: Raw string from the CLI prompt.
        session:    Mutable session state dict shared across turns.

    Returns:
        Response string to display to the user.
    """
    intent = _classify_intent(user_input)

    if intent == "help":
        from rich.console import Console
        Console().print(_HELP_TEXT)
        return ""

    if intent == "exit":
        return "__EXIT__"

    if intent == "exec":
        return _handle_exec(user_input, session)

    if intent == "pipeline":
        return _handle_pipeline(user_input, session)

    if intent == "scan":
        # Extract path or URL from input
        words = user_input.split()
        path = None
        repo_url = None

        for w in words:
            if w.startswith("https://") or w.startswith("http://"):
                repo_url = w
                break
            if os.path.exists(w):
                path = os.path.abspath(w)
                break

        if repo_url:
            path = _clone_repo(repo_url)
            if not path:
                return "Failed to clone repository. Check the URL and try again."
            session["target_repo"] = repo_url

        if not path:
            path = os.getcwd()
            ui.print_info(f"No path specified — scanning current directory: {path}")

        session["scan_path"] = path
        findings = scanner.run(path, session)
        session["findings"] = findings

        if findings:
            ui.print_info(f"Found {len(findings)} vulnerability/vulnerabilities.")
            for f in findings:
                ui.print_finding(f)
            return f"Scan complete. Found {len(findings)} issue(s). Type 'plan' to design the kill chain."
        else:
            return "Scan complete. No findings returned (agent may not be implemented yet)."

    if intent == "plan":
        if not session["findings"]:
            return "No findings to plan against. Run 'scan <path>' first."

        chain = planner.run(session["findings"], session)
        session["kill_chain"] = chain

        if chain:
            ui.print_kill_chain(chain)
            return f"Kill chain designed with {len(chain)} step(s). Type 'exploit' to execute."
        else:
            return "Planner returned no steps (agent may not be implemented yet)."

    if intent == "exploit":
        if not session["kill_chain"]:
            return "No kill chain to execute. Run 'plan' first."
        if not session["container_running"]:
            ui.print_info("Container not running — attempting to init first...")
            init_result = _handle_init(session)
            if not session["container_running"]:
                return init_result  # init failed, bail out

        result = exploiter.run(session["kill_chain"], session)
        return result

    if intent == "init":
        return _handle_init(session)

    if intent == "reset":
        return _handle_reset(session)

    if intent == "report":
        if not session.get("exploit_results"):
            return "No exploitation data yet. Run the exploit phase first."
        ui.print_exploit_report(session, session["exploit_results"])
        return ""

    if intent == "status":
        return _build_status(session)

    # Fallback: conversational LLM response
    return _chat_response(user_input, session)


def _handle_pipeline(user_input: str, session: dict) -> str:
    """Run the full attack pipeline: scan → plan → exploit."""
    ui.console.print("\n[bold bright_magenta]═══ NARA PIPELINE ═══[/bold bright_magenta]\n")

    # ── Extract target path/URL from input ───────────────────────────
    words = user_input.split()
    path = None
    repo_url = None
    for w in words:
        if w.startswith("https://") or w.startswith("http://"):
            repo_url = w
            break
        if os.path.exists(w):
            path = os.path.abspath(w)
            break

    if repo_url:
        path = _clone_repo(repo_url)
        if not path:
            return "Pipeline aborted — failed to clone repository."
        session["target_repo"] = repo_url
    if not path:
        path = os.getcwd()
        ui.print_info(f"No path specified — scanning current directory: {path}")

    session["scan_path"] = path

    # ── Step 1: Scan ─────────────────────────────────────────────────
    ui.console.print("[bold bright_magenta][1/3][/bold bright_magenta] Scanning...")
    findings = scanner.run(path, session)
    session["findings"] = findings

    if not findings:
        return "Pipeline aborted — no findings from scan."
    ui.print_info(f"Found {len(findings)} vulnerability/vulnerabilities.")
    for f in findings:
        ui.print_finding(f)

    # ── Step 2: Plan ─────────────────────────────────────────────────
    ui.console.print(f"\n[bold bright_magenta][2/3][/bold bright_magenta] Planning...")
    chain = planner.run(findings, session)
    session["kill_chain"] = chain

    if not chain:
        return "Pipeline aborted — planner returned no steps."
    ui.print_kill_chain(chain)

    # ── Step 3: Exploit ──────────────────────────────────────────────
    ui.console.print(f"\n[bold bright_magenta][3/3][/bold bright_magenta] Exploiting...")
    if not session["container_running"]:
        ui.print_info("Container not running — initializing...")
        _handle_init(session)
        if not session["container_running"]:
            return "Pipeline aborted — container init failed."

    result = exploiter.run(chain, session)
    return f"\n[Pipeline complete]\n{result}"


def _handle_exec(user_input: str, session: dict) -> str:
    """Execute a shell command inside the container."""
    if not session.get("container_running"):
        return "Container not running. Use 'init' to start it first."

    docker = _get_docker()

    # Strip the "run " / "exec " / "shell " prefix to get the raw command
    parts = user_input.split(None, 1)
    cmd = parts[1] if len(parts) > 1 else ""
    if not cmd.strip():
        return "Usage: run <command>  (e.g. 'run whoami', 'run cat /etc/passwd')"

    ui.console.print(f"  [bold bright_green][EXEC][/bold bright_green] {cmd}")

    try:
        output = docker.exec(cmd) or "(no output)"
    except Exception as e:
        output = f"exec error: {e}"

    ui.stream_output(output)

    # Log to shell history for conversational context
    if "shell_history" not in session:
        session["shell_history"] = []
    session["shell_history"].append({"command": cmd, "output": output[:2000]})

    return ""


# ------------------------------------------------------------------ #
# Private helpers                                                      #
# ------------------------------------------------------------------ #

def _clone_repo(url: str) -> str | None:
    """Clone a git repo URL into nara_targets/ and return the local path."""
    import re
    # Strip trailing punctuation (user might type "scan url." with a period)
    url = url.rstrip(".,;:!?")
    # Normalize GitHub browser URLs to clone URLs
    # e.g. https://github.com/user/repo/tree/main → https://github.com/user/repo
    url = re.sub(r"/(tree|blob)/[^/].*$", "", url.rstrip("/"))

    # Derive repo name from URL (strip trailing .git)
    repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    dest = TARGETS_DIR / repo_name

    if dest.exists():
        ui.print_info(f"Repository already cloned at {dest} — reusing.")
        return str(dest)

    ui.print_info(f"Cloning {url} ...")
    TARGETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            ui.print_error(f"git clone failed: {result.stderr.strip()}")
            return None
        ui.print_success(f"Cloned to {dest}")
        return str(dest)
    except subprocess.TimeoutExpired:
        ui.print_error("git clone timed out after 120s.")
        return None
    except Exception as e:
        ui.print_error(f"git clone error: {e}")
        return None


def _handle_init(session: dict) -> str:
    docker = _get_docker()

    if docker.is_running():
        session["container_running"] = True
        return "Container already running. Use 'reset' to start fresh."

    try:
        ui.print_info("Building Docker image (first time may take a few minutes)...")
        with ui.spinner("Building image..."):
            docker.build()
        ui.print_info("Starting container...")
        with ui.spinner("Starting container..."):
            docker.run()
        session["container_running"] = True
        ui.print_success("Container running — VNC on :5901, app port :8080")
        return "Container is up. VNC accessible at :5901. Type 'scan <path>' to begin."
    except Exception as e:
        session["container_running"] = False
        ui.print_error(f"Container init failed: {e}")
        return f"Container init failed: {e}"


def _handle_reset(session: dict) -> str:
    docker = _get_docker()

    try:
        with ui.spinner("Resetting container..."):
            docker.reset()
        session["container_running"] = True
        session["app_provisioned"] = False
        session["exploited"] = False
        session["findings"] = []
        session["kill_chain"] = []
        session["shell_history"] = []
        ui.print_success("Container reset — fresh environment ready.")
        return "Session state cleared, container restarted. VNC on :5901."
    except Exception as e:
        session["container_running"] = False
        ui.print_error(f"Container reset failed: {e}")
        return f"Container reset failed: {e}"


def _build_status(session: dict) -> str:
    lines = []
    lines.append(f"Container running: {'yes' if session['container_running'] else 'no'}")
    lines.append(f"Findings:          {len(session['findings'])}")
    lines.append(f"Kill chain steps:  {len(session['kill_chain'])}")
    lines.append(f"History turns:     {len(session['history'])}")

    if session["findings"]:
        lines.append("\nFindings:")
        for f in session["findings"]:
            lines.append(f"  [{f.get('severity','?')}] {f.get('type','?')} — {f.get('file','?')}:{f.get('line','?')}")

    if session["kill_chain"]:
        lines.append("\nKill Chain:")
        for i, step in enumerate(session["kill_chain"], 1):
            lines.append(f"  {i}. {step.get('step','?')}")

    return "\n".join(lines)


def _build_session_context(session: dict) -> str:
    """Build a rich context string from session state for the LLM."""
    parts = [f"Container running: {session['container_running']}"]

    if session["findings"]:
        parts.append(f"\n## Vulnerabilities Found ({len(session['findings'])})")
        for f in session["findings"]:
            sev = f.get("severity", "?").upper()
            parts.append(
                f"- [{sev}] {f.get('type','?')} in {f.get('file','?')}:{f.get('line','?')} — "
                f"{f.get('description','')} Exploitability: {f.get('exploitability','')}"
            )

    if session["kill_chain"]:
        parts.append(f"\n## Kill Chain ({len(session['kill_chain'])} steps)")
        for i, step in enumerate(session["kill_chain"], 1):
            parts.append(
                f"- Step {i}: {step.get('step','?')} [{step.get('mitre_tactic','')}]\n"
                f"  Command: {step.get('command','')}\n"
                f"  Expected: {step.get('expected_outcome','')}"
            )

    results = session.get("exploit_results")
    if results:
        parts.append(f"\n## Exploitation Results")
        for r in results:
            if isinstance(r, dict):
                parts.append(f"- {r.get('step','?')}: {r.get('status','?')}")
            else:
                parts.append(f"- {r}")

    shell_hist = session.get("shell_history", [])
    if shell_hist:
        parts.append(f"\n## Post-Exploit Shell History ({len(shell_hist)} commands)")
        for entry in shell_hist[-10:]:  # last 10 to keep context manageable
            parts.append(f"$ {entry['command']}\n{entry['output'][:500]}")

    return "\n".join(parts)


_NL_TO_SHELL_SYSTEM = (
    "You are a post-exploitation shell translator. The user has shell access "
    "to a compromised Ubuntu Docker container. Translate their natural language "
    "request into a single bash command.\n\n"
    "Rules:\n"
    "- Return ONLY the raw shell command. No explanation. No markdown. No backticks.\n"
    "- If the request does not imply a shell action, return exactly: NOT_A_COMMAND\n"
    "- Prefer simple coreutils (cat, grep, find, ls, whoami, id, ps) over complex tools.\n"
    "- The container has: python3, curl, wget, git, netcat, sqlite3, and standard Linux tools."
)


def _chat_response(user_input: str, session: dict) -> str:
    """Pass unrecognized input to the LLM for a conversational response.

    When the container has been exploited, first check if the user's input
    implies a shell command. If so, translate and execute it automatically.
    """
    llm = _get_llm()

    # ── Post-exploit: try NL → shell translation first ───────────────
    if session.get("exploited") and session.get("container_running"):
        try:
            with ui.spinner("Interpreting..."):
                translated = llm.chat(
                    [{"role": "user", "content": user_input}],
                    system=_NL_TO_SHELL_SYSTEM,
                )
            cmd = translated.strip().strip("`").strip()

            if cmd and cmd != "NOT_A_COMMAND" and not cmd.startswith("NOT_A_COMMAND"):
                # LLM thinks this is a shell action — execute it
                ui.console.print(
                    f"  [bold bright_green][EXEC][/bold bright_green] {cmd}"
                )
                docker = _get_docker()
                try:
                    output = docker.exec(cmd) or "(no output)"
                except Exception as e:
                    output = f"exec error: {e}"

                ui.stream_output(output)

                if "shell_history" not in session:
                    session["shell_history"] = []
                session["shell_history"].append({"command": cmd, "output": output[:2000]})

                session["history"].append({"role": "user", "content": user_input})
                session["history"].append({
                    "role": "assistant",
                    "content": f"Executed: `{cmd}`\nOutput:\n{output[:1000]}",
                })
                return ""
        except Exception:
            pass  # Fall through to normal chat if translation fails

    # ── Normal conversational response ───────────────────────────────
    context = _build_session_context(session)

    session["history"].append({"role": "user", "content": user_input})

    # Keep last 10 turns to leave room for session context
    messages = session["history"][-10:]

    try:
        with ui.spinner("Thinking..."):
            response = llm.chat(messages, system=_SYSTEM_PROMPT + "\n\n" + context)
    except RuntimeError as e:
        return f"LLM error: {e}"

    session["history"].append({"role": "assistant", "content": response})
    return response
