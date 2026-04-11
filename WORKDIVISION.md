# NARA — Work Division (4 People, ~36 Hours)

Bitcamp 2025 | April 11–13 | Goal: working demo by Sunday 9:30 AM

---

## Person 1 — Docker & Container Infrastructure

**Own:** Everything the target environment runs on.

### Tasks
- [ ] `nara/docker/Dockerfile` — Ubuntu 22.04 + XFCE4 + TigerVNC, expose ports 5901 (VNC) and 8080 (app)
- [ ] `nara/docker/start_vnc.sh` — entrypoint that boots XFCE desktop + VNC server on container start
- [ ] `nara/docker/docker_manager.py` — Python wrapper for container lifecycle:
  - `build()` — build the image
  - `run()` — start the container
  - `exec(cmd)` — run a shell command inside container, capture + stream stdout/stderr
  - `reset()` — stop + remove + fresh run
  - `is_running()` — health check
- [ ] Verify: `docker build`, `docker run`, VNC accessible at `:5901`, `docker exec` works

### Handoff to team
- `docker_manager.py` must be importable by the Exploiter agent
- `exec(cmd)` is the critical method — Exploiter calls it constantly
- Document what the container has baked in vs. what Exploiter installs at runtime

---

## Person 2 — Vulnerable Flask App (Separate Repo)

**Own:** The target that gets scanned and exploited. Lives in a **separate public GitHub repo**.

### Tasks
- [ ] Create a new public repo (e.g., `github.com/<user>/pokedex-vuln`)
- [ ] Pokemon-themed Flask REST API with these deliberate vulnerabilities:

| Endpoint | Vulnerability |
|---|---|
| `GET /api/pokemon?name=<input>` | **Command injection** — `os.system(f"grep {name} pokedex.csv")` |
| `POST /api/team` | SQL injection — raw string concat into SQLite query |
| `GET /api/pokedex?search=<input>` | Reflected XSS — search term rendered back unsanitized |
| `POST /api/upload-sprite` | Unrestricted file upload — no extension/MIME validation |
| `GET /api/stats?pokemon=<input>` | SSRF — user controls the URL being fetched |

- [ ] `pokedex.csv` + `pokedex.db` (SQLite) — minimal Pokemon data for the endpoints to use
- [ ] Pokemon-themed HTML/CSS/JS frontend — looks like a legit Pokedex app (not obviously a security demo)
- [ ] `requirements.txt` for the Flask app
- [ ] Verify: `flask run --port 8080` works, all 5 endpoints respond, command injection fires with `?name=pikachu;whoami`

### Handoff to team
- Share the repo URL — Exploiter agent will `git clone` it inside the container at runtime
- The command injection endpoint is the primary exploit path for the demo
- Make sure it runs cleanly with `pip install -r requirements.txt && flask run --port 8080`

---

## Person 3 — LLM Client, CLI Shell & Orchestrator

**Own:** The `nara` command, the interactive REPL, and the wiring between everything.

### Tasks
- [ ] `.env.example` — template with `LLM_BACKEND`, `OLLAMA_MODEL`, `ANTHROPIC_API_KEY`
- [ ] `nara/utils/config.py` — loads `.env`, exposes config values
- [ ] `nara/utils/llm_client.py` — unified LLM interface:
  - `chat(messages, system_prompt)` → response string
  - Ollama backend: calls local Qwen2.5 via `ollama` Python package
  - Claude backend: calls `anthropic` SDK
  - Switched via `LLM_BACKEND` env var — no code changes to switch
- [ ] `nara/utils/terminal_ui.py` — Rich-based output helpers:
  - Agent banners (`[SCANNER]`, `[PLANNER]`, `[EXPLOITER]`, `[RANSOMWARE]`)
  - Streaming text output
  - Status spinners, colored panels
- [ ] `nara/cli.py` — interactive REPL entry point:
  - `prompt_toolkit` for the `nara > ` prompt
  - Maintains session state (findings, kill chain, container status)
  - Passes user input to `orchestrator.py`
