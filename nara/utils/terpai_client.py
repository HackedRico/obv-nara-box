"""
Agent — Blue Team Advisor (TerpAI)

Takes red team findings and kill chain from the session and queries TerpAI
for blue team remediation advice on each vulnerability.

Fits into the existing NARA multi-agent pipeline:
    session["findings"]   → read (from Scanner)
    session["kill_chain"] → read (from Planner)
    session["blue_team"]  → written back here

Usage:
    from nara.agents import blue_team
    report = blue_team.run(session)

Authentication:
    Set TERPAI_BEARER_TOKEN in your .env file.
    Tokens expire every ~30 minutes — re-login to TerpAI and copy a fresh
    Bearer token from DevTools → Network → any request → Authorization header.

TerpAI transport:
    The API responds with Server-Sent Events (SSE), not JSON.
    Each SSE event has a named type and a base64-encoded data payload.

    SSE event types observed:
        conversation-and-segment-id  — base64 JSON with ConversationId
        step-update                  — base64 string e.g. "Thinking"
        response-updated             — base64 token chunk (streamed word by word)
        cosmos-db-session-tokens     — base64 JSON array of Cosmos session tokens
        response-model               — base64 JSON with final metadata + title
        no-more-data                 — empty, signals stream end
"""

import base64
import json
import uuid
import logging
import requests

from nara.utils import config as cfg
from nara.utils import terminal_ui as ui

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# TerpAI configuration                                                 #
# ------------------------------------------------------------------ #

TERPAI_BASE_URL   = "https://terpai.umd.edu"
TERPAI_GPT_SYSTEM = "056a216a-c338-4e02-b753-83abb5a2f37d"

# SSE stream timeout — TerpAI responses can be long for detailed advice
_STREAM_TIMEOUT_S = 120

# ------------------------------------------------------------------ #
# Blue team framing prepended to every query                           #
# ------------------------------------------------------------------ #

_BLUE_TEAM_PREAMBLE = (
    "You are a blue team security advisor reviewing the output of a red team exercise. "
    "For each vulnerability listed, provide: (1) a plain-English risk explanation, "
    "(2) immediate remediation steps with specific code or config changes, "
    "(3) detection strategies including what to log and what alerts to configure, "
    "(4) long-term hardening recommendations. "
    "Be specific and actionable. Format with a clear section per vulnerability.\n\n"
)


# ------------------------------------------------------------------ #
# Public interface                                                     #
# ------------------------------------------------------------------ #

def run(session: dict) -> dict:
    """
    Query TerpAI for blue team remediation advice based on session findings.

    Args:
        session: Shared session dict. Reads 'findings' and 'kill_chain'.
                 Writes 'blue_team' (the full advice report) back to session.

    Returns:
        Blue team report as a dict with keys:
            raw_advice      — full TerpAI response text (assembled from SSE stream)
            per_vuln        — list of {vuln_type, advice} dicts (best-effort parsed)
            conversation_id — TerpAI conversation ID for reference
    """
    ui.agent_header("BLUE TEAM")

    findings   = session.get("findings", [])
    kill_chain = session.get("kill_chain", [])

    if not findings:
        ui.print_error("No findings in session — nothing to advise on.")
        return {}

    ui.print_info(f"Preparing blue team query for {len(findings)} finding(s)...")

    token = _get_bearer_token()
    if not token:
        ui.print_error(
            "TERPAI_BEARER_TOKEN not set in .env\n"
            "Login to terpai.umd.edu → DevTools → Network → any request → "
            "copy the Authorization: Bearer <token> header value."
        )
        return {}

    client  = TerpAIClient(token)
    message = _build_query(findings, kill_chain)

    try:
        ui.print_info("Streaming response from TerpAI...")
        conversation_id, raw_advice = client.send_and_stream(message)

    except RuntimeError as e:
        ui.print_error(f"TerpAI request failed: {e}")
        return {}

    ui.print_success("Blue team advice received from TerpAI.")
    ui.stream_output(raw_advice)

    report = {
        "raw_advice":      raw_advice,
        "per_vuln":        _parse_per_vuln(raw_advice, findings),
        "conversation_id": conversation_id,
    }

    session["blue_team"] = report
    ui.print_info("Blue team report written to session['blue_team'].")
    return report


# ------------------------------------------------------------------ #
# TerpAI SSE client                                                    #
# ------------------------------------------------------------------ #

