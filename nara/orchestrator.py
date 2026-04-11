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

  [bright_cyan]scan[/bright_cyan] [dim]<path>[/dim]      Scan a codebase for vulnerabilities
  [bright_yellow]plan[/bright_yellow]             Design a kill chain from scan findings
  [bright_red]exploit[/bright_red]          Execute the kill chain against the container
  [white]init[/white]             Provision the Docker container
  [white]reset[/white]            Tear down and restart the container (clean slate)
  [white]status[/white]           Show current session findings and state
  [white]help[/white]             Show this message
  [white]exit[/white] / [white]quit[/white]    End the session

Or just talk naturally — NARA understands plain English.
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
    """Keyword-based intent classification. Returns intent label."""
    t = text.lower().strip()

    if any(k in t for k in ["scan", "analyze", "analyse", "find vuln", "check for vuln", "audit"]):
        return "scan"
    if any(k in t for k in ["plan", "kill chain", "attack chain", "design attack", "what's the plan"]):
        return "plan"
    if any(k in t for k in ["exploit", "attack", "run the chain", "go for it", "execute", "fire"]):
        return "exploit"
    if any(k in t for k in ["init", "start container", "provision", "set up env", "setup env"]):
        return "init"
    if any(k in t for k in ["reset", "restart", "fresh", "clean slate", "tear down"]):
        return "reset"
    if any(k in t for k in ["status", "what did you find", "show findings", "what have you found", "findings"]):
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

    if intent == "status":
        return _build_status(session)

    # Fallback: conversational LLM response
    return _chat_response(user_input, session)


# ------------------------------------------------------------------ #
# Private helpers                                                      #
# ------------------------------------------------------------------ #

def _clone_repo(url: str) -> str | None:
    """Clone a git repo URL into nara_targets/ and return the local path."""
    # Derive repo name from URL (strip trailing .git and slashes)
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
        session["findings"] = []
        session["kill_chain"] = []
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


def _chat_response(user_input: str, session: dict) -> str:
    """Pass unrecognized input to the LLM for a conversational response."""
    llm = _get_llm()

    # Build context summary for the LLM
    context = f"[Session context] Findings: {len(session['findings'])}, Kill chain steps: {len(session['kill_chain'])}, Container running: {session['container_running']}"

    session["history"].append({"role": "user", "content": user_input})

    # Keep last 20 turns to avoid context overflow
    messages = session["history"][-20:]

    try:
        with ui.spinner("Thinking..."):
            response = llm.chat(messages, system=_SYSTEM_PROMPT + "\n" + context)
    except RuntimeError as e:
        return f"LLM error: {e}"

    session["history"].append({"role": "assistant", "content": response})
    return response
