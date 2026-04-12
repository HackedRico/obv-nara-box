# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NARA** — An AI-powered autonomous penetration testing CLI built for Bitcamp 2026 (Cybersecurity Track + Neelbauer Agent Revolution Award). It orchestrates three AI agents (Scanner, Planner, Exploiter) to scan codebases, design attack chains, and execute exploits against an isolated Docker container running a vulnerable Flask app. All output streams live to the terminal; the container exposes VNC (5901), noVNC (6080), and the target app (8080) so the user can watch exploitation in real time.

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

Three backends, switched via `LLM_BACKEND` in `.env` — no code changes needed. **Default:** `featherless` with `microsoft/Phi-4-mini-instruct` (see [featherless.ai/models](https://featherless.ai/models)).

| Backend | Env var | Use case |
|---|---|---|
| `featherless` | `FEATHERLESS_API_KEY=...`, `FEATHERLESS_MODEL=microsoft/Phi-4-mini-instruct` (default) | Primary — OpenAI-compatible API (`pip install openai`) |
| `ollama` | `OLLAMA_MODEL=qwen2.5-coder:7b-instruct` | Local dev (free) |
| `claude` | `ANTHROPIC_API_KEY=...` | Anthropic API |

`nara/utils/llm_client.py` abstracts all three behind `LLMClient.chat(messages, system)`. All agents use this single interface.

## Architecture

### Data flow

```
User input → cli.py (REPL) → orchestrator.route() → keyword intent classifier
  ├─ "pipeline" → scan → plan → exploit (full auto, end to end)
  ├─ "scan"     → scanner.run(path, session) → Semgrep + Bandit → LLM triage → findings list
  ├─ "plan"     → planner.run(findings, session) → LLM kill chain design → step list
  ├─ "exploit"  → exploiter.run(kill_chain, session) → docker exec → LLM step assessment
  ├─ "init" / "reset" / "status" / "help" / "exit" → DockerManager + session plumbing
  └─ chat       → LLM conversational fallback
```

Intent classification is keyword-based in `orchestrator._classify_intent()`. When the user passes a URL or path argument to `scan`/`pipeline`, `_clone_repo()` shallow-clones it into `./nara_targets/<repo>/` (normalizing GitHub `/tree/`, `/blob/` URLs) and scans the local copy.

### Session state

`cli.py` creates a session dict (`findings`, `kill_chain`, `container_running`, `app_provisioned`, `history`, and optionally `scan_path` / `target_repo`) passed to every `orchestrator.route()` call. Agents mutate it directly.

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

`nara/docker/docker_manager.py` is fully implemented and shells out to the `docker` CLI. The container image (`nara-target`) is pre-baked with Firefox + an XFCE/VNC desktop so the Exploiter can drive the browser live. Key methods beyond the base contract:

- `exec(cmd) -> str` — run a command, capture combined stdout+stderr, 120s timeout
- `exec_detached(cmd)` — fire-and-forget (used to launch the tail-follow terminal, Firefox, etc.)
- `copy_to_container(host_path, container_path)` — `docker cp` wrapper
- `write_to_container_file(path, text)` / `append_to_container_file(path, text)` — pipe UTF-8 into the container via `bash -c 'cat > …'` / `tee -a`

The Exploiter still has a **DRY RUN fallback**: if DockerManager can't be imported or a step's `_exec` returns None, commands are printed rather than executed. The Dockerfile path is resolved relative to `docker_manager.py` so the package works both editable-installed and from a site-packages copy.

`DOCKERFILE_DIR`, `IMAGE_NAME = "nara-target"`, and `CONTAINER_NAME = "nara-container"` are module constants — if you rename the image/container you must change both places.

### Vulnerable app target

The Exploiter clones a separate vulnerable-app repo into the container at runtime. The real target lives at `https://github.com/aprameyak/exploitable-dummy-app` (per README), but the `VULN_APP_REPO` constant at the top of `nara/agents/exploiter.py` is still a `PLACEHOLDER` — update that constant before running against the real target. Primary exploit path: command injection on `GET /api/pokemon?name=<input>`.

### Ransomware payload

`nara/payloads/ransomware.py` is **self-contained stdlib-only Python** designed to run inside the container. It creates dummy files then "encrypts" them (renames to `.NARA_ENCRYPTED`), drops a ransom note, generates a dark-red PNG wallpaper from scratch using struct+zlib, and attempts to set it via `xfconf-query` or `feh`.
