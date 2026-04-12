import os
from pathlib import Path
from dotenv import load_dotenv

def _load_dotenv_file() -> None:
    """
    Find .env reliably:
    - Walk upward from this file (works for editable installs).
    - Else walk upward from cwd (works when the package lives in site-packages).
    override=True so values in .env win over empty shell exports.
    """
    here = Path(__file__).resolve()

    def walk(anchor: Path) -> Path | None:
        start = anchor if anchor.is_dir() else anchor.parent
        for ancestor in [start, *start.parents]:
            candidate = ancestor / ".env"
            if candidate.is_file():
                return candidate
        return None

    env_path = walk(here) or walk(Path.cwd())
    if env_path is not None:
        load_dotenv(dotenv_path=env_path, override=True)


_load_dotenv_file()


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default


# Default backend: Featherless (OpenAI-compatible API at api.featherless.ai/v1).
# Set LLM_BACKEND=ollama or claude in .env to use other providers.
LLM_BACKEND: str = _env("LLM_BACKEND", "featherless").lower()
# Default matches a typical `ollama pull` name; must equal a tag from `ollama list`.
OLLAMA_MODEL: str = _env("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")
ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY")
FEATHERLESS_API_KEY: str = _env("FEATHERLESS_API_KEY")
# Catalog: https://featherless.ai/models (e.g. safety-research / cybersecurity)
FEATHERLESS_MODELS: tuple[str, ...] = (
    "microsoft/Phi-4-mini-instruct",
)
FEATHERLESS_MODEL: str = _env("FEATHERLESS_MODEL") or FEATHERLESS_MODELS[0]

_VALID_BACKENDS = {"ollama", "claude", "featherless"}


def validate():
    """Fail loudly if required config is missing. Call once at startup."""
    if LLM_BACKEND not in _VALID_BACKENDS:
        raise ValueError(
            f"LLM_BACKEND='{LLM_BACKEND}' is not valid. "
            f"Choose one of: {', '.join(_VALID_BACKENDS)}"
        )

    if LLM_BACKEND == "claude" and not ANTHROPIC_API_KEY:
        raise ValueError(
            "LLM_BACKEND=claude requires ANTHROPIC_API_KEY to be set in .env\n"
            "Get your key at: https://console.anthropic.com"
        )

    if LLM_BACKEND == "featherless" and not FEATHERLESS_API_KEY:
        raise ValueError(
            "LLM_BACKEND=featherless requires FEATHERLESS_API_KEY. "
            "Add it to a .env file in this repo (or any parent of your cwd), then run: "
            "pip install -e . && unset FEATHERLESS_API_KEY"
        )
