#!/usr/bin/env python3
"""DQG runner - works from any directory on any OS.

Uses only stdlib. Called by the /dqg opencode command.

Subcommands:
  auto-review       Full auto: start services, run review async, poll, print results
  launch            Launch review as detached background process
  launch-from-jira  Launch from-jira review async (returns immediately)
  poll              Poll for review results
  start             Start a detached review process (legacy)
  from-jira         Generate document from Jira task and run DQG review (blocking)
  status            Check if the latest review is complete
  report            Print the latest report
  check-proxy       Check if LiteLLM proxy is running
  locate            Print the DQG project root path
"""

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

DQG_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = DQG_ROOT / "src"
RUNS_DIR = DQG_ROOT / "outputs" / "runs"
_MARKER_FILE = DQG_ROOT / "outputs" / ".active_review"
_ENV_FILE = DQG_ROOT / ".env"


def _load_env():
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _venv_python():
    if os.name == "nt":
        return DQG_ROOT / ".venv" / "Scripts" / "python.exe"
    return DQG_ROOT / ".venv" / "bin" / "python"


def _check_url(url):
    try:
        return urlopen(url, timeout=3).status == 200
    except Exception:
        return False


def _check_proxy():
    return _check_url("http://localhost:4000/health/liveliness")


def _check_web():
    return _check_url("http://localhost:8080/api/status")


def _latest_run_dir():
    if not RUNS_DIR.exists():
        return None
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def _read_marker():
    if not _MARKER_FILE.exists():
        return {}
    result = {}
    for line in _MARKER_FILE.read_text(encoding="utf-8").strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _write_marker(**kwargs):
    _MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MARKER_FILE.write_text("\n".join(f"{k}={v}" for k, v in kwargs.items()), encoding="utf-8")


def _clear_marker():
    if _MARKER_FILE.exists():
        _MARKER_FILE.unlink()


def _find_run_id_in_log(log_path):
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(r"run_id=(\S+)", text)
    return m.group(1) if m else None


def _wait_for(check_fn, label, max_attempts=30, interval=2.0):
    for i in range(max_attempts):
        if check_fn():
            print(f"{label}_READY")
            return True
        time.sleep(interval)
    print(f"{label}_TIMEOUT")
    return False


def _api_post(url, data, timeout=10):
    try:
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        r = urlopen(req, timeout=timeout)
        return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _api_get(url, timeout=10):
    try:
        r = urlopen(url, timeout=timeout)
        return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _nt_startup():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si


def _nt_flags():
    return subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS


