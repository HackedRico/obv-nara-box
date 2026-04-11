# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NARA** — An AI-powered autonomous penetration testing CLI built for Bitcamp 2025 (Cybersecurity Track). It orchestrates three AI agents to scan codebases, plan attack chains, and execute exploits against an isolated Docker container running a vulnerable Flask app.

> **Note:** As of project start, only `PLAN.md` exists. Implementation has not begun. All architecture below reflects the planned design in `PLAN.md`.

## Setup & Commands

```bash
# Install Python dependencies
pip install -r requirements.txt

# Pull the local LLM model (development mode)
ollama pull qwen2.5

# Configure environment
cp .env.example .env  # Set LLM_BACKEND=ollama or LLM_BACKEND=claude

# Build Docker container
docker build -t nara-target ./nara/docker/

# Install CLI locally
pip install -e .

# Run the interactive CLI
nara
```

## LLM Backend

Controlled entirely via `.env` — no code changes needed to switch:

```
# Development (local, free)
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5

# Demo (production quality)
LLM_BACKEND=claude
ANTHROPIC_API_KEY=sk-...
```

`nara/utils/llm_client.py` abstracts both backends behind a unified interface used by all agents.

## Architecture

### Agent Pipeline

User NLP input → `orchestrator.py` → sequential agent pipeline:

1. **Scanner** (`agents/scanner.py`) — runs Semgrep, Bandit, Snyk on the target repo; LLM deduplicates and prioritizes findings
2. **Planner** (`agents/planner.py`) — receives scanner findings, designs an ordered kill chain including ransomware deployment
3. **Exploiter** (`agents/exploiter.py`) — provisions the Docker container, executes the kill chain via `docker exec`, streams live output to terminal

### Container Architecture

The Docker container (Ubuntu 22.04 + XFCE + VNC on port 5901) is provisioned at runtime by the Exploiter agent. It runs a Pokemon-themed Flask app (separate repo) with deliberate vulnerabilities. Primary exploit path: command injection on `GET /api/pokemon?name=<input>`.

### Key Module Map

```
nara/
├── cli.py              # Interactive REPL entry point
├── orchestrator.py     # Routes intent to agent pipeline
├── agents/
│   ├── scanner.py      # SAST tool runner + LLM triage
│   ├── planner.py      # Kill chain design
│   └── exploiter.py    # Container provisioning + execution
├── docker/
│   ├── Dockerfile      # Ubuntu 22.04 + XFCE + VNC
│   └── docker_manager.py
├── payloads/
│   └── ransomware.py   # Wallpaper, icons, ransom note simulation
└── utils/
    ├── llm_client.py   # Ollama/Claude abstraction
    ├── terminal_ui.py  # Rich terminal output
    └── config.py       # .env loading
```

## Build Phases (from PLAN.md)

1. **Phase 1** — Docker image + `docker_manager.py`
2. **Phase 2** — `llm_client.py` + interactive CLI (`nara` REPL)
3. **Phase 3** — All three agents + full pipeline
4. **Phase 4** — Polish, reliability testing, demo prep (switch to Claude API)
