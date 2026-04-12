"""
TerpAI client — wraps the NebulaOne-based TerpAI API at terpai.umd.edu.

Authentication: TerpAI uses UMD Entra ID (Azure AD) SSO and issues short-lived
JWTs (30 min TTL) via NebulaOne. This module handles token acquisition via
Playwright browser automation and token caching.

Usage:
    # First time (or when token expired): run auth flow in browser
    client = TerpAIClient()
    client.authenticate()           # opens browser, user logs in via UMD SSO

    # Chat
    reply = client.chat("scan this Flask app for vulnerabilities")
    print(reply)
"""

import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://terpai.umd.edu"
_TOKEN_CACHE = Path.home() / ".nara" / "terpai_token.json"


# --------------------------------------------------------------------------- #
# Token management                                                             #
# --------------------------------------------------------------------------- #

def _save_token(token: str, expires_at: float) -> None:
    _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_CACHE.write_text(json.dumps({"token": token, "expires_at": expires_at}))


def _load_token() -> tuple[str, float] | None:
    """Return (token, expires_at) if a cached token exists, else None."""
    if not _TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(_TOKEN_CACHE.read_text())
        return data["token"], data["expires_at"]
    except Exception:
        return None


def _token_is_valid(expires_at: float, margin_secs: int = 120) -> bool:
    """True if the token won't expire within `margin_secs` seconds."""
    return time.time() < (expires_at - margin_secs)


def _decode_jwt_expiry(token: str) -> float:
    """Extract the `exp` claim from a JWT without verifying the signature."""
    import base64
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Not a valid JWT")
    # Pad base64 if needed
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    return float(payload["exp"])


# --------------------------------------------------------------------------- #
# Browser-based auth (Playwright)                                              #
# --------------------------------------------------------------------------- #

def authenticate_via_browser() -> str:
    """
    Open a Playwright browser window pointing at TerpAI. The user logs in
    through UMD SSO (Duo MFA etc). We intercept the first API request that
    contains a Bearer token, save it, and close the browser.

    Returns the captured Bearer token string.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "Playwright is required for TerpAI auth.\n"
            "Run: pip install playwright && playwright install chromium"
        )

    captured: dict = {}

    def _intercept(request):
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer ") and "terpai.umd.edu" in request.url:
            captured["token"] = auth[len("Bearer "):]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.on("request", _intercept)

        print("\n[TerpAI] Opening browser — log in with your UMD credentials.")
        print("[TerpAI] Complete Duo MFA if prompted. The window will close automatically.\n")

        page.goto(f"{_BASE_URL}/")

        # Poll until we capture a token (up to 3 minutes)
        deadline = time.time() + 180
        while not captured and time.time() < deadline:
            time.sleep(0.5)
            # Keep page alive / trigger a small navigation if needed
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass

        browser.close()

    if not captured:
        raise TimeoutError("TerpAI auth timed out — no Bearer token captured in 3 minutes.")

    token = captured["token"]
    expires_at = _decode_jwt_expiry(token)
    _save_token(token, expires_at)
    print(f"[TerpAI] Token captured and cached. Valid until {time.strftime('%H:%M:%S', time.localtime(expires_at))}.\n")
    return token


# --------------------------------------------------------------------------- #
# TerpAI API client                                                            #
# --------------------------------------------------------------------------- #

class TerpAIClient:
    """
    Thin wrapper around the NebulaOne/TerpAI internal REST API.

    One client = one conversation. Call .authenticate() if you don't have a
    cached token yet. Then call .chat(message) to get a response string.
    """

    def __init__(self, token: str | None = None):
        self._token: str | None = token
        self._conversation_id: str | None = None
        self._session = requests.Session()

        # If no token passed in, try the cache or env var
        if not self._token:
            env_token = os.getenv("TERPAI_TOKEN", "")
            if env_token:
                self._token = env_token
            else:
                cached = _load_token()
                if cached:
                    tok, exp = cached
                    if _token_is_valid(exp):
                        self._token = tok
                    else:
                        logger.info("Cached TerpAI token expired — re-auth needed.")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def authenticate(self) -> None:
        """Acquire a fresh token via browser if not already valid."""
        if self._token and self._is_token_valid():
            return
        self._token = authenticate_via_browser()

    def chat(self, message: str, system: str = "") -> str:
        """
        Send a message to TerpAI and return the full response text.
        Creates a new conversation if one doesn't exist yet.
        """
        self._ensure_token()
        if not self._conversation_id:
            self._conversation_id = self._create_conversation()

        return self._send_segment(message, system)

    def reset_conversation(self) -> None:
        """Start a fresh conversation on the next .chat() call."""
        self._conversation_id = None

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _ensure_token(self) -> None:
        if not self._token or not self._is_token_valid():
            self.authenticate()

    def _is_token_valid(self) -> bool:
        if not self._token:
            return False
        try:
            exp = _decode_jwt_expiry(self._token)
            return _token_is_valid(exp)
        except Exception:
            return False

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    def _create_conversation(self) -> str:
        """POST to create a new conversation, return its ID."""
        url = f"{_BASE_URL}/api/internal/userConversations"
        body = {"title": "NARA Session"}
        resp = self._session.post(url, json=body, headers=self._headers(), timeout=30)
        if resp.status_code == 401:
            # Token rejected — re-auth and retry once
            self.authenticate()
            resp = self._session.post(url, json=body, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Response likely has an "id" or "conversationId" field
        conv_id = data.get("id") or data.get("conversationId") or data.get("data", {}).get("id")
        if not conv_id:
            raise RuntimeError(f"TerpAI: could not find conversation ID in response: {data}")
        logger.debug("TerpAI conversation created: %s", conv_id)
        return conv_id

    def _send_segment(self, message: str, system: str = "") -> str:
        """
        POST a message segment and collect the SSE stream into a full string.
        """
        url = f"{_BASE_URL}/api/internal/userConversations/{self._conversation_id}/segments"

        # Build request body — NebulaOne segment format
        body: dict = {"content": message, "role": "user"}
        if system:
            body["systemPrompt"] = system

        resp = self._session.post(
            url,
            json=body,
            headers={**self._headers(), "Accept": "text/event-stream"},
            stream=True,
            timeout=120,
        )

        if resp.status_code == 401:
            self.authenticate()
            resp = self._session.post(
                url,
                json=body,
                headers={**self._headers(), "Accept": "text/event-stream"},
                stream=True,
                timeout=120,
            )

        resp.raise_for_status()
        return self._parse_sse(resp)

    @staticmethod
    def _parse_sse(response) -> str:
        """
        Consume a Server-Sent Events stream and return the concatenated text content.

        SSE lines look like:
            data: {"content": "chunk"}
            data: [DONE]
        """
        chunks: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if raw_line.startswith("data:"):
                payload = raw_line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                    # Try common field names used by NebulaOne / OpenAI-compatible APIs
                    text = (
                        obj.get("content")
                        or obj.get("text")
                        or obj.get("delta", {}).get("content")
                        or obj.get("choices", [{}])[0].get("delta", {}).get("content")
                        or ""
                    )
                    if text:
                        chunks.append(text)
                except json.JSONDecodeError:
                    # Non-JSON SSE line — skip
                    pass
            elif raw_line.startswith("event:") or raw_line.startswith(":"):
                # SSE comments / event type lines — ignore
                pass

        return "".join(chunks)