def _start_proxy():
    _load_env()
    litellm_config = DQG_ROOT / "config" / "litellm" / "config.yaml"
    if not litellm_config.exists():
        litellm_config = DQG_ROOT / "config" / "litellm_config.yaml"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if os.name == "nt":
        venv_py = str(_venv_python())
        subprocess.Popen(
            [venv_py, "-c",
             "from litellm.proxy.proxy_cli import run_server; "
             "run_server(args=['--config', r'" + str(litellm_config) + "', '--port', '4000'])"],
            cwd=str(DQG_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=_nt_startup(),
            creationflags=_nt_flags(),
        )
    else:
        venv_py = str(_venv_python())
        subprocess.Popen(
            [venv_py, "-m", "litellm", "--config", str(litellm_config), "--port", "4000"],
            cwd=str(DQG_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _kill_proxy():
    try:
        if os.name == "nt":
            subprocess.run(
                ["powershell", "-Command",
                 "Get-NetTCPConnection -LocalPort 4000 -ErrorAction SilentlyContinue | "
                 "Select-Object -ExpandProperty OwningProcess | "
                 "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
            )
        else:
            subprocess.run(["pkill", "-f", "litellm.*--port 4000"], capture_output=True, timeout=10)
    except Exception:
        pass


def _kill_web_server():
    try:
        if os.name == "nt":
            subprocess.run(
                ["powershell", "-Command",
                 "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | "
                 "Select-Object -ExpandProperty OwningProcess | "
                 "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
                capture_output=True, timeout=10,
            )
        else:
            subprocess.run(["pkill", "-f", "app.cli web.*8080"], capture_output=True, timeout=10)
    except Exception:
        pass


def _start_web_server():
    _load_env()
    venv_py = str(_venv_python())
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    log_dir = DQG_ROOT / "outputs"
    log_dir.mkdir(parents=True, exist_ok=True)
    web_log = open(str(log_dir / "web_server.log"), "w", encoding="utf-8")
    if os.name == "nt":
        subprocess.Popen(
            [str(venv_py), "-c",
             "import sys,uvicorn; "
             "sys.path.insert(0,r'" + str(SRC_DIR).replace("'", "\\'") + "'); "
             "from app.config import load_app_config; "
             "from app.utils.logging import setup_logging as _sl; "
             "_cfg=load_app_config(); _sl('INFO',enable_websocket=True,log_dir=_cfg.log_dir); "
             "uvicorn.run('app.web.app:app',host='0.0.0.0',port=8080,log_level='info')"],
            cwd=str(DQG_ROOT),
            env=env,
            stdout=web_log,
            stderr=web_log,
            startupinfo=_nt_startup(),
            creationflags=_nt_flags(),
        )
    else:
        subprocess.Popen(
            [venv_py, "-c",
             "import sys,uvicorn; "
             "sys.path.insert(0,'" + str(SRC_DIR) + "'); "
             "from app.config import load_app_config; "
             "from app.utils.logging import setup_logging as _sl; "
             "_cfg=load_app_config(); _sl('INFO',enable_websocket=True,log_dir=_cfg.log_dir); "
             "uvicorn.run('app.web.app:app',host='0.0.0.0',port=8080,log_level='info')"],
            cwd=str(DQG_ROOT),
            env=env,
            stdout=web_log,
            stderr=web_log,
            start_new_session=True,
        )


def cmd_auto_review(args):
    launch_args = argparse.Namespace(
        doc_path=args.doc_path,
        project=args.project,
        type=args.type,
        context_path=getattr(args, "context_path", None),
    )
    review_id = None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            cmd_launch(launch_args)
        except SystemExit:
            pass
    output = buf.getvalue()
    print(output, end="")
    for line in output.splitlines():
        if line.startswith("REVIEW_STARTED"):
            m = re.search(r"review_id=(\S+)", line)
            if m:
                review_id = m.group(1)
    if not review_id:
        sys.exit(1)

    poll_args = argparse.Namespace(
        review_id=review_id,
        max_attempts=120,
    )
    cmd_poll(poll_args)


def cmd_from_jira(args):
    task_key = args.task_key
    context_path = getattr(args, "context_path", None)
    project_path = getattr(args, "project", None)
    generate_only = getattr(args, "generate_only", False)

    if not context_path:
        from dotenv import dotenv_values

        env_vals = dotenv_values(str(_ENV_FILE))
        context_path = env_vals.get("DQG_JIRA_DEFAULT_CONTEXT_PATH")

    if project_path:
        project_path = str(Path(project_path).resolve())
    elif context_path:
        project_path = str(Path.cwd().resolve())
    if context_path:
        context_path = str(Path(context_path).resolve())

    payload = {"task_key": task_key}
    if context_path:
        payload["context_path"] = context_path
    if project_path:
        payload["project_path"] = project_path
    if generate_only:
        payload["generate_only"] = True

    result = _api_post("http://localhost:8080/api/review/from-jira", payload, timeout=15)
    if not result or "error" in result:
        print(f"FATAL: Could not start from-jira review: {result}")
        sys.exit(1)

    review_id = result.get("review_id")
    print(f"REVIEW_ID: {review_id}")

    poll_args = argparse.Namespace(review_id=review_id, max_attempts=200)
    cmd_poll(poll_args)


def cmd_launch_from_jira(args):
    task_key = args.task_key
    context_path = getattr(args, "context_path", None)
    project_path = getattr(args, "project", None)
    generate_only = getattr(args, "generate_only", False)

    if not context_path:
        from dotenv import dotenv_values

        env_vals = dotenv_values(str(_ENV_FILE))
        context_path = env_vals.get("DQG_JIRA_DEFAULT_CONTEXT_PATH")

    if project_path:
        project_path = str(Path(project_path).resolve())
    elif context_path:
        project_path = str(Path.cwd().resolve())
    if context_path:
        context_path = str(Path(context_path).resolve())

    print(f"JIRA_TASK: {task_key}")
    if context_path:
        print(f"CONTEXT_PATH: {context_path}")
    if project_path:
        print(f"PROJECT_PATH: {project_path}")

    payload = {"task_key": task_key}
    if context_path:
        payload["context_path"] = context_path
    if project_path:
        payload["project_path"] = project_path
    if generate_only:
        payload["generate_only"] = True

    result = _api_post("http://localhost:8080/api/review/from-jira", payload, timeout=15)
    if not result or "error" in result:
        print(f"FATAL: Could not start from-jira review: {result}")
        sys.exit(1)

    review_id = result.get("review_id")
    print(f"REVIEW_STARTED review_id={review_id}")
    print(f"Use: python {__file__} poll {review_id}")


_SERVICE_COMMANDS = {"launch", "launch-from-jira", "auto-review", "from-jira", "review", "start"}


def _ensure_services():
    proxy_up = _check_proxy()
    web_up = _check_web()

    if proxy_up and web_up:
        print("Services already running (proxy + web).")
        return

    if web_up:
        print("Cancelling active pipeline (if any)...")
        _api_post("http://localhost:8080/api/pipeline/cancel", {}, timeout=5)
        time.sleep(1)

    if not proxy_up:
        print("Starting LiteLLM proxy...")
        _start_proxy()
        if not _wait_for(_check_proxy, "PROXY", max_attempts=30, interval=2.0):
            print("FATAL: LiteLLM proxy could not start. Check .env for ZAI_API_KEY.")
            sys.exit(1)

    if not web_up:
        print("Starting DQG web server...")
        _start_web_server()
        if not _wait_for(_check_web, "WEB", max_attempts=15, interval=2.0):
            print("FATAL: DQG web server could not start.")
            sys.exit(1)

        import webbrowser
        webbrowser.open("http://localhost:8080")
        print("WEB_UI_OPENED http://localhost:8080")


def cmd_launch(args):
    venv_py = _venv_python()
    if not venv_py.exists():
        print(f"ERROR: Virtual environment not found at {venv_py}")
        print("Run the setup script first to create the venv.")
        sys.exit(1)

    doc_path = str(Path(args.doc_path).resolve())
    doc_type = args.type
    context_path = getattr(args, "context_path", None)
    if context_path:
        context_path = str(Path(context_path).resolve())

    if args.project:
        project_path = str(Path(args.project).resolve())
    elif context_path:
        project_path = str(Path.cwd().resolve())
    else:
        project_path = None

    print(f"DOC_PATH: {doc_path}")
    if project_path:
        print(f"PROJECT_PATH: {project_path}")
    if context_path:
        print(f"CONTEXT_PATH: {context_path}")

    payload = {"file_path": doc_path, "project_path": project_path or "."}
    if doc_type:
        payload["doc_type"] = doc_type
    if context_path:
        payload["context_path"] = context_path

    result = _api_post("http://localhost:8080/api/review/start", payload, timeout=10)
    if not result or "error" in result:
        print(f"FATAL: Could not start review: {result}")
        sys.exit(1)

    review_id = result.get("review_id")
    if not review_id:
        print(f"FATAL: No review_id in response: {result}")
        sys.exit(1)

    print(f"REVIEW_STARTED review_id={review_id}")
    print(f"Use: python {__file__} poll {review_id}")


def cmd_poll(args):
    review_id = args.review_id
    max_attempts = args.max_attempts

    status = "unknown"
    for attempt in range(max_attempts):
        status_data = _api_get(f"http://localhost:8080/api/review/status/{review_id}", timeout=10)
        if not status_data or status_data.get("error"):
            print(f"POLL_RETRY attempt={attempt + 1}/{max_attempts}")
            time.sleep(10)
            continue

        status = status_data.get("status", "unknown")
        if status == "complete":
            print("REVIEW_COMPLETE")
            rr = status_data.get("result", {})
            score = rr.get("overall_score", "?")
            passed = rr.get("passed", "?")
            action = rr.get("recommended_next_action", "?")
            print(f"SCORE: {score}/10 | {'PASS' if passed else 'FAIL'} | Action: {action}")

            for key, label in [("cross_ref_issues", "CROSS_REF_ISSUES"), ("quality_issues", "QUALITY_ISSUES")]:
                items = rr.get(key, [])
                if items:
                    print(f"\n{label} ({len(items)}):")
                    for item in items[:10]:
                        print(f"  - [{item.get('severity', '?')}] {item.get('description', str(item))}")

            dims = rr.get("dimension_scores", {})
            if dims:
                print(f"\nDIMENSION_SCORES:")
                for dim, val in dims.items():
                    print(f"  {dim}: {val}")

            print(f"\nREVIEW_ID: {review_id}")
            return

        if status == "failed":
            print(f"REVIEW_FAILED: {status_data.get('error', 'unknown error')}")
            sys.exit(1)

        print(f"STATUS: {status} (attempt {attempt + 1}/{max_attempts})")
        time.sleep(10)

    print(f"POLL_INCOMPLETE status={status} - run again with same command to continue polling")


def cmd_start(args):
    venv_py = _venv_python()
    if not venv_py.exists():
        print(f"ERROR: Virtual environment not found at {venv_py}")
        sys.exit(1)
    if not _check_proxy():
        print("ERROR: LiteLLM proxy is not running at http://localhost:4000")
        sys.exit(1)

    doc_path = str(Path(args.doc_path).resolve())
    project_path = str(Path(args.project).resolve())
    cmd = [str(venv_py), "-m", "app.cli", "review", doc_path, "--project", project_path]
    if args.type:
        cmd.extend(["-t", args.type])
    context_path = getattr(args, "context_path", None)
    if context_path:
        cmd.extend(["--cp", str(Path(context_path).resolve())])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    log_path = DQG_ROOT / "outputs" / "review.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = {
        "cwd": str(DQG_ROOT),
        "env": env,
        "stdout": open(str(log_path), "w", encoding="utf-8"),
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    _write_marker(
        pid=str(proc.pid),
        doc_path=doc_path,
        project_path=project_path,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="RUNNING",
    )
    time.sleep(2)

    if proc.poll() is not None:
        _write_marker(
            pid=str(proc.pid),
            doc_path=doc_path,
            project_path=project_path,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            status="FAILED",
        )
        print(f"ERROR: Review process exited immediately with code {proc.returncode}")
        sys.exit(1)

    print("REVIEW_STARTED")
    print(f"PID: {proc.pid}")
    run_id = _find_run_id_in_log(log_path)
    if run_id:
        print(f"Run ID: {run_id}")


def cmd_status(args):
    marker = _read_marker()
    if not marker:
        print("NO_ACTIVE_REVIEW")
        return

    pid = int(marker.get("pid", 0))
    alive = False
    if pid:
        try:
            if os.name == "nt":
                proc = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=5
                )
                alive = str(pid) in proc.stdout
            else:
                os.kill(pid, 0)
                alive = True
        except Exception:
            alive = False

    run_dir = _latest_run_dir()
    has_results = (
        run_dir and (run_dir / "scorecard.json").exists() and (run_dir / "report.md").exists() if run_dir else False
    )

    if has_results:
        _clear_marker()
        print("COMPLETE")
        print(f"Run: {run_dir.name}")
        try:
            data = json.loads((run_dir / "scorecard.json").read_text(encoding="utf-8"))
            print(f"Score: {data.get('overall_score', '?')}/10 | {'PASS' if data.get('passed') else 'FAIL'}")
        except Exception:
            pass
    elif not alive:
        _clear_marker()
        print("FAILED")
    else:
        print("RUNNING")
        print(f"PID: {pid}")


def cmd_review(args):
    venv_py = _venv_python()
    doc_path = str(Path(args.doc_path).resolve())
    project_path = str(Path(args.project).resolve())
    cmd = [str(venv_py), "-m", "app.cli", "review", doc_path, "--project", project_path]
    if args.type:
        cmd.extend(["-t", args.type])
    context_path = getattr(args, "context_path", None)
    if context_path:
        cmd.extend(["--cp", str(Path(context_path).resolve())])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    result = subprocess.run(cmd, cwd=str(DQG_ROOT), env=env)
    sys.exit(result.returncode)


def cmd_report(args):
    run_dir = _latest_run_dir()
    if not run_dir or not (run_dir / "report.md").exists():
        print("No report found.")
        sys.exit(1)
    print((run_dir / "report.md").read_text(encoding="utf-8"))


def cmd_locate(args):
    print(DQG_ROOT)


def cmd_rescore(args):
    previous_review_id = args.review_id
    revised_file_path = getattr(args, "revised_file_path", None)

    payload = {"previous_review_id": previous_review_id}
    if revised_file_path:
        payload["revised_file_path"] = str(Path(revised_file_path).resolve())

    result = _api_post("http://localhost:8080/api/review/rescore", payload, timeout=10)
    if not result or "error" in result:
        print(f"FATAL: Could not start rescore: {result}")
        sys.exit(1)

    new_review_id = result.get("review_id")
    print(f"RESCORE_STARTED review_id={new_review_id} from={previous_review_id}")
    print(f"Use: python {__file__} poll {new_review_id}")


def cmd_check_proxy(args):
    print("PROXY_OK" if _check_proxy() else "PROXY_DOWN")


def main():
    parser = argparse.ArgumentParser(description="DQG Runner")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("launch", help="Start services + launch async review (returns immediately)")
    p.add_argument("doc_path")
    p.add_argument("--project", "-p", default=None)
    p.add_argument("--type", "-t", default=None)
    p.add_argument("--cp", dest="context_path", default=None, help="Path to domain context directory")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("poll", help="Poll for review results")
    p.add_argument("review_id")
    p.add_argument("--max-attempts", "-n", type=int, default=6, help="Max poll attempts (default 6, ~1 min)")
    p.set_defaults(func=cmd_poll)

    p = sub.add_parser("auto-review", help="Launch + poll in one command (may timeout)")
    p.add_argument("doc_path")
    p.add_argument("--project", "-p", default=None)
    p.add_argument("--type", "-t", default=None)
    p.add_argument("--cp", dest="context_path", default=None, help="Path to domain context directory")
    p.set_defaults(func=cmd_auto_review)

    p = sub.add_parser("start")
    p.add_argument("doc_path")
    p.add_argument("--project", "-p", required=True)
    p.add_argument("--type", "-t", default=None)
    p.add_argument("--cp", dest="context_path", default=None, help="Path to domain context directory")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("review")
    p.add_argument("doc_path")
    p.add_argument("--project", "-p", required=True)
    p.add_argument("--type", "-t", default=None)
    p.add_argument("--cp", dest="context_path", default=None, help="Path to domain context directory")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("report")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("locate")
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("check-proxy")
    p.set_defaults(func=cmd_check_proxy)

    p = sub.add_parser("from-jira", help="Generate document from Jira task and run DQG review (blocking)")
    p.add_argument("task_key", help="Jira task key (e.g. PDB-11139)")
    p.add_argument("--cp", dest="context_path", default=None, help="Path to domain context directory")
    p.add_argument("--project", "-p", default=None, help="Path to target project for cross-reference")
    p.add_argument("--generate-only", action="store_true", help="Generate document only, skip DQG review")
    p.set_defaults(func=cmd_from_jira)

    p = sub.add_parser("launch-from-jira", help="Launch from-jira review async (returns immediately)")
    p.add_argument("task_key", help="Jira task key (e.g. PDB-11139)")
    p.add_argument("--cp", dest="context_path", default=None, help="Path to domain context directory")
    p.add_argument("--project", "-p", default=None, help="Path to target project for cross-reference")
    p.add_argument("--generate-only", action="store_true", help="Generate document only, skip DQG review")
    p.set_defaults(func=cmd_launch_from_jira)

    p = sub.add_parser("rescore", help="Rescore previous review (fast: only score + meta_judge)")
    p.add_argument("review_id", help="Previous review ID to rescore")
    p.add_argument("--revised", dest="revised_file_path", default=None, help="Path to revised document (default: uses previous revised.md)")
    p.set_defaults(func=cmd_rescore)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    _load_env()

    if args.command in _SERVICE_COMMANDS:
        _ensure_services()

    args.func(args)


if __name__ == "__main__":
    main()