- [ ] `nara/orchestrator.py` — routes NLP intent to the right agent:
  - "scan", "init", "exploit", "reset", "what did you find" → dispatches to the right agent
  - Maintains context across turns (stateful session)
- [ ] `setup.py` — makes `nara` a CLI command (`pip install -e .`)
- [ ] Verify: `nara` starts, prints the banner, responds to chat, intent routing works without full agents

### Handoff to team
- `llm_client.py` is shared by all three agents — get this done first
- `terminal_ui.py` helpers should be usable by all agents for consistent output
- `orchestrator.py` calls agents — agree on function signatures with Persons 1 and 4 early

---

## Person 4 — Agents (Scanner, Planner, Exploiter) & Ransomware Payload

**Own:** The three AI agents and the ransomware simulation. This is the core intelligence of NARA.

### Dependencies
- Needs `llm_client.py` from Person 3 (get a stub early if needed)
- Needs `docker_manager.exec()` from Person 1 for the Exploiter
- Needs the vuln app repo URL from Person 2

### Tasks

**Scanner (`nara/agents/scanner.py`)**
- [ ] Run Semgrep against a given directory path, capture output
- [ ] Run Bandit against Python files, capture output
- [ ] Combine raw tool outputs, pass to LLM with a system prompt to deduplicate and prioritize
- [ ] Output: structured list of findings (vuln type, file, line, severity, exploitability notes)

**Planner (`nara/agents/planner.py`)**
- [ ] Takes Scanner findings as input
- [ ] LLM system prompt: "You are a red team kill chain architect. Design an ordered attack sequence. Always include ransomware deployment as the final stage."
- [ ] Output: kill chain as ordered steps with commands and expected outcomes

**Exploiter (`nara/agents/exploiter.py`)**
- [ ] Receives kill chain from Planner
- [ ] Container provisioning sequence (via `docker_manager.exec()`):
  1. `apt-get install` required tools
  2. `git clone <vuln-app-repo>`
  3. `pip install -r requirements.txt`
  4. Start Flask app on port 8080
  5. Confirm app is reachable
- [ ] Execute each kill chain step via `docker_manager.exec()`, stream output to terminal
- [ ] On step failure: LLM adapts (retry, adjust payload, alternate approach)
- [ ] Ask user for ransomware customization (image/text) via the CLI before final step
- [ ] Deploy ransomware payload as final step

**Ransomware payload (`nara/payloads/`)**
- [ ] `ransomware.py` — scripts to deploy via `docker exec`:
  - Change XFCE desktop wallpaper to a ransom image
  - Drop `README_RANSOM.txt` on the desktop
  - Optionally rename desktop icons
- [ ] `assets/` — default ransom wallpaper image + note template
- [ ] The payload should be injectable as a shell command or script via `docker exec`

---

## Integration Checkpoints

| Time | Milestone |
|---|---|
| ~Hour 6 | P1: Container running + VNC accessible. P2: Flask app runs locally. P3: `nara` REPL starts + `llm_client.py` done |
| ~Hour 12 | P1+P2 integration: Exploiter can provision container and start Flask app. P3+P4: Scanner returns findings from a test codebase |
| ~Hour 20 | Full pipeline: scan → plan → exploit → output visible in terminal |
| ~Hour 28 | Ransomware deploys, VNC shows desktop effects. Full chain clean. |
| ~Hour 33 | Polish, switch to Claude API, demo rehearsal |

---

## Shared Interfaces (agree on these early)

```python
# docker_manager.py (Person 1)
manager.exec(cmd: str) -> str        # run cmd in container, return output
manager.run() -> None                # start container
manager.reset() -> None              # fresh container

# llm_client.py (Person 3)
llm.chat(messages: list, system: str) -> str

# scanner.py output (Person 4 → Planner)
findings: list[dict]  # [{type, file, line, severity, description}]

# planner.py output (Person 4 → Exploiter)
kill_chain: list[dict]  # [{step, command, expected_outcome}]
```
