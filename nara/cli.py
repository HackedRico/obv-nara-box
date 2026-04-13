"""
NARA CLI — interactive REPL entry point.

Invoked via: nara  (after pip install -e .)
"""

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style

from nara.utils import terminal_ui as ui
from nara.utils import config as cfg
from nara import orchestrator

_PROMPT_STYLE = Style.from_dict({
    "prompt": "bold ansired",
})

_SESSION_TEMPLATE: dict = {
    "findings": [],
    "kill_chain": [],
    "container_running": False,
    "app_provisioned": False,
    "exploited": False,
    "history": [],
    "shell_history": [],
}


def main():
    # Validate config before doing anything
    try:
        cfg.validate()
    except ValueError as e:
        ui.print_error(str(e))
        raise SystemExit(1)

    ui.print_banner()
    ui.print_info(f"Backend: [bold]{cfg.LLM_BACKEND.upper()}[/bold]")
    ui.print_info("Type [bold]help[/bold] to see available commands. Type [bold]exit[/bold] to quit.")
    ui.console.print()

    session = dict(_SESSION_TEMPLATE)
    # Reset mutable defaults properly
    session["findings"] = []
    session["kill_chain"] = []
    session["history"] = []

    prompt_session = PromptSession(
        history=InMemoryHistory(),
        style=_PROMPT_STYLE,
    )

    while True:
        try:
            user_input = prompt_session.prompt("nara > ")
        except KeyboardInterrupt:
            ui.console.print()
            ui.print_info("Use [bold]exit[/bold] to quit cleanly.")
            continue
        except EOFError:
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        try:
            response = orchestrator.route(user_input, session)
        except Exception as e:
            ui.print_error(f"Unexpected error: {e}")
            continue

        if response == "__EXIT__":
            break

        if response:
            ui.console.print(f"\n[bright_white]{response}[/bright_white]\n")

    ui.print_info("Session ended. Stay safe out there.")


if __name__ == "__main__":
    main()
