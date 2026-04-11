# NARA — Autonomous Red Team Platform

An AI-powered penetration testing CLI that orchestrates three agents to scan codebases, plan attack chains, and execute exploits against an isolated Docker container — streaming the entire kill chain live to the terminal.

Built for **Bitcamp 2025** (Cybersecurity Track + Neelbauer Agent Revolution Award).

> Security tools tell you *what* is vulnerable. NARA shows you *what happens when it gets exploited* — autonomously, in real time, end to end.

---

## Demo

```
$ nara

 ███╗   ██╗ █████╗ ██████╗  █████╗
 ████╗  ██║██╔══██╗██╔══██╗██╔══██╗
 ██╔██╗ ██║███████║██████╔╝███████║
 ██║╚██╗██║██╔══██║██╔══██╗██╔══██║
 ██║ ╚████║██║  ██║██║  ██║██║  ██║
 ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

nara > init
[+] Building Docker image... done
[+] Container running — VNC on :5901, app port :8080

nara > scan /path/to/vulnerable-app
[SCANNER] Running Semgrep... Running Bandit...
[SCANNER] Found 3 vulnerabilities:
  CRITICAL — Command Injection in app.py:23
  HIGH     — SQL Injection in app.py:45
  MEDIUM   — Reflected XSS in templates/index.html:15

nara > plan
[PLANNER] Designing kill chain from 3 findings...
  1. Reconnaissance — confirm app is live
  2. Command Injection — whoami
  3. Upload ransomware payload
  4. Ransomware Deployment

nara > exploit
[EXPLOITER] Executing 4 kill chain steps...
[STEP 1/4] Reconnaissance            ✓
[STEP 2/4] Command Injection — whoami ✓  (www-data)
[STEP 3/4] Upload ransomware payload  ✓
[STEP 4/4] Ransomware Deployment      ✓
Kill chain complete — check VNC :5901 to see the desktop.
```

---

## How It Works

```
USER (natural language)
  │
  ▼
nara CLI (interactive REPL)
  │
  ▼
Orchestrator (intent routing)
  │
  ├── Agent 1: Scanner
  │     Runs Semgrep + Bandit → LLM deduplicates and prioritizes findings
  │
  ├── Agent 2: Planner
  │     Takes findings → LLM designs ordered kill chain (always ends with ransomware)
  │
  └── Agent 3: Exploiter
        Provisions Docker container → executes kill chain via docker exec
        LLM assesses each step → adapts on failure (retry / rewrite command / abort)
        Deploys ransomware payload as final step
```

**Host machine** = scanning, planning, orchestration, LLM reasoning
**Docker container** = disposable target with Ubuntu 22.04 + XFCE desktop + VNC

---

## Setup

### Prerequisites

- Python 3.10+
- Docker
- One of: [Ollama](https://ollama.com) (free, local) or an [Anthropic API key](https://console.anthropic.com)

### Install

```bash
# Clone
git clone https://github.com/HackedRico/obv-nara-box.git
cd obv-nara-box

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install .

# Configure LLM backend
cp .env.example .env
# Edit .env — set LLM_BACKEND and API keys

# Build the Docker target container
docker build -t nara-target ./nara/docker/
```

### LLM Backend

Set `LLM_BACKEND` in `.env` — no code changes needed to switch:

| Backend | Config | Use case |
|---|---|---|
| `ollama` | `OLLAMA_MODEL=qwen2.5` | Development — free, local. Run `ollama pull qwen2.5` first. |
| `claude` | `ANTHROPIC_API_KEY=sk-...` | Demo — best reasoning quality. |
| `featherless` | `FEATHERLESS_API_KEY=...` | Open-source models via OpenAI-compatible API. |

---

## Usage

```bash
nara
```

This opens an interactive REPL. Available commands:

| Command | What it does |
|---|---|
| `init` | Build image and start the Docker container |
| `scan <path>` | Run Semgrep + Bandit, LLM triages results |
| `plan` | Design a kill chain from scan findings |
| `exploit` | Execute the kill chain against the container |
| `status` | Show current findings, kill chain, and container state |
| `reset` | Tear down container and clear session |
| `help` | Show available commands |
| `exit` | End session |

Or just type naturally — NARA understands plain English and falls back to conversational LLM responses.

### Typical flow

```
nara > init                    # spin up the container
nara > scan /path/to/code      # find vulnerabilities
nara > plan                    # design the attack
nara > exploit                 # execute it live
```

After exploitation, connect to **VNC on port 5901** to see the ransomware desktop effects (wallpaper change, ransom note, "encrypted" files).

---

## Project Structure

```
nara/
├── cli.py                 # Interactive REPL entry point
├── orchestrator.py        # NLP intent routing → agents
├── agents/
│   ├── scanner.py         # Semgrep + Bandit → LLM triage
│   ├── planner.py         # Kill chain architect
│   └── exploiter.py       # Container provisioning + exploitation
├── docker/
│   ├── Dockerfile         # Ubuntu 22.04 + XFCE + VNC
│   ├── docker_manager.py  # Container lifecycle (build/run/exec/reset)
│   └── start_vnc.sh       # Container entrypoint
├── payloads/
│   ├── ransomware.py      # Wallpaper, ransom note, fake encryption
│   └── assets/            # Default wallpaper + note template
└── utils/
    ├── llm_client.py      # Ollama / Claude / Featherless abstraction
    ├── terminal_ui.py     # Rich-based terminal output
    └── config.py          # .env loading + validation
```

---

## Target Application

NARA is designed to exploit a separate **Pokemon-themed vulnerable Flask app** ([pokedex-vuln](https://github.com/HackedRico/pokedex-vuln)) with deliberate injection flaws. The Exploiter agent clones it into the container at runtime.

Primary exploit path: **command injection** on `GET /api/pokemon?name=<input>` — user input goes straight to `os.system()` with no sanitization.

---

## Legal Scope

This tool is built for **educational and authorized security research only**.

- Only targets deliberately vulnerable applications in isolated Docker containers
- Ransomware payload is a visual simulation — no real encryption or exfiltration
- Container is disposable and resettable
- Never use against systems without explicit written permission

---

## Tech Stack

| Layer | Tools |
|---|---|
| CLI | Python, prompt_toolkit, Rich |
| LLM | Ollama/Qwen2.5, Claude API, or Featherless |
| Static Analysis | Semgrep, Bandit |
| Container | Docker, Ubuntu 22.04, XFCE, TigerVNC |
| Target App | Flask (separate repo) |

---

## Team

Built at Bitcamp 2025, University of Maryland.
