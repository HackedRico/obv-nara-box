# Lifecycle — Autonomous Red Team Platform

---

## Hackathon Context

**Event:** Bitcamp 2025 — University of Maryland, College Park
**Date:** April 11–13, 2025 (36-hour hacking window: 9:00 PM Friday → 9:30 AM Sunday)
**Venue:** Reckord Armory, UMD

### Track: Cybersecurity
> *"Explore the realm of cybersecurity and understand various aspects of the field through interactive workshops that include discussions of web vulnerabilities, real-world applications of combating security weaknesses, and ethical decision-making."*
>
> *Best hack that demonstrates cybersecurity principles and incorporates cybersecurity workshop content.*

### Special Award: Neelbauer Agent Revolution Award (NARA)
> *"Best example of using trained and initially prompted AI agents launched at Bitcamp to autonomously red team another software or agent or build the best unexpected/unprompted output on its own after initial training and prompting."*
>
> **Prize:** $75 Visa Gift Card — Judge: Juliana Neelbauer

**Lifecycle is submitted to both the Cybersecurity Track and targeting the NARA special award.**

---

## Overview

An AI-powered penetration testing platform with a **Claude Code-style natural language CLI** called **Lifecycle**, invoked with `nara`. The user points it at a codebase, the platform autonomously scans it, plans an attack chain, then fires exploits into an isolated Docker container — streaming the entire kill chain live to the terminal.

**LLM backend:** Ollama + Qwen2.5 for development (free, local). Claude API for demo (better reasoning). Switched via `.env`.

The core market gap: security tools tell you *what* is vulnerable. Lifecycle shows you *what happens when it gets exploited* — in real time, autonomously, end to end.

---

## The Problem

- SAST/DAST tools produce CVE numbers and severity scores
- Non-technical stakeholders have no visceral understanding of what a vulnerability means in practice
- Security reports are ignored because the impact is abstract
- Real attackers operate autonomously — defenders need to see that

---

## The Solution

A natural language CLI (run `nara`) that orchestrates three prompt-engineered AI agents across two environments — the host machine and an isolated Docker container — taking a codebase from scan to live exploit with a human-in-the-loop feedback model. All output streams directly to the terminal.

---

## Architecture

```
HOST MACHINE                          DOCKER CONTAINER (Ubuntu 22.04 + XFCE + VNC)
─────────────────────────────         ──────────────────────────────
nara CLI (NLP interactive terminal)   XFCE desktop + VNC ready on boot
LLM: Ollama/Qwen2.5 (dev)            (GUI for observing ransomware effects)
     Claude API (demo)
        ↓                             
Agent 1 — Scanner (host-side)         
  runs: Semgrep, Bandit, Snyk, etc.
        ↓ structured findings
Agent 2 — Planner                     
  designs kill chain from findings
        ↓ kill chain plan
Agent 3 — Exploiter ── docker exec ──→ Sets up + exploits:
        ↓                               - starts vulnerable web app
        ↓                               - fires exploits
        ↓                               - deploys ransomware payload
Terminal output (Rich) ←── stdout/stderr from container
```

**Host** = scanning, planning, orchestration, LLM reasoning
**Container** = target environment with GUI — disposable, resettable
**Communication** = `docker exec`

**Agent flow:**
1. **Scanner** runs multiple SAST tools against the codebase, LLM reasons over combined output
2. **Planner** takes findings, designs the full kill chain (including ransomware as final stage)
3. **Exploiter** provisions the container, starts the app, executes the kill chain, deploys ransomware

---

## CLI — `nara`

One command to enter. Interactive REPL session — like Claude Code.

```bash
$ nara
```

Opens a persistent conversational session. The agent talks back, asks questions when it needs input, and executes autonomously when it has enough context.

