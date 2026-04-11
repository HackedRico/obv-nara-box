import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama").lower()
# Default matches a typical `ollama pull` name; must equal a tag from `ollama list`.
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
FEATHERLESS_API_KEY: str = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_MODEL: str = os.getenv("FEATHERLESS_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

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
            "LLM_BACKEND=featherless requires FEATHERLESS_API_KEY to be set in .env"
        )
