# DQG Ensure - Auto-Install + Self-Healing

This document describes how to ensure DQG is installed, configured, and running before the pipeline starts.

## Configuration

Read from AGENTS.md `## Pipeline Config` section:
- `dqg_path`: Local path where DQG is/will be installed
- `dqg_repo`: Git repository URL to clone from

**Defaults:**
- `dqg_path`: `C:\repos\doc-quailty-gate` (Windows) or `~/doc-quality-gate` (Linux/macOS)
- `dqg_repo`: `https://github.com/ekintkara/doc-quailty-gate.git`

## Check Flow

Run these checks in order. If any fails, fix it before proceeding.

### Check 0: Git Installed

```
Test: git --version

If NOT FOUND:
  1. Ask user: "Git gerekli. Kurduktan sonra pipeline'i tekrar baslatin."
  2. STOP pipeline
```

### Check 1: Directory Exists

```
Test: Does {dqg_path} directory exist?

If NO:
  1. Run: git clone {dqg_repo} {dqg_path}
  2. If clone fails:
     a. Check network: ping github.com
     b. If network issue → ask user to check connection
     c. If repo not found → check dqg_repo URL, ask user
     d. If auth error → repo public olmali, kontrol et
  3. If clone succeeds → continue to Check 2
```

### Check 2: Python Available

```
Test: python --version (or python3 --version on Linux/macOS)

Required: Python 3.11+ (pyproject.toml: requires-python = ">=3.11")

If NOT FOUND or VERSION TOO OLD:
  1. Ask user: "Python 3.11+ gerekli. Kurduktan sonra pipeline'i tekrar baslatin."
  2. STOP pipeline
```

### Check 3: Virtual Environment + Dependencies

```
Test: Does {dqg_path}/.venv exist?

If NO:
  Windows:
    cd {dqg_path}
    python -m venv .venv
    .venv\Scripts\pip install -e ".[dev]"
    .venv\Scripts\pip install "litellm[proxy]"

  Linux/macOS:
    cd {dqg_path}
    python3 -m venv .venv
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/pip install "litellm[proxy]"

  NOTE: DQG uses pyproject.toml (NOT requirements.txt).
        pip install -e ".[dev]" installs all deps including dev tools.
        litellm[proxy] is needed for the proxy server.

  If pip install fails:
    1. Try: pip install --no-cache-dir -e ".[dev]"
    2. Try: pip install --upgrade pip && pip install -e ".[dev]"
    3. Try: pip install --no-build-isolation orjson (common failure)
    4. If still fails → show error, ask user
```

### Check 4: Environment Configuration

```
Test: Does {dqg_path}/.env exist and contain ZAI_API_KEY?

If NO .env file:
  1. If .env.example exists → copy it
  2. Otherwise create empty .env
  3. Ask user: "DQG icin Z.AI API key gerekli.
     Key'i girin (https://z.ai dashboard'dan alabilirsiniz):"
  4. Write ZAI_API_KEY={user_input} to .env
  5. Also set LITELLM_MASTER_KEY to a random UUID if not set

If .env exists but ZAI_API_KEY is empty:
  1. Ask user for the key
  2. Update .env

If LITELLM_MASTER_KEY not set:
  1. Auto-generate UUID and add to .env

IMPORTANT: Never hardcode API keys. Always ask the user.
Never expose keys in output or logs.
```

### Check 5: LiteLLM Proxy

```
Test: curl http://localhost:4000/health/liveliness (or python httpx)

If PROXY_DOWN:
  1. Start proxy:
     Windows:
       Start-Process -FilePath "cmd" -ArgumentList "/c", "{dqg_path}\.venv\Scripts\activate && litellm --config {dqg_path}\config\litellm\config.yaml --port 4000" -WindowStyle Hidden

     Linux/macOS:
       nohup {dqg_path}/.venv/bin/litellm --config {dqg_path}/config/litellm/config.yaml --port 4000 &

  2. Wait up to 60 seconds for proxy to start (poll every 2 seconds)
  3. If still down after 60s:
     a. Check if port 4000 is occupied:
        Windows: Get-NetTCPConnection -LocalPort 4000
        Linux: lsof -i :4000
     b. Kill occupant if needed
     c. Retry
  4. If still fails → ask user: "LiteLLM proxy baslatilamadi: {error}"

NOTE: litellm.exe may be broken on Windows. If so, use Python wrapper:
  python -c "from litellm.proxy.proxy_cli import run_server; run_server(args=['--config', '{dqg_path}/config/litellm/config.yaml', '--port', '4000'])"
```

### Check 6: Web Dashboard (Optional)

```
Test: curl http://localhost:8080/api/status (or python httpx)

If WEB_DOWN:
  1. Start web server:
     Windows:
       Start-Process -FilePath "cmd" -ArgumentList "/c", "{dqg_path}\.venv\Scripts\activate && python -m app.cli web --port 8080" -WindowStyle Hidden

     Linux/macOS:
       nohup {dqg_path}/.venv/bin/python -m app.cli web --port 8080 &

  2. Wait up to 10 seconds
  3. Open browser: http://localhost:8080

NOTE: Web dashboard is optional. Pipeline works without it.
      But it provides real-time monitoring of DQG review progress.
```

### Check 7: Smoke Test

```
Test: Run python {dqg_path}/scripts/dqg_run.py check-proxy → PROXY_OK

If PASS → DQG READY, proceed with pipeline
If FAIL → go back to Check 5
```

## Quick Start Script

DQG repo includes a setup script for first-time installation:

**Windows:** `{dqg_path}\scripts\win\start.ps1`
**Linux/macOS:** `{dqg_path}\scripts/mac/start.sh`

These scripts handle all checks automatically. If running manually, they are the recommended way to set up DQG.

## Self-Healing Summary

| Problem | Fix |
|---------|-----|
| Git not found | Ask user to install |
| DQG not installed | `git clone` from `dqg_repo` |
| No venv | `python -m venv .venv && pip install -e ".[dev]"` |
| Missing deps | `pip install -e ".[dev]"` or `--no-cache-dir` |
| orjson build fails | `pip install orjson --no-build-isolation` |
| No .env | Create, ask user for API key |
| No ZAI_API_KEY | Ask user interactively |
| No LITELLM_MASTER_KEY | Auto-generate UUID |
| Proxy not running | Start via `litellm` or Python wrapper |
| litellm.exe broken | Use `python -c "from litellm.proxy.proxy_cli import run_server; ..."` |
| Port 4000 occupied | Kill occupant, restart |
| Web dashboard down | Start web server (optional) |
| Python not found | Ask user to install |
| Network error | Ask user to check connection |
| Clone auth error | Check repo URL, ask user |

## Important Notes

1. **API Keys:** NEVER hardcode, NEVER log, NEVER show in output. Always ask user.
2. **Platform:** Detect OS (Windows vs Linux/macOS) and use correct paths:
   - Windows: `.venv\Scripts\python.exe`, `.venv\Scripts\pip.exe`
   - Linux/macOS: `.venv/bin/python`, `.venv/bin/pip`
3. **Python version:** DQG requires Python 3.11+ (per pyproject.toml)
4. **Dependencies:** DQG uses `pyproject.toml`, NOT `requirements.txt`. Install with `pip install -e ".[dev]"`
5. **Idempotent:** All checks can be run multiple times safely.
6. **Partial state:** If DQG was partially installed (e.g., clone succeeded but pip failed), just continue from where it failed.
7. **User communication:** Always tell user what you're doing:
   "DQG kuruluyor..." / "DQG proxy baslatiliyor..." / "DQG hazir"
8. **Web dashboard:** Optional but recommended for monitoring review progress.