```
$ nara

  ╭──────────────────────────────────╮
  │  Lifecycle — Autonomous Red Team  │
  ╰──────────────────────────────────╯

lifecycle > hey, set up the environment
[+] Starting container... done
[+] XFCE desktop + VNC ready on :5901
Ready to go. Want me to scan something?

lifecycle > yeah scan this repo
[SCANNER] Running Semgrep...
[SCANNER] Running Bandit...
[SCANNER] Found 3 vulnerabilities:
  1. CRITICAL — Command Injection in app.py:23
  2. HIGH — XSS in templates/index.html:15
  3. MEDIUM — Hardcoded secret in config.py:4
Want me to exploit these?

lifecycle > go for it, full chain
[PLANNER] Designing kill chain...
  Step 1: Deploy vulnerable app in container
  Step 2: Exploit command injection via /ping endpoint
  Step 3: Confirm shell access
  Step 4: Deploy ransomware simulation

[EXPLOITER] Starting vulnerable app in container...
[EXPLOITER] App running on container:8080
[EXPLOITER] Targeting command injection at /ping endpoint...
[EXPLOITER] Sending payload: ; whoami
[EXPLOITER] Response: www-data — shell access confirmed
[RANSOMWARE] What image do you want for the ransom wallpaper?

lifecycle > something scary, like a skull
[RANSOMWARE] Got it. Deploying payload...
[RANSOMWARE] Wallpaper changed, icons modified, ransom note dropped
[RANSOMWARE] ✓ Complete — check VNC :5901 to see the desktop

lifecycle > what did you find?
I found 3 vulnerabilities in the Flask app. The critical one was a command
injection in the /ping endpoint — user input goes straight to os.system()
with no sanitization. I exploited it to get shell access as www-data, then
deployed the ransomware sim. Check VNC to see the desktop effects.

lifecycle > exit
```

**Key behaviors:**
- Conversational — responds naturally, asks clarifying questions
- Human-in-the-loop — user feedback drives agent decisions
- Stateful — remembers findings across the session
- Autonomous — once it has context, runs the full chain without prompting

---

## Project Structure

```
obv-nara-box/                           # THIS REPO — the nara CLI platform
├── lifecycle/                  
│   ├── __init__.py
│   ├── cli.py                  # Entry point — `nara` interactive REPL
│   ├── orchestrator.py         # Routes NLP intent → agent pipeline
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── scanner.py          # Agent 1 — runs Semgrep, Bandit, Snyk, etc.
│   │   ├── planner.py          # Agent 2 — kill chain design from scan results
│   │   └── exploiter.py        # Agent 3 — container setup + kill chain execution
│   ├── docker/
│   │   ├── Dockerfile          # Ubuntu 22.04 + XFCE + VNC (GUI layer only)
│   │   ├── docker_manager.py   # Container lifecycle (build, run, reset, exec)
│   │   └── start_vnc.sh        # Entrypoint — starts VNC + XFCE on boot
│   ├── payloads/
│   │   ├── ransomware.py       # Wallpaper change, icon rename, ransom note
│   │   └── assets/             # Default ransom images, note templates
│   └── utils/
│       ├── llm_client.py       # LLM abstraction — Ollama (dev) / Claude API (demo)
│       ├── terminal_ui.py      # Rich terminal output (streaming, colors, panels)
│       └── config.py           # .env loading, model config, container config
├── .env.example                # Template: LLM_BACKEND=ollama|claude, API keys
├── requirements.txt            # Python deps (ollama, anthropic, rich, prompt_toolkit)
├── setup.py                    # Makes `nara` a CLI command
└── PLAN.md

SEPARATE REPO (e.g., github.com/HackedRico/vuln-flask-app)
  — Claude-generated vulnerable web app with command injection
├── app.py                      # Flask app with deliberate injection flaws
├── templates/                  # HTML templates
└── requirements.txt
```

---

## Agent Architecture

### Agent 1 — Scanner
Runs on the **host machine** against the target codebase.

**Tools (one agent, multiple tools — no sub-agents):**
- Semgrep — pattern-based static analysis (XSS, SQLi, RCE, command injection)
- Bandit — Python-specific SAST
- JavaScript dependency scanner (e.g., `npm audit`)
- Snyk — dependency vulnerability scanning
- Other tools as needed

The Scanner runs all applicable tools, collects their output, and the LLM reasons over the **combined results** in a single pass — deduplicates, prioritizes, assesses exploitability.

**Output:** Structured findings — vuln type, file, line, severity, how it could be exploited.

---

### Agent 2 — Planner
Runs on the **host machine**. The **kill chain architect**.

