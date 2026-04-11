# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NARA** — An AI-powered autonomous penetration testing CLI built for Bitcamp 2025 (Cybersecurity Track). It orchestrates three AI agents (Scanner, Planner, Exploiter) to scan codebases, design attack chains, and execute exploits against an isolated Docker container running a vulnerable Flask app. All output streams live to the terminal.

## Setup & Commands

```bash
pip install -r requirements.txt       # Python deps
pip install -e .                       # Install `nara` CLI entry point
cp .env.example .env                   # Configure LLM backend
ollama pull qwen2.5                    # Only if using Ollama backend
docker build -t nara-target ./nara/docker/   # Build the target container
nara                                   # Launch interactive REPL
```

SAST tools (used by the Scanner agent): `pip install semgrep bandit`

There are no tests or linting configured.

## LLM Backend

Three backends, switched via `LLM_BACKEND` in `.env` — no code changes needed:

| Backend | Env var | Use case |
|---|---|---|
| `ollama` | `OLLAMA_MODEL=qwen2.5` | Local dev (free) |
| `claude` | `ANTHROPIC_API_KEY=...` | Demo (best quality) |
| `featherless` | `FEATHERLESS_API_KEY=...`, `FEATHERLESS_MODEL=...` | Open-source models via OpenAI-compatible API (requires `pip install openai`) |

`nara/utils/llm_client.py` abstracts all three behind `LLMClient.chat(messages, system)`. All agents use this single interface.

## Architecture

### Data flow

```
User input → cli.py (REPL) → orchestrator.route() → keyword intent classifier
  ├─ "scan"    → scanner.run(path, session) → Semgrep + Bandit → LLM triage → findings list
  ├─ "plan"    → planner.run(findings, session) → LLM kill chain design → step list
  ├─ "exploit" → exploiter.run(kill_chain, session) → docker exec → LLM step assessment
  └─ other     → LLM conversational fallback
```

### Session state

`cli.py` creates a session dict (`findings`, `kill_chain`, `container_running`, `history`) passed to every `orchestrator.route()` call. Agents mutate it directly.

### Agent contracts

All three agents in `nara/agents/` follow the same pattern:
- LLM system prompts demand **raw JSON only** (no markdown) — arrays of dicts with specific keys
- `_parse_json_list()` strips markdown fences then `json.loads()`
- Each agent has a hardcoded fallback if LLM output fails to parse

**Scanner** output keys: `type, file, line, severity, description, exploitability`
**Planner** output keys: `step, command, expected_outcome, vuln_type, mitre_tactic`
**Planner always appends ransomware deployment as the final step** if the LLM doesn't include it.

### Exploiter adaptive loop

For each kill chain step, the Exploiter:
1. Executes via `docker exec` (or DRY RUN print if DockerManager unavailable)
2. Sends output to LLM for assessment → returns `{success, reason, next_action}`
3. `next_action` can be `continue`, `retry` (same command), `adapt` (LLM rewrites command), or `abort`

### Docker integration

`nara/docker/docker_manager.py` and the Dockerfile exist but are stubs (empty/minimal). The Exploiter gracefully falls back to **DRY RUN mode** (prints commands without executing) when DockerManager can't be imported or initialized. The expected interface is:

```python
DockerManager().build() / .run() / .exec(cmd: str) -> str / .reset() / .is_running() -> bool
```

### Vulnerable app target

The Exploiter clones a separate repo (`VULN_APP_REPO` constant in `exploiter.py` — currently a placeholder URL) into the container at runtime. Primary exploit path: command injection on `GET /api/pokemon?name=<input>`.

### Ransomware payload

`nara/payloads/ransomware.py` is **self-contained stdlib-only Python** designed to run inside the container. It creates dummy files then "encrypts" them (renames to `.NARA_ENCRYPTED`), drops a ransom note, generates a dark-red PNG wallpaper from scratch using struct+zlib, and attempts to set it via `xfconf-query` or `feh`.
