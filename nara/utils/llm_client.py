"""
LLM abstraction layer — unified interface for Featherless (default), Ollama, and Claude.

All agents call LLMClient().chat(...). The backend is controlled by LLM_BACKEND
and model IDs in .env (see nara.utils.config FEATHERLESS_MODELS / FEATHERLESS_MODEL).

Interface (contractual — do not change signatures):
    llm = LLMClient()
    response: str = llm.chat(messages, system)
"""

import logging
from nara.utils import config as cfg

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        cfg.validate()
        self.backend = cfg.LLM_BACKEND
        self._client = self._build_client()

    # ------------------------------------------------------------------ #
    # Public interface — all agents use this and only this                 #
    # ------------------------------------------------------------------ #

    def chat(self, messages: list[dict], system: str = "", *, ollama_json: bool = False) -> str:
        """
        Send a conversation to the configured LLM and return the response text.

        Args:
            messages: List of {"role": "user"|"assistant", "content": str}
            system:   Optional system prompt string.
            ollama_json: If True and backend is Ollama, request JSON-valued output (format=json).

        Returns:
            The model's response as a plain string.

        Raises:
            RuntimeError: On API error, with a descriptive message.
        """
        try:
            if self.backend == "ollama":
                return self._chat_ollama(messages, system, json_mode=ollama_json)
            elif self.backend == "claude":
                return self._chat_claude(messages, system)
            elif self.backend == "featherless":
                return self._chat_featherless(messages, system)
        except Exception as exc:
            msg = f"[LLMClient/{self.backend}] API call failed: {exc}"
            logger.error(msg)
            raise RuntimeError(msg) from exc

    # ------------------------------------------------------------------ #
    # Backend implementations                                              #
    # ------------------------------------------------------------------ #

    def _build_client(self):
        if self.backend == "ollama":
            import ollama  # noqa: F401 — just validate import
            return None  # ollama module is used directly
        elif self.backend == "claude":
            import anthropic
            return anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        elif self.backend == "featherless":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "Featherless backend requires the 'openai' package.\n"
                    "Run: pip install openai"
                )
            return OpenAI(
                base_url="https://api.featherless.ai/v1",
                api_key=cfg.FEATHERLESS_API_KEY,
            )

    def _chat_ollama(self, messages: list[dict], system: str, *, json_mode: bool = False) -> str:
        import ollama

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict = {
            "model": cfg.OLLAMA_MODEL,
            "messages": full_messages,
        }
        if json_mode:
            kwargs["format"] = "json"

        response = ollama.chat(**kwargs)
        content = response["message"]["content"]
        return content if isinstance(content, str) else ""

    def _chat_claude(self, messages: list[dict], system: str) -> str:
        kwargs = {
            "model": "claude-opus-4-5",
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def _chat_featherless(self, messages: list[dict], system: str) -> str:
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = self._client.chat.completions.create(
            model=cfg.FEATHERLESS_MODEL,
            messages=full_messages,
            max_tokens=4096,
        )
        return response.choices[0].message.content