**Responsibilities:**
1. Takes Scanner findings and designs the full attack sequence
2. Determines what tools/setup the Exploiter will need in the container
3. Defines the kill chain as ordered steps with expected outcomes
4. Kill chain always ends with ransomware deployment as the impact stage

**Output:** Kill chain definition — ordered steps, commands, expected outcomes, tool requirements.

---

### Agent 3 — Exploiter
Runs on the **host machine** but fires all commands **into the Docker container via `docker exec`**.

**Responsibilities:**
1. Receives the kill chain from Agent 2
2. **Sets up the container** — starts the vulnerable web app, installs exploit tools, confirms target is reachable
3. Executes each kill chain step sequentially
4. Adapts if a step fails (retries, adjusts payload, tries alternate approach)
5. Deploys the ransomware payload as the final step
6. Streams every step + reasoning to the terminal

The Exploiter is told that XFCE + VNC exists in the container and can leverage the desktop for visual ransomware effects.

**Output:** Live terminal output of the full exploitation → ransomware simulation deployed.

---

## Vulnerable Web App

A **Claude-generated** Flask web server with deliberate injection flaws — lives in a **separate public GitHub repo**.

**Vulnerabilities:**
- Command injection — a "ping" / "network lookup" form passes user input to `os.system()` with no sanitization
- Allows shell access via the web interface (e.g., `; cat /etc/passwd`, `; whoami`)
- Basic HTML UI so it looks like a real application

**Why Claude-generated:** More meta — an AI builds the vulnerable app, another AI finds and exploits the vulns. Good story for NARA judges.

---

## Ransomware Simulation Payload

Pre-built Python/bash scripts that the Exploiter deploys after gaining shell access.

**Effects:**
- Changes XFCE desktop wallpaper to a ransom image
- Renames/changes desktop shortcut icons
- Drops a ransom note (`README_RANSOM.txt`) on the desktop
- Optionally "encrypts" (base64 encodes) dummy files
- The CLI asks the user what image/text they want before deploying (NLP customization)
- Default hardcoded assets for quick demo

---

## Docker Container

One container — the **disposable target environment** with a GUI for observing exploit effects.

### What's Baked In (Dockerfile)

```
Base:       Ubuntu 22.04
Desktop:    XFCE4 + TigerVNC (starts on boot via start_vnc.sh)
Exposed:    Port 5901 (VNC — observe the desktop)
            Port 8080 (for vulnerable web app)
```

### What the Exploiter Agent Sets Up at Runtime

```
via docker exec:
  1. apt-get install python3 pip git curl wget netcat ...
  2. git clone the vulnerable Flask repo
  3. pip install flask (+ deps)
  4. Start the vulnerable web app on port 8080
  5. Install any exploit-specific tools from the kill chain plan
  6. Confirm app is reachable
```

### Container Lifecycle

```
User types "init" in nara session
    ↓
docker build (first time) + docker run
    ↓
Container running — XFCE desktop + VNC ready, nothing else
    ↓
Exploiter agent provisions via docker exec:
  → installs packages, clones vuln repo, starts app
    ↓
Container ready → app at localhost:8080, desktop via VNC :5901
    ↓
Exploiter agent fires kill chain via docker exec
    ↓
User types "reset" → stop + remove + fresh run (clean slate)
```

---

## LLM Backend

Dual backend with `.env` toggle — no code changes needed to switch.

```
.env:
  LLM_BACKEND=ollama          # or "claude"
  OLLAMA_MODEL=qwen2.5        # for dev
  ANTHROPIC_API_KEY=sk-...    # for demo (only needed if LLM_BACKEND=claude)
```

| Mode | Backend | When to use |
|---|---|---|
| Development | Ollama + Qwen2.5 (local, free) | Day-to-day dev, testing, iteration |
| Demo | Claude API | Hackathon judging, better reasoning quality |

`llm_client.py` abstracts this — all agents call the same interface regardless of backend.

---

## The Kill Chain (Full Demo Flow)

1. User runs `nara`
2. Types "init" → container spins up (XFCE + VNC ready)
3. Types "scan this repo and exploit whatever you find"
4. **Scanner** runs Semgrep, Bandit, etc. — finds vulnerabilities
5. **Planner** designs the kill chain including ransomware as final stage
6. **Exploiter** provisions container (starts app, installs tools, confirms ready)
7. **Exploiter** executes kill chain step-by-step
8. Agent asks user for ransomware customization
9. Ransomware payload deploys (wallpaper, icons, ransom note visible via VNC)
10. User can ask "what did you find?" for a conversational summary

