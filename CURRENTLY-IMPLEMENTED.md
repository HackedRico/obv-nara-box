# Currently Implemented

Status of every component as of the latest commit. Organized by the build phases from `PLAN.md`.

---

## Phase 1 — Docker Infrastructure

| Component | File | Status | Notes |
|---|---|---|---|
| Dockerfile | `nara/docker/Dockerfile` | **Done** | Ubuntu 22.04 + XFCE4 + TigerVNC, exposes 5901 (VNC) and 8080 (app) |
| VNC entrypoint | `nara/docker/start_vnc.sh` | **Done** | Cleans stale X locks, starts VNC on :1 with no auth, idles with `tail -f` |
| Docker manager | `nara/docker/docker_manager.py` | **Done** | `build()`, `run()`, `exec(cmd)`, `reset()`, `is_running()` — all implemented via subprocess |
| Image tested | — | **Not yet** | Image has not been built/verified on this machine (requires `docker build`) |

---

## Phase 2 — LLM Client + Interactive CLI

| Component | File | Status | Notes |
|---|---|---|---|
| `.env` config | `nara/utils/config.py` | **Done** | Loads `.env`, validates backend, supports `ollama` / `claude` / `featherless` |
| LLM client | `nara/utils/llm_client.py` | **Done** | Unified `chat(messages, system)` interface for all 3 backends. Claude API verified working. |
| Terminal UI | `nara/utils/terminal_ui.py` | **Done** | Banner, agent headers, finding panels, kill chain table, spinner, stream output — all Rich-based |
| CLI REPL | `nara/cli.py` | **Done** | `prompt_toolkit` REPL with session state, Ctrl+C handling, styled prompt |
| Orchestrator | `nara/orchestrator.py` | **Done** | Keyword intent classifier routes to agents or LLM chat fallback. Docker init/reset wired in. |
| `setup.py` | `setup.py` | **Done** | `pip install -e .` registers the `nara` console command |
| Python venv | `.venv/` | **Done** | Python 3.14, all deps installed including semgrep and bandit |

---

## Phase 3 — Agents + Ransomware

| Component | File | Status | Notes |
|---|---|---|---|
| Scanner agent | `nara/agents/scanner.py` | **Done** | Runs Semgrep + Bandit via subprocess, LLM triages combined output into structured JSON findings. Bandit fallback parser if LLM fails. |
| Planner agent | `nara/agents/planner.py` | **Done** | LLM designs kill chain from findings. Always appends ransomware as final step. Hardcoded fallback chain targeting command injection. |
| Exploiter agent | `nara/agents/exploiter.py` | **Done** | Provisions container, executes kill chain step-by-step. LLM assesses each step (continue/retry/adapt/abort). Falls back to DRY RUN mode if Docker unavailable. |
| Ransomware payload | `nara/payloads/ransomware.py` | **Done** | Stdlib-only Python. Drops ransom note, fake-encrypts dummy files (.NARA_ENCRYPTED), generates dark-red PNG wallpaper, sets it via xfconf-query/feh. |
| Ransom assets | `nara/payloads/assets/` | **Partial** | `ransom_note_template.txt` and `wallpaper.png` present. Payload generates its own wallpaper at runtime so the static asset is optional. |
| Vuln app repo URL | `exploiter.py:21` | **Placeholder** | `VULN_APP_REPO` is set to `https://github.com/PLACEHOLDER/pokedex-vuln` — needs Person 2's actual repo URL |

---

## Phase 4 — Polish + Demo Prep

| Component | Status | Notes |
|---|---|---|
| Claude API backend | **Done** | Verified working — scanner triage, planner kill chains, exploiter assessment all return valid JSON |
| Full pipeline test | **Not yet** | Have not run `scan → plan → exploit` end-to-end against a live container with the vuln app |
| Docker image build | **Not yet** | Dockerfile written but not built/tested |
| VNC desktop verified | **Not yet** | Depends on Docker image build |
| Demo rehearsal | **Not yet** | — |

---

## Integration Gaps

These are the remaining items needed for a working end-to-end demo:

1. **Build and test the Docker image** — run `docker build -t nara-target ./nara/docker/` and verify VNC is accessible on :5901
2. **Set `VULN_APP_REPO`** in `nara/agents/exploiter.py:21` to Person 2's actual vulnerable Flask app repo URL
3. **End-to-end pipeline test** — `nara > init > scan > plan > exploit` against the live container
4. **Ransomware VNC verification** — confirm wallpaper change and ransom note are visible through VNC client

---

## What's Verified Working (tested in current session)

- All Python imports across every module
- LLM client → Claude API (chat, scanner triage, planner kill chain, exploiter assessment)
- Intent classification — all 16 keyword patterns route correctly
- Orchestrator routing — help, status, plan-without-findings, exploit-without-chain, exit, chat fallback
- Terminal UI — banner, all 4 agent headers, finding panels, kill chain table, spinner, stream output
- Ransomware payload — ransom note drop, dummy file encryption, wallpaper PNG generation
- DockerManager — `is_running()` returns False gracefully when no container exists
- Exploiter DRY RUN mode — prints commands without crashing when Docker container isn't running