class TerpAIClient:
    """
    HTTP client for the TerpAI internal API.

    TerpAI responds to POST /byGptSystemId/{id} with a Server-Sent Events
    stream. Each line is either:
        event: <event-name>
        data:  <base64-encoded payload>
    or a blank line (separator between events).

    The response text is assembled by concatenating all decoded
    'response-updated' data chunks in order.
    """

    def __init__(self, bearer_token: str):
        self.token   = bearer_token
        self.session = requests.Session()
        self.session.headers.update(self._base_headers())

    # ---------------------------------------------------------------- #

    def send_and_stream(self, message: str) -> tuple[str, str]:
        """
        POST a message and consume the SSE stream to completion.

        Returns:
            (conversation_id, full_response_text) tuple.

        Raises:
            RuntimeError on HTTP error or malformed stream.
        """
        url = (
            f"{TERPAI_BASE_URL}/api/internal/userConversations"
            f"/byGptSystemId/{TERPAI_GPT_SYSTEM}"
        )
        payload = {
            "question":             message,
            "visionImageIds":       [],
            "attachmentIds":        [],
            "session":              {"sessionIdentifier": str(uuid.uuid4())},
            "segmentTraceLogLevel": "NonPersisted",
        }

        resp = self.session.post(
            url,
            json=payload,
            headers={"x-request-id": str(uuid.uuid4())},
            stream=True,           # keep connection open for SSE
            timeout=_STREAM_TIMEOUT_S,
        )

        if not resp.ok:
            raise RuntimeError(
                f"TerpAI POST → {resp.status_code}: {resp.text[:300]}"
            )

        return self._parse_sse_stream(resp)

    # ---------------------------------------------------------------- #
    # SSE stream parser                                                  #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _parse_sse_stream(resp: requests.Response) -> tuple[str, str]:
        """
        Parse the raw SSE byte stream from TerpAI.

        SSE format per event block:
            event: <name>\\n
            data: <base64>\\n
            \\n                  ← blank line = end of event

        Assembles the full response by decoding and concatenating every
        'response-updated' chunk in order.

        Returns:
            (conversation_id, assembled_response_text)
        """
        conversation_id = ""
        response_chunks = []
        current_event   = ""

        for raw_line in resp.iter_lines(decode_unicode=True):
            line = raw_line.strip() if raw_line else ""

            if line.startswith("event:"):
                current_event = line[len("event:"):].strip()

            elif line.startswith("data:"):
                raw_data = line[len("data:"):].strip()
                if not raw_data:
                    continue

                decoded = _b64_decode(raw_data)

                if current_event == "conversation-and-segment-id":
                    # {"ConversationId": "...", "ConversationSegmentId": "..."}
                    try:
                        meta = json.loads(decoded)
                        conversation_id = (
                            meta.get("ConversationId")
                            or meta.get("conversationId")
                            or ""
                        )
                        logger.debug(f"ConversationId: {conversation_id}")
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Could not parse conversation-and-segment-id: {decoded}"
                        )

                elif current_event == "response-updated":
                    # Each chunk is a token or short phrase — concatenate directly
                    response_chunks.append(decoded)

                elif current_event == "response-model":
                    # Final metadata — log for debugging
                    try:
                        logger.debug(f"response-model: {json.loads(decoded)}")
                    except json.JSONDecodeError:
                        pass

                elif current_event == "no-more-data":
                    break  # stream finished

                elif current_event == "step-update":
                    logger.debug(f"step-update: {decoded}")

                # cosmos-db-session-tokens — routing only, not needed

            elif line == "":
                current_event = ""  # blank line = event separator

        full_response = "".join(response_chunks).strip()

        if not full_response:
            raise RuntimeError(
                "SSE stream completed but no response-updated chunks received. "
                f"conversation_id={conversation_id!r}"
            )

        return conversation_id, full_response

    # ---------------------------------------------------------------- #
    # Headers                                                            #
    # ---------------------------------------------------------------- #

    def _base_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
            "Accept":        "text/event-stream",  # tells server we want SSE
            "x-timezone":    "America/New_York",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        }


# ------------------------------------------------------------------ #
# Message builder                                                      #
# ------------------------------------------------------------------ #

def _build_query(findings: list[dict], kill_chain: list[dict]) -> str:
    """
    Build the natural-language query to send to TerpAI.
    Includes the blue team framing preamble, all findings, and the kill chain.
    """
    lines = [
        _BLUE_TEAM_PREAMBLE,
        "## Vulnerabilities Found\n",
    ]

    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. [{f.get('severity', 'UNKNOWN')}] {f.get('type', 'Unknown')}\n"
            f"   File: {f.get('file', 'unknown')}:{f.get('line', '?')}\n"
            f"   Description: {f.get('description', 'No description')}\n"
        )

    if kill_chain:
        lines.append("\n## Red Team Kill Chain (for context)\n")
        for i, step in enumerate(kill_chain, 1):
            lines.append(
                f"Step {i}: {step.get('step', '')}\n"
                f"  Command:      {step.get('command', '')}\n"
                f"  MITRE Tactic: {step.get('mitre_tactic', '')}\n"
                f"  Vuln class:   {step.get('vuln_type', '')}\n"
            )

    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Response parsing                                                     #
# ------------------------------------------------------------------ #

def _parse_per_vuln(raw_advice: str, findings: list[dict]) -> list[dict]:
    """
    Best-effort split of the raw advice into per-vulnerability sections.
    Matches sections by looking for the vuln type name in headers/lines.

    Returns a list of {vuln_type, advice} dicts — one per finding.
    If a section can't be isolated, the full advice is used as fallback.
    """
    per_vuln = []
    lines    = raw_advice.splitlines()

    for finding in findings:
        vuln_type     = finding.get("type", "Unknown")
        section_lines = []
        in_section    = False

        for line in lines:
            if vuln_type.lower() in line.lower():
                in_section = True
            if in_section:
                section_lines.append(line)
                # Stop at the next major heading
                if len(section_lines) > 3 and line.startswith(("##", "---", "===")):
                    break

        per_vuln.append({
            "vuln_type": vuln_type,
            "advice":    "\n".join(section_lines).strip() or raw_advice,
        })

    return per_vuln


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _b64_decode(s: str) -> str:
    """
    Decode a base64 string to UTF-8 text.
    Returns the original string unchanged on failure.
    """
    try:
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return s


def _get_bearer_token() -> str:
    """Read TERPAI_BEARER_TOKEN from nara config. Returns '' if unset."""
    return getattr(cfg, "TERPAI_BEARER_TOKEN", "") or ""