---

## Tech Stack

| Layer | Tools |
|---|---|
| CLI | Python + prompt_toolkit + Rich |
| LLM (dev) | Ollama + Qwen2.5 (local, free) |
| LLM (demo) | Claude API |
| LLM switching | `.env` config — `llm_client.py` abstracts the backend |
| SAST scanning | Semgrep, Bandit, npm audit, Snyk |
| Kill chain planning | LLM-powered (Agent 2 — Planner) |
| Exploit execution | docker exec + curl/wget |
| Container | Docker — Ubuntu 22.04 + XFCE + VNC |
| Vulnerable app | Flask (Claude-generated, separate repo) |
| Ransomware sim | Python/bash payload scripts |
| Agent reasoning | LLM — prompt-engineered per agent role |

---

## Build Phases

### Phase 1 — Docker Image + Manager + Vulnerable App Repo
- Create Dockerfile (Ubuntu 22.04 + XFCE + VNC — GUI layer only)
- Create start_vnc.sh entrypoint (boots XFCE desktop + VNC server)
- Create docker_manager.py (build image, run container, exec wrapper, reset)
- Use Claude to generate the vulnerable Flask app in a **separate public repo**
- Verify: container starts, VNC accessible, desktop visible, docker exec works

### Phase 2 — LLM Client + Interactive CLI (`nara`)
- Create `.env` + `config.py` for LLM backend switching
- Create `llm_client.py` — unified interface for Ollama and Claude API
- Confirm Ollama running with Qwen2.5 pulled (`ollama pull qwen2.5`)
- Create the `nara` interactive REPL with prompt_toolkit
- Rich terminal output (colored agents, streaming text)
- setup.py so `nara` is the CLI entry point
- Verify: `nara` starts, can chat, intent routing works

### Phase 3 — Agents (Scanner → Planner → Exploiter)
- Implement Scanner agent (runs Semgrep, Bandit, Snyk — LLM reasons over combined output)
- Implement Planner agent (kill chain design from scan results, always includes ransomware)
- Implement Exploiter agent (container provisioning + kill chain execution + ransomware deployment)
- Create ransomware payload scripts (wallpaper, icons, ransom note)
- Wire up NLP customization for payload (ask user for image/text preferences)
- Validate structured handoff between all three agents
- Full pipeline: scan → plan → provision + exploit → ransomware deployed

### Phase 4 — Polish + Demo Prep
- Clean terminal output, timing/stats
- Test full chain for reliability
- Switch to Claude API backend for demo quality
- Prepare vulnerable app repo for "scanning unknown code" demo

---

## Dependencies

**Python packages:** `ollama`, `anthropic`, `rich`, `prompt_toolkit`, `python-dotenv`
**System:** Docker, Ollama (with `qwen2.5` model), Semgrep (`pip install semgrep`), optionally Bandit/Snyk
**API keys:** Anthropic API key (demo only — set in `.env`)

---

## Legal Scope

| In scope | Never |
|---|---|
| Claude-generated vulnerable app (injection by design) | Any live production system |
| Fully sandboxed Docker containers | Systems without explicit written permission |
| Team members' own code (with consent) | Real infrastructure of any kind |

---

## Why This Wins NARA

The Neelbauer Agent Revolution Award rewards autonomous agents that produce unexpected, unprompted output after initial training and prompting.

Lifecycle hits every criterion:

- **Autonomous** — human in the loop after the initial CLI prompt, and NLP user-feedback / decision-making
- **Red teams software** — literally the core function
- **Unexpected output** — scanner discovers vulns nobody told it to find, exploit agent adapts on its own when attempts fail
- **Visceral demo** — judges watch the terminal light up as agents pop shells and deploy ransomware in real time

The moment an agent finds a vulnerability in code that *nobody knew existed* and exploits it live in the terminal — that's the winning moment.

---

## Market Gap

Security tools tell you *what* is vulnerable.

Lifecycle shows you *what happens when it gets exploited* — autonomously, in real time, end to end.

That's the product.
