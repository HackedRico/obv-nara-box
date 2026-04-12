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

## Known placeholder before running

`VULN_APP_REPO` in `nara/agents/exploiter.py:22` is still `"https://github.com/PLACEHOLDER/pokedex-vuln"` — update it to the real vulnerable Flask app repo URL before running the exploit pipeline. The provisioning logic at `exploiter._provision()` will use `session["target_repo"]` if set by a prior scan, falling back to this constant.

## LLM Backend

Three backends, switched via `LLM_BACKEND` in `.env` — no code changes needed. **Default:** `featherless` with `microsoft/Phi-4-mini-instruct` (see [featherless.ai/models](https://featherless.ai/models)).

| Backend | Env var | Use case |
|---|---|---|
| `featherless` | `FEATHERLESS_API_KEY=...`, `FEATHERLESS_MODEL=microsoft/Phi-4-mini-instruct` (default) | Primary — OpenAI-compatible API (`pip install openai`) |
| `ollama` | `OLLAMA_MODEL=qwen2.5-coder:7b-instruct` | Local dev (free) |
| `claude` | `ANTHROPIC_API_KEY=...` | Anthropic API |

`nara/utils/llm_client.py` abstracts all three behind `LLMClient.chat(messages, system)`. All agents use this single interface. Config is loaded from the nearest `.env` walking up from `config.py` or `cwd` — see `nara/utils/config.py`.

There is also `nara/utils/terpai_client.py` — a standalone `TerpAIClient` wrapping the UMD TerpAI (NebulaOne) SSE API with Playwright-based browser auth and JWT caching. It is **not wired into `LLMClient`** yet; it can be integrated as a fourth backend if needed.

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

### LLM JSON parsing

All agents rely on `nara/utils/llm_json.parse_json_array_from_llm()` rather than bare `json.loads()`. It handles: BOM stripping, `<think>` / reasoning block removal (Qwen/DeepSeek), markdown fence removal, and unwrapping objects that contain an array under common keys (`findings`, `steps`, `kill_chain`, etc.). Use this utility for any new agent that needs to parse LLM-returned JSON.

### Agent contracts

All three agents in `nara/agents/` follow the same pattern:
- LLM system prompts demand **raw JSON only** (no markdown) — arrays of dicts with specific keys
- JSON is parsed via `parse_json_array_from_llm()` from `nara/utils/llm_json.py`
- Each agent has a hardcoded fallback if LLM output fails to parse

**Scanner** output keys: `type, file, line, severity, description, exploitability`  
**Planner** output keys: `step, command, expected_outcome, vuln_type, mitre_tactic`  
**Planner always appends ransomware deployment as the final step** if the LLM doesn't include it.

Scanner findings are normalized through `_normalize_finding()` (maps ~30 alternative key names LLMs commonly emit) and deduplicated by `(file, line)` before being returned.

### Exploiter adaptive loop

For each kill chain step, the Exploiter:
1. Executes via `docker exec` (or DRY RUN print if DockerManager unavailable)
2. Sends output to LLM for assessment → returns `{success, reason, next_action}`
3. `next_action` can be `continue`, `retry` (same command), `adapt` (LLM rewrites command), or `abort`

Steps whose name or command contains `"ransomware"` are routed to `_deploy_ransomware()` instead of normal execution. That function copies `nara/payloads/ransomware.py` into the container and runs it with `DISPLAY=:1`.

### Docker integration

`nara/docker/docker_manager.py` shells out to the `docker` CLI. The container image (`nara-target`) is pre-baked with Firefox + an XFCE/VNC desktop so the Exploiter can drive the browser live. Key methods:

- `exec(cmd) -> str` — run a command, capture combined stdout+stderr, 120s timeout
- `exec_detached(cmd)` — fire-and-forget (used to launch the tail-follow terminal, Firefox, etc.)
- `copy_to_container(host_path, container_path)` — `docker cp` wrapper
- `write_to_container_file(path, text)` / `append_to_container_file(path, text)` — pipe UTF-8 into the container via `bash -c 'cat > …'` / `tee -a`

`IMAGE_NAME = "nara-target"` and `CONTAINER_NAME = "nara-container"` are module constants — rename both if the image/container names change.

The Exploiter has a **DRY RUN fallback**: if DockerManager can't be imported or `_exec` returns None, commands are printed rather than executed. All VNC log writes (`_append_vnc_log`) and browser launch (`_launch_vnc_browser`) are no-ops in DRY RUN mode.

### Ransomware payload

`nara/payloads/ransomware.py` is **self-contained stdlib-only Python** designed to run inside the container. It creates dummy files then "encrypts" them (renames to `.NARA_ENCRYPTED`), drops a ransom note, generates a dark-red PNG wallpaper from scratch using struct+zlib, and attempts to set it via `xfconf-query` or `feh`. An optional `team_rocket_wallpaper.jpg` asset in `nara/payloads/assets/` is copied to the container first if it exists.
