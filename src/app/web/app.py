from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import uuid
from pathlib import Path

import structlog
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import load_app_config, load_model_routing
from app.orchestrator import Orchestrator, PipelineCancelledError
from app.utils.files import find_run_dir
from app.web.log_stream import LogBroadcaster

from app.simulator import (
    get_all_stages,
    get_comparison,
    get_profiles,
    simulate_pipeline,
)

logger = structlog.get_logger("web")

_async_reviews: dict[str, dict] = {}
_active_runs: dict[str, threading.Event] = {}

app = FastAPI(title="Doc Quality Gate", version="0.1.0")

_UPLOAD_DIR = Path(tempfile.gettempdir()) / "dqg_uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_static = Path(__file__).parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


def _get_orchestrator() -> Orchestrator:
    config = load_app_config()
    return Orchestrator(config)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _render_page("dashboard")


@app.get("/runs", response_class=HTMLResponse)
async def runs_page():
    return _render_page("runs")


@app.get("/smoke", response_class=HTMLResponse)
async def smoke_page():
    return _render_page("smoke")


@app.get("/simulator", response_class=HTMLResponse)
async def simulator_page():
    return _render_page("simulator")


@app.get("/api/simulator/stages")
async def api_simulator_stages():
    return {"stages": get_all_stages()}


@app.get("/api/simulator/profiles")
async def api_simulator_profiles():
    return {"profiles": get_profiles()}


@app.post("/api/simulator/calculate")
async def api_simulator_calculate(payload: dict):
    profile = payload.get("profile", "standard")
    early_exit = payload.get("early_exit", True)
    fan_out = payload.get("fan_out", True)
    pruning = payload.get("pruning", True)
    has_project = payload.get("has_project", True)
    return simulate_pipeline(profile, early_exit, fan_out, pruning, has_project)


@app.get("/api/simulator/comparison")
async def api_simulator_comparison():
    return get_comparison()


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_detail(run_id: str):
    return _render_page("run_detail", run_id=run_id)


@app.get("/api/runs")
async def api_list_runs():
    config = load_app_config()
    runs_dir = Path(config.output_base_dir)
    if not runs_dir.exists():
        return {"runs": []}

    runs = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        score_path = d / "scorecard.json"
        meta = {}
        score = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        if score_path.exists():
            try:
                score = json.loads(score_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        runs.append(
            {
                "run_id": d.name,
                "timestamp": meta.get("timestamp", ""),
                "document_type": meta.get("document_type", ""),
                "status": meta.get("execution_status", ""),
                "overall_score": score.get("overall_score"),
                "passed": score.get("passed"),
                "recommended_next_action": score.get("recommended_next_action", ""),
                "duration_ms": meta.get("duration_ms"),
            }
        )

    return {"runs": runs}


@app.get("/api/runs/{run_id}")
async def api_get_run(run_id: str):
    config = load_app_config()
    run_dir = find_run_dir(config.output_base_dir, run_id)
    if not run_dir:
        raise HTTPException(404, f"Run not found: {run_id}")

    result: dict = {"run_id": run_id}

    for name in ["metadata", "scorecard", "issues", "validations"]:
        p = run_dir / f"{name}.json"
        if p.exists():
            try:
                result[name] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                result[name] = None

    for name in ["original.md", "revised.md"]:
        p = run_dir / name
        if p.exists():
            result[name] = p.read_text(encoding="utf-8")

    return result


@app.get("/api/runs/{run_id}/report")
async def api_get_report(run_id: str):
    config = load_app_config()
    run_dir = find_run_dir(config.output_base_dir, run_id)
    if not run_dir:
        raise HTTPException(404, f"Run not found: {run_id}")

    html_path = run_dir / "report.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")

    md_path = run_dir / "report.md"
    if md_path.exists():
        return FileResponse(str(md_path), media_type="text/markdown")

    raise HTTPException(404, "Report not found")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return _dashboard_html()


@app.get("/api/runs/{run_id}/file/{filename}")
async def api_get_run_file(run_id: str, filename: str):
    from fastapi.responses import Response

    config = load_app_config()
    run_dir = find_run_dir(config.output_base_dir, run_id)
    if not run_dir:
        raise HTTPException(404, f"Run not found: {run_id}")
    p = run_dir / filename
    if not p.exists():
        raise HTTPException(404, f"File not found: {filename}")
    content = p.read_bytes()
    if filename.endswith(".json"):
        return Response(content=content, media_type="application/json; charset=utf-8")
    if filename.endswith(".md"):
        return Response(content=content, media_type="text/markdown; charset=utf-8")
    if filename.endswith(".html"):
        return Response(content=content, media_type="text/html; charset=utf-8")
    return Response(content=content, media_type="text/plain; charset=utf-8")


@app.get("/api/runs/{run_id}/files")
async def api_get_run_files(run_id: str):
    config = load_app_config()
    run_dir = find_run_dir(config.output_base_dir, run_id)
    if not run_dir:
        raise HTTPException(404, f"Run not found: {run_id}")
    tracked = [
        "task_analysis.json", "original.md", "domain_context.md",
        "domain_analysis.md", "codebase_context.md",
        "issues.json", "validations.json", "revised.md",
        "scorecard.json", "report.html", "report.md",
        "metadata.json", "fact_check.json", "fact_check.md",
    ]
    files = {}
    for name in tracked:
        p = run_dir / name
        if p.exists():
            files[name] = {"size": p.stat().st_size, "modified": p.stat().st_mtime}
    meta = {}
    mp = run_dir / "metadata.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"run_id": run_id, "files": files, "status": meta.get("execution_status", "unknown")}


@app.post("/api/events/ingest")
async def api_ingest_events(payload: dict):
    events = payload.get("events", [])
    if not events:
        return {"status": "ok", "count": 0}
    broadcaster = LogBroadcaster.get()
    for event in events:
        broadcaster.publish(event)
    return {"status": "ok", "count": len(events)}


@app.get("/api/events")
async def sse_events():
    broadcaster = LogBroadcaster.get()
    client_id, queue = broadcaster.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe(client_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/status")
async def api_status():
    broadcaster = LogBroadcaster.get()
    state = broadcaster.setup_state

    config = load_app_config()
    proxy_url = config.proxy_base_url

    proxy_ok = False
    try:
        import httpx

        async with httpx.AsyncClient() as c:
            r = await c.get(f"{proxy_url}/health/liveliness", timeout=3)
            proxy_ok = r.status_code == 200
    except Exception:
        pass

    return {
        "proxy": {"url": proxy_url, "healthy": proxy_ok},
        "setup": state,
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return _render_page("settings")


@app.get("/api/models")
async def api_get_models():
    config = load_app_config()
    routing = load_model_routing(config.config_dir)

    groups = {}
    for name, g in routing.model_groups.items():
        groups[name] = {
            "name": name,
            "provider": g.provider,
            "model": g.model,
            "description": g.description,
        }

    return {
        "groups": groups,
        "routing": config.model_aliases,
    }


@app.post("/api/models/routing")
async def api_update_routing(data: dict):
    new_routing = data.get("routing", {})
    if not new_routing:
        raise HTTPException(400, "routing field required")

    config = load_app_config()
    config_dir = Path(config.config_dir)
    app_yaml = config_dir / "app.yaml"

    if not app_yaml.exists():
        raise HTTPException(500, "app.yaml not found")

    with open(app_yaml) as f:
        raw = yaml.safe_load(f)

    raw["model_aliases"] = new_routing

    with open(app_yaml, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("model_routing_updated", new_routing=new_routing)
    return {"status": "ok", "routing": new_routing}


@app.post("/api/models/group/{group_name}")
async def api_update_model_group(group_name: str, data: dict):
    model_value = data.get("model", "")
    if not model_value:
        raise HTTPException(400, "model field required")

    config = load_app_config()
    config_dir = Path(config.config_dir)
    routing_yaml = config_dir / "model_routing.yaml"
    litellm_yaml = config_dir / "litellm" / "config.yaml"

    if routing_yaml.exists():
        with open(routing_yaml) as f:
            routing_raw = yaml.safe_load(f)
        if group_name in routing_raw.get("model_groups", {}):
            routing_raw["model_groups"][group_name]["model"] = model_value
            with open(routing_yaml, "w") as f:
                yaml.dump(routing_raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if litellm_yaml.exists():
        with open(litellm_yaml) as f:
            litellm_raw = yaml.safe_load(f)
        for entry in litellm_raw.get("model_list", []):
            if entry.get("model_name") == group_name:
                entry["litellm_params"]["model"] = model_value
        with open(litellm_yaml, "w") as f:
            yaml.dump(litellm_raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("model_group_updated", group=group_name, model=model_value)
    return {"status": "ok", "group": group_name, "model": model_value}


@app.get("/api/copilot/status")
async def api_copilot_status():
    config = load_app_config()
    proxy_url = config.proxy_base_url

    copilot_info = {
        "provider": "github_copilot",
        "model_group": "strong_judge",
        "configured": False,
        "authenticated": False,
        "model": "",
        "proxy_healthy": False,
        "error": None,
        "subscription": None,
    }

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            health_resp = await client.get(f"{proxy_url}/health/liveliness")
            copilot_info["proxy_healthy"] = health_resp.status_code == 200
    except Exception as e:
        copilot_info["error"] = f"Proxy unreachable: {e}"
        return copilot_info

    routing = load_model_routing(config.config_dir)
    judge_group = routing.model_groups.get("strong_judge")
    if judge_group:
        copilot_info["configured"] = True
        copilot_info["model"] = judge_group.model

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            test_payload = {
                "model": "strong_judge",
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 10,
                "temperature": 0.0,
            }
            headers = {"Content-Type": "application/json"}
            if config.proxy_api_key:
                headers["Authorization"] = f"Bearer {config.proxy_api_key}"

            test_resp = await client.post(
                f"{proxy_url}/chat/completions",
                json=test_payload,
                headers=headers,
            )
            if test_resp.status_code == 200:
                copilot_info["authenticated"] = True
                body = test_resp.json()
                usage = body.get("usage", {})
                copilot_info["subscription"] = {
                    "status": "active",
                    "model_responded": body.get("model", "unknown"),
                    "test_tokens": usage.get("total_tokens", 0),
                }
            else:
                err_detail = test_resp.text[:200]
                copilot_info["authenticated"] = False
                if "401" in str(test_resp.status_code):
                    copilot_info["error"] = (
                        "Authentication failed - run `litellm --config config/litellm/config.yaml` and complete OAuth flow"
                    )
                    copilot_info["subscription"] = {"status": "not_authenticated"}
                else:
                    copilot_info["error"] = f"HTTP {test_resp.status_code}: {err_detail}"
                    copilot_info["subscription"] = {"status": "error", "detail": err_detail}
    except Exception as e:
        copilot_info["authenticated"] = False
        copilot_info["error"] = f"Test request failed: {e}"
        copilot_info["subscription"] = {"status": "error", "detail": str(e)}

    return copilot_info


@app.post("/api/pipeline/cancel")
async def api_cancel_pipeline(payload: dict):
    run_id = payload.get("run_id")
    if not run_id:
        active_ids = list(_active_runs.keys())
        if not active_ids:
            raise HTTPException(400, "No active pipeline to cancel")
        run_id = active_ids[-1]

    event = _active_runs.get(run_id)
    if not event:
        raise HTTPException(404, f"No active pipeline found for run: {run_id}")

    event.set()
    logger.info("pipeline_cancel_requested", run_id=run_id)
    return {"status": "cancelling", "run_id": run_id}


@app.get("/api/smoke")
async def api_smoke_test():
    try:
        orch = _get_orchestrator()
        results = orch.smoke_test()
        return results
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/review")
async def api_review(payload: dict):
    doc_path = payload.get("file_path")
    if not doc_path:
        raise HTTPException(400, "file_path is required")

    doc_type = payload.get("doc_type")
    project_path = payload.get("project_path")
    context_path = payload.get("context_path")

    p = Path(doc_path)
    if not p.exists():
        raise HTTPException(400, f"File not found: {doc_path}")

    config = load_app_config()
    orch = Orchestrator(config)

    loop = asyncio.get_event_loop()

    def _run_sync():
        return orch.run(doc_path, doc_type, project_path=project_path, context_path=context_path)

    try:
        artifacts = await loop.run_in_executor(None, _run_sync)
        return _artifacts_to_response(artifacts)
    except Exception as e:
        logger.error("review_failed", error=str(e))
        raise HTTPException(500, str(e))


def _run_review_background(
    review_id: str,
    doc_path: str,
    doc_type: str | None,
    project_path: str | None,
    context_path: str | None = None,
    cancel_event: threading.Event | None = None,
):
    try:
        _async_reviews[review_id]["status"] = "running"
        config = load_app_config()
        orch = Orchestrator(config)
        artifacts = orch.run(
            doc_path, doc_type, project_path=project_path, context_path=context_path, cancel_event=cancel_event
        )
        _async_reviews[review_id]["status"] = "complete"
        _async_reviews[review_id]["result"] = _artifacts_to_response(artifacts)
    except PipelineCancelledError:
        _async_reviews[review_id]["status"] = "cancelled"
        _async_reviews[review_id]["error"] = "Pipeline cancelled by user"
    except Exception as e:
        logger.exception("async_review_failed", review_id=review_id, error=str(e), exc_info=True)
        _async_reviews[review_id]["status"] = "failed"
        _async_reviews[review_id]["error"] = str(e)
    finally:
        _active_runs.pop(review_id, None)


def _run_from_jira_background(
    review_id: str,
    task_key: str,
    context_path: str | None,
    project_path: str | None,
    generate_only: bool = False,
    cancel_event: threading.Event | None = None,
):
    try:
        _async_reviews[review_id]["status"] = "running"
        config = load_app_config()
        orch = Orchestrator(config)
        artifacts = orch.run_from_jira(
            task_key=task_key,
            context_path=context_path,
            project_path=project_path,
            generate_only=generate_only,
            cancel_event=cancel_event,
        )
        _async_reviews[review_id]["status"] = "complete"
        _async_reviews[review_id]["result"] = _artifacts_to_response(artifacts)
    except PipelineCancelledError:
        _async_reviews[review_id]["status"] = "cancelled"
        _async_reviews[review_id]["error"] = "Pipeline cancelled by user"
    except Exception as e:
        logger.exception("from_jira_failed", review_id=review_id, error=str(e), exc_info=True)
        _async_reviews[review_id]["status"] = "failed"
        _async_reviews[review_id]["error"] = str(e)
    finally:
        _active_runs.pop(review_id, None)


@app.post("/api/review/start")
async def api_review_start(payload: dict):
    doc_path = payload.get("file_path")
    if not doc_path:
        raise HTTPException(400, "file_path is required")

    p = Path(doc_path)
    if not p.exists():
        raise HTTPException(400, f"File not found: {doc_path}")

    doc_type = payload.get("doc_type")
    project_path = payload.get("project_path")
    context_path = payload.get("context_path")
    review_id = uuid.uuid4().hex[:12]

    _async_reviews[review_id] = {
        "review_id": review_id,
        "status": "queued",
        "doc_path": doc_path,
        "doc_type": doc_type,
        "project_path": project_path,
        "result": None,
        "error": None,
    }

    cancel_event = threading.Event()
    _active_runs[review_id] = cancel_event

    t = threading.Thread(
        target=_run_review_background,
        args=(review_id, doc_path, doc_type, project_path),
        kwargs={"context_path": context_path, "cancel_event": cancel_event},
        daemon=True,
    )
    t.start()

    return {"review_id": review_id, "status": "queued"}


@app.post("/api/review/from-jira")
async def api_review_from_jira(payload: dict):
    task_key = payload.get("task_key")
    if not task_key:
        raise HTTPException(400, "task_key is required")

    context_path = payload.get("context_path")
    project_path = payload.get("project_path")
    generate_only = payload.get("generate_only", False)
    review_id = uuid.uuid4().hex[:12]

    _async_reviews[review_id] = {
        "review_id": review_id,
        "status": "queued",
        "doc_path": None,
        "doc_type": "implementation_plan",
        "project_path": project_path,
        "task_key": task_key,
        "result": None,
        "error": None,
    }

    cancel_event = threading.Event()
    _active_runs[review_id] = cancel_event

    t = threading.Thread(
        target=_run_from_jira_background,
        args=(review_id, task_key, context_path, project_path, generate_only),
        kwargs={"cancel_event": cancel_event},
        daemon=True,
    )
    t.start()

    return {"review_id": review_id, "status": "queued"}


@app.get("/api/review/status/{review_id}")
async def api_review_status(review_id: str):
    review = _async_reviews.get(review_id)
    if not review:
        raise HTTPException(404, f"Review not found: {review_id}")

    return {
        "review_id": review_id,
        "status": review["status"],
        "result": review["result"],
        "error": review["error"],
    }


@app.post("/api/review/rescore")
async def api_review_rescore(payload: dict):
    previous_review_id = payload.get("previous_review_id")
    if not previous_review_id:
        raise HTTPException(400, "previous_review_id is required")

    prev_review = _async_reviews.get(previous_review_id)
    if not prev_review:
        raise HTTPException(404, f"Previous review not found: {previous_review_id}")

    prev_result = prev_review.get("result") or {}
    prev_run_dir = prev_result.get("output_dir")
    if not prev_run_dir:
        raise HTTPException(400, "Previous review has no output directory")

    revised_file_path = payload.get("revised_file_path")
    review_id = uuid.uuid4().hex[:12]

    _async_reviews[review_id] = {
        "review_id": review_id,
        "status": "queued",
        "doc_path": None,
        "doc_type": "rescore",
        "project_path": None,
        "result": None,
        "error": None,
    }

    cancel_event = threading.Event()
    _active_runs[review_id] = cancel_event

    def _run_rescore_bg(rid, prev_dir, rev_path, cancel_evt):
        try:
            _async_reviews[rid]["status"] = "running"
            config = load_app_config()
            orch = Orchestrator(config)
            artifacts = orch.run_rescore(
                previous_run_dir=prev_dir,
                revised_file_path=rev_path,
                cancel_event=cancel_evt,
            )
            _async_reviews[rid]["result"] = _artifacts_to_response(artifacts)
            _async_reviews[rid]["status"] = "complete"
        except Exception as e:
            _async_reviews[rid]["error"] = str(e)
            _async_reviews[rid]["status"] = "failed"

    t = threading.Thread(
        target=_run_rescore_bg,
        args=(review_id, prev_run_dir, revised_file_path, cancel_event),
        daemon=True,
    )
    t.start()

    return {"review_id": review_id, "status": "queued", "previous_review_id": previous_review_id}


@app.post("/api/demo")
async def api_demo():
    try:
        config = load_app_config()
        orch = Orchestrator(config)
        results = []
        examples = {
            "feature_spec": str(_PROJECT_ROOT / "examples" / "feature_spec" / "sample.md"),
            "implementation_plan": str(_PROJECT_ROOT / "examples" / "implementation_plan" / "sample.md"),
            "architecture_change": str(_PROJECT_ROOT / "examples" / "architecture_change" / "sample.md"),
        }
        for doc_type, path in examples.items():
            if Path(path).exists():
                artifacts = orch.run(path, doc_type)
                results.append(_artifacts_to_response(artifacts))
        return {"results": results}
    except Exception as e:
        logger.error("demo_failed", error=str(e))
        raise HTTPException(500, str(e))


def _artifacts_to_response(artifacts) -> dict:
    scorecard = artifacts.scorecard
    return {
        "run_id": artifacts.run_id,
        "output_dir": artifacts.output_dir,
        "issues_count": len(artifacts.issues),
        "valid_issues": sum(1 for v in artifacts.validations if v.decision.value == "valid"),
        "scorecard": scorecard.model_dump() if scorecard else None,
        "passed": scorecard.passed if scorecard else None,
        "overall_score": scorecard.overall_score if scorecard else None,
        "recommended_next_action": (scorecard.recommended_next_action.value if scorecard else None),
    }


def _render_page(page: str, **kwargs) -> str:
    if page == "runs":
        return _runs_html()
    elif page == "run_detail":
        return _run_detail_html(kwargs.get("run_id", ""))
    elif page == "dashboard":
        return _dashboard_html()
    elif page == "settings":
        return _settings_html()
    elif page == "smoke":
        return _smoke_html()
    elif page == "simulator":
        return _simulator_html()
    return "<html><body>Not found</body></html>"


def _runs_html() -> str:
    return """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Çalışmalar - Doc Quality Gate</title>
<style>
  :root { --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --purple: #a855f7; --orange: #f97316; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  nav { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--accent); }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.9rem; }
  nav a:hover, nav a.active { color: var(--text); }
  .container { max-width: 960px; margin: 2rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.6rem; margin-bottom: 1.5rem; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); text-align: left; font-size: 0.9rem; }
  th { color: var(--dim); font-weight: 500; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  tr:hover { background: var(--surface); }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }
  .badge-pass { background: #14532d; color: #86efac; }
  .badge-fail { background: #7f1d1d; color: #fca5a5; }
  .badge-cancelled { background: #422006; color: #fbbf24; }
  .badge-running { background: #1e3a5f; color: #93c5fd; }
  .dur { color: var(--purple); font-weight: 600; }
  .status-cancelled { color: var(--orange); }
</style>
</head>
<body>
<nav>
  <div class="brand">DQG</div>
  <a href="/dashboard">Dashboard</a>
  <a href="/runs" class="active">Çalışmalar</a>
  <a href="/settings">Ayarlar</a>
  <a href="/smoke">Smoke Test</a>
  <a href="/simulator">Simulator</a>
</nav>
<div class="container">
  <h1>Geçmiş Çalışmalar</h1>
  <table>
    <thead><tr><th>Çalışma ID</th><th>Tür</th><th>Puan</th><th>Sonuç</th><th>Süre</th><th>Durum</th><th>Zaman</th></tr></thead>
    <tbody id="runsBody"></tbody>
  </table>
</div>
<script>
function fmtDur(ms){if(ms==null||ms===undefined)return'<span style="color:var(--dim)">-</span>';if(ms<1000)return ms+'ms';if(ms<60000)return(ms/1000).toFixed(1)+'s';var m=Math.floor(ms/60000);var s=Math.round((ms%60000)/1000);return m+'dk '+s+'sn';}
async function loadRuns() {
  const resp = await fetch('/api/runs');
  const data = await resp.json();
  const tbody = document.getElementById('runsBody');
  tbody.innerHTML = data.runs.map(r => {
    var statusBadge = '-';
    if(r.overall_score!=null&&r.overall_score!==undefined) statusBadge=r.overall_score>=8?'<span class="badge badge-pass">GEÇTİ</span>':'<span class="badge badge-fail">KALDI</span>';
    else if(r.status==='cancelled') statusBadge='<span class="badge badge-cancelled">İPTAL</span>';
    else if(r.status==='running') statusBadge='<span class="badge badge-running">ÇALIŞIYOR</span>';
    else if(r.status==='failed') statusBadge='<span class="badge badge-fail">HATA</span>';
    else if(r.status) statusBadge=r.status;
    return `<tr>
    <td><a href="/run/${r.run_id}">${r.run_id}</a></td>
    <td>${r.document_type}</td>
    <td>${r.overall_score !== null && r.overall_score !== undefined ? r.overall_score + '/10' : '-'}</td>
    <td>${statusBadge}</td>
    <td class="dur">${fmtDur(r.duration_ms)}</td>
    <td>${r.recommended_next_action || '-'}</td>
    <td>${r.timestamp ? new Date(r.timestamp).toLocaleString('tr-TR') : '-'}</td>
  </tr>`}).join('');
}
loadRuns();
</script>
</body>
</html>"""


def _run_detail_html(run_id: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Run {run_id} - Doc Quality Gate</title>
<style>
  :root {{ --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
  nav {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }}
  nav .brand {{ font-weight: 700; font-size: 1.1rem; color: var(--accent); }}
  nav a {{ color: var(--dim); text-decoration: none; font-size: 0.9rem; }}
  nav a:hover {{ color: var(--text); }}
  .container {{ max-width: 960px; margin: 2rem auto; padding: 0 1.5rem; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 1rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }}
  .score-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 0.5rem; }}
  .score-item {{ background: var(--bg); border-radius: 6px; padding: 0.6rem; text-align: center; }}
  .score-item .label {{ font-size: 0.7rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.04em; }}
  .score-item .value {{ font-size: 1.3rem; font-weight: 700; }}
  .score-good {{ color: var(--green); }} .score-ok {{ color: var(--yellow); }} .score-bad {{ color: var(--red); }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }}
  .badge-pass {{ background: #14532d; color: #86efac; }} .badge-fail {{ background: #7f1d1d; color: #fca5a5; }}
  .gate-pass {{ border-left: 4px solid var(--green); }} .gate-fail {{ border-left: 4px solid var(--red); }}
  pre {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; overflow-x: auto; font-size: 0.82rem; white-space: pre-wrap; }}
  .bar-track {{ height: 4px; background: var(--border); border-radius: 2px; margin-top: 0.3rem; }}
  .bar-fill {{ height: 100%; border-radius: 2px; }}
  .tab-bar {{ display: flex; gap: 0; margin-bottom: 1rem; }}
  .tab {{ padding: 0.4rem 0.8rem; background: var(--bg); border: 1px solid var(--border); cursor: pointer; font-size: 0.85rem; color: var(--dim); }}
  .tab:first-child {{ border-radius: 6px 0 0 6px; }} .tab:last-child {{ border-radius: 0 6px 6px 0; }}
  .tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .tab-content {{ display: none; }} .tab-content.active {{ display: block; }}
</style>
</head>
<body>
<nav>
   <div class="brand">DQG</div>
   <a href="/dashboard">Dashboard</a>
   <a href="/runs">Runs</a>
   <a href="/settings">Settings</a>
   <a href="/smoke">Smoke Test</a>
   <a href="/simulator">Simulator</a>
</nav>
<div class="container">
   <h1>Run: <span id="runId">{run_id}</span></h1>
  <div id="content">Loading...</div>
</div>
<script>
function scoreColor(s) {{ return s >= 8 ? 'score-good' : s >= 6 ? 'score-ok' : 'score-bad'; }}
function barColor(s) {{ return s >= 8 ? 'var(--green)' : s >= 6 ? 'var(--yellow)' : 'var(--red)'; }}

async function load() {{
  const resp = await fetch('/api/runs/{run_id}');
  const data = await resp.json();
  const sc = data.scorecard || {{}};
  const ds = sc.dimension_scores || {{}};
  const dims = ['correctness','completeness','implementability','consistency','edge_case_coverage','testability','risk_awareness','clarity'];
  const passed = sc.overall_score != null && sc.overall_score >= 8;
  const gateClass = passed ? 'gate-pass' : 'gate-fail';
  const gateBadge = passed ? 'badge-pass' : 'badge-fail';

  let html = `
    <div class="card ${{gateClass}}">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span class="badge ${{gateBadge}}" style="font-size:1rem;padding:0.3rem 0.8rem;">${{passed ? 'PASS' : 'FAIL'}}</span>
        <span style="font-size:1.8rem;font-weight:700;" class="${{scoreColor(sc.overall_score||0)}}">${{sc.overall_score||0}}/10</span>
      </div>
      <div style="margin-top:0.5rem;color:var(--dim);font-size:0.85rem;">
        Action: ${{sc.recommended_next_action||'-'}} | Unresolved critical: ${{sc.unresolved_critical_issues_count||0}}
      </div>
      ${{sc.blocking_reasons && sc.blocking_reasons.length ? '<div style="margin-top:0.5rem;color:var(--red);font-size:0.85rem;">' + sc.blocking_reasons.map(r=>'• '+r).join('<br>') + '</div>' : ''}}
    </div>
    <div class="score-grid">
      ${{dims.map(d => {{
        const v = ds[d] || 0;
        return '<div class="score-item"><div class="label">'+d.replace(/_/g,' ')+'</div><div class="value ${{scoreColor(v)}}">'+v+'</div><div class="bar-track"><div class="bar-fill" style="width:'+v*10+'%;background:'+barColor(v)+';"></div></div></div>';
      }}).join('')}}
    </div>
    <div class="tab-bar" style="margin-top:1rem;">
      <div class="tab active" onclick="switchTab('original')">Original</div>
      <div class="tab" onclick="switchTab('revised')">Revised</div>
      <div class="tab" onclick="switchTab('issues')">Issues</div>
      <div class="tab" onclick="switchTab('fullreport')">Full Report</div>
    </div>
    <div id="tab-original" class="tab-content active"><pre>${{(data['original.md']||'').replace(/</g,'&lt;')}}</pre></div>
    <div id="tab-revised" class="tab-content"><pre>${{(data['revised.md']||'').replace(/</g,'&lt;')}}</pre></div>
    <div id="tab-issues" class="tab-content"><pre>${{JSON.stringify(data.issues||[], null, 2).replace(/</g,'&lt;')}}</pre></div>
    <div id="tab-fullreport" class="tab-content"><iframe src="/api/runs/{run_id}/report" style="width:100%;height:80vh;border:none;border-radius:6px;"></iframe></div>
  `;
  document.getElementById('content').innerHTML = html;
}}

function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  event.target.classList.add('active');
}}

load();
</script>
</body>
</html>"""


def _settings_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Settings - Doc Quality Gate</title>
<style>
  :root { --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  nav { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--accent); }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.9rem; }
  nav a:hover, nav a.active { color: var(--text); }
  .container { max-width: 960px; margin: 2rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.6rem; margin-bottom: 1.5rem; }
  h2 { font-size: 1.2rem; margin-bottom: 1rem; color: var(--dim); }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
  label { display: block; font-size: 0.85rem; color: var(--dim); margin-bottom: 0.4rem; font-weight: 500; }
  select, input[type="text"] { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem; color: var(--text); font-size: 0.9rem; margin-bottom: 1rem; }
  select:focus, input:focus { outline: none; border-color: var(--accent); }
  button { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 0.7rem 1.5rem; font-size: 0.95rem; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
  button:hover { opacity: 0.9; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-sm { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
  .btn-secondary { background: var(--border); }
  .btn-green { background: var(--green); }
  .btn-red { background: var(--red); }
  table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
  th, td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); text-align: left; font-size: 0.9rem; }
  th { color: var(--dim); font-weight: 500; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }
  .badge-ok { background: #14532d; color: #86efac; }
  .badge-err { background: #7f1d1d; color: #fca5a5; }
  .badge-warn { background: #713f12; color: #fde047; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.4rem; }
  .dot-green { background: var(--green); }
  .dot-red { background: var(--red); }
  .dot-yellow { background: var(--yellow); }
  .status-section { margin-top: 1rem; }
  .flex-between { display: flex; justify-content: space-between; align-items: center; }
  .msg { padding: 0.5rem 0; font-size: 0.85rem; }
  .msg-ok { color: var(--green); }
  .msg-err { color: var(--red); }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 0.5rem; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<nav>
  <div class="brand">DQG</div>
  <a href="/dashboard">Dashboard</a>
  <a href="/runs">Runs</a>
  <a href="/settings" class="active">Settings</a>
  <a href="/smoke">Smoke Test</a>
  <a href="/simulator">Simulator</a>
</nav>

<div class="container">
  <h1>Settings</h1>

  <!-- COPilot STATUS -->
  <h2>GitHub Copilot Subscription</h2>
  <div class="card" id="copilotCard">
    <div class="flex-between">
      <span>Checking status...</span>
      <span class="spinner"></span>
    </div>
  </div>

  <!-- MODEL GROUPS -->
  <h2>Model Groups</h2>
  <div class="card">
    <p style="color:var(--dim);font-size:0.85rem;margin-bottom:1rem;">Configure the underlying model for each group. Changes are written to config files and take effect on next pipeline run. Restart the LiteLLM proxy to apply changes.</p>
    <table>
      <thead><tr><th>Group</th><th>Provider</th><th>Current Model</th><th>New Model</th><th></th></tr></thead>
      <tbody id="groupsBody"></tbody>
    </table>
    <div id="groupMsg" class="msg"></div>
  </div>

  <!-- STAGE ROUTING -->
  <h2>Stage Routing</h2>
  <div class="card">
    <p style="color:var(--dim);font-size:0.85rem;margin-bottom:1rem;">Map pipeline stages to model groups. Changes take effect on next pipeline run.</p>
    <table>
      <thead><tr><th>Stage</th><th>Model Group</th></tr></thead>
      <tbody id="routingBody"></tbody>
    </table>
    <div style="margin-top:1rem;">
      <button onclick="saveRouting()">Save Routing</button>
    </div>
    <div id="routingMsg" class="msg"></div>
  </div>
</div>

<script>
const GROUPS_ORDER = ['cheap_large_context', 'cheap_large_context_alt', 'strong_judge', 'fallback_general'];
const STAGES_ORDER = ['critic_a', 'critic_b', 'critic_judge', 'validator', 'reviser', 'scorer', 'fallback'];
let currentRouting = {};
let currentGroups = {};

async function loadModels() {
  const resp = await fetch('/api/models');
  const data = await resp.json();
  currentGroups = data.groups || {};
  currentRouting = data.routing || {};
  renderGroups();
  renderRouting();
}

function renderGroups() {
  const tbody = document.getElementById('groupsBody');
  tbody.innerHTML = GROUPS_ORDER.filter(g => currentGroups[g]).map(g => {
    const grp = currentGroups[g];
    return `<tr>
      <td><strong>${g}</strong><br><span style="font-size:0.75rem;color:var(--dim)">${grp.description}</span></td>
      <td>${grp.provider}</td>
      <td><code style="color:var(--accent)">${grp.model}</code></td>
      <td><input type="text" id="model-${g}" value="${grp.model}" style="width:100%;padding:0.4rem;font-size:0.85rem;"></td>
      <td><button class="btn-sm" onclick="updateGroup('${g}')">Update</button></td>
    </tr>`;
  }).join('');
}

function renderRouting() {
  const tbody = document.getElementById('routingBody');
  tbody.innerHTML = STAGES_ORDER.map(stage => {
    const current = currentRouting[stage] || '';
    return `<tr>
      <td><code>${stage}</code></td>
      <td>
        <select id="route-${stage}" style="width:100%;padding:0.4rem;font-size:0.85rem;">
          ${GROUPS_ORDER.map(g => `<option value="${g}" ${g === current ? 'selected' : ''}>${g}</option>`).join('')}
        </select>
      </td>
    </tr>`;
  }).join('');
}

async function updateGroup(groupName) {
  const input = document.getElementById('model-' + groupName);
  const newModel = input.value.trim();
  const msg = document.getElementById('groupMsg');
  if (!newModel) { msg.className = 'msg msg-err'; msg.textContent = 'Model cannot be empty'; return; }

  msg.className = 'msg'; msg.innerHTML = '<span class="spinner"></span>Saving...';
  try {
    const resp = await fetch('/api/models/group/' + groupName, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model: newModel})
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Failed');
    msg.className = 'msg msg-ok'; msg.textContent = 'Updated ' + groupName + ' to ' + newModel;
    setTimeout(() => loadModels(), 500);
  } catch(e) {
    msg.className = 'msg msg-err'; msg.textContent = 'Error: ' + e.message;
  }
}

async function saveRouting() {
  const msg = document.getElementById('routingMsg');
  const newRouting = {};
  STAGES_ORDER.forEach(stage => {
    const sel = document.getElementById('route-' + stage);
    if (sel) newRouting[stage] = sel.value;
  });

  msg.className = 'msg'; msg.innerHTML = '<span class="spinner"></span>Saving...';
  try {
    const resp = await fetch('/api/models/routing', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({routing: newRouting})
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Failed');
    currentRouting = data.routing;
    msg.className = 'msg msg-ok'; msg.textContent = 'Routing saved successfully.';
  } catch(e) {
    msg.className = 'msg msg-err'; msg.textContent = 'Error: ' + e.message;
  }
}

async function loadCopilotStatus() {
  const card = document.getElementById('copilotCard');
  card.innerHTML = '<div class="flex-between"><span>Checking Copilot status...</span><span class="spinner"></span></div>';

  try {
    const resp = await fetch('/api/copilot/status');
    const data = await resp.json();

    let proxyDot = data.proxy_healthy ? '<span class="status-dot dot-green"></span>Proxy: Healthy' : '<span class="status-dot dot-red"></span>Proxy: Unhealthy';
    let configDot = data.configured ? '<span class="status-dot dot-green"></span>Configured' : '<span class="status-dot dot-yellow"></span>Not Configured';
    let authDot = data.authenticated ? '<span class="status-dot dot-green"></span>Authenticated' : '<span class="status-dot dot-red"></span>Not Authenticated';

    let subBadge = '';
    if (data.subscription) {
      const st = data.subscription.status;
      if (st === 'active') subBadge = '<span class="badge badge-ok">Subscription Active</span>';
      else if (st === 'not_authenticated') subBadge = '<span class="badge badge-err">Not Authenticated</span>';
      else subBadge = '<span class="badge badge-warn">' + st + '</span>';
    }

    let details = '';
    if (data.model) details += '<div style="margin-top:0.5rem;font-size:0.85rem;">Model: <code style="color:var(--accent)">' + data.model + '</code></div>';
    if (data.subscription && data.subscription.model_responded) {
      details += '<div style="font-size:0.85rem;">Responded as: <code>' + data.subscription.model_responded + '</code></div>';
    }
    if (data.error) {
      details += '<div style="margin-top:0.5rem;font-size:0.85rem;color:var(--red);">' + data.error + '</div>';
    }

    card.innerHTML = `
      <div style="display:flex;gap:1.5rem;flex-wrap:wrap;align-items:center;">
        ${proxyDot} &nbsp; ${configDot} &nbsp; ${authDot} &nbsp; ${subBadge}
      </div>
      ${details}
      <div style="margin-top:1rem;">
        <button class="btn-sm btn-secondary" onclick="loadCopilotStatus()">Refresh</button>
      </div>
    `;
  } catch(e) {
    card.innerHTML = '<div class="msg msg-err">Failed to check status: ' + e.message + '</div>';
  }
}

loadModels();
loadCopilotStatus();
</script>
</body>
</html>"""


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard - Doc Quality Gate</title>
<style>
  :root { --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; --orange: #f97316; --purple: #a855f7; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  nav { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--accent); }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.9rem; transition: color 0.15s; }
  nav a:hover, nav a.active { color: var(--text); }
  .container { max-width: 1100px; margin: 1.5rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.5rem; margin-bottom: 1.25rem; }
  .status-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .status-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; }
  .status-card .label { font-size: 0.75rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.4rem; }
  .status-card .value { font-size: 1.1rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .dot-red { background: var(--red); box-shadow: 0 0 6px var(--red); }
  .dot-yellow { background: var(--yellow); box-shadow: 0 0 6px var(--yellow); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }
  .progress-section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .progress-section h2 { font-size: 1rem; margin-bottom: 0.75rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.05em; }
  .stage-list { display: flex; flex-direction: column; gap: 0.5rem; }
  .stage-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0.75rem; border-radius: 6px; background: var(--bg); font-size: 0.88rem; }
  .stage-row.active { border-left: 3px solid var(--accent); }
  .stage-row.done { border-left: 3px solid var(--green); }
  .stage-row.error { border-left: 3px solid var(--red); }
  .stage-icon { width: 18px; text-align: center; }
  .stage-name { flex: 1; }
  .stage-status { font-size: 0.78rem; color: var(--dim); }
  .stage-detail { font-size: 0.78rem; color: var(--dim); font-family: monospace; }
  .stage-duration { font-size: 0.78rem; color: var(--purple); font-weight: 600; min-width: 60px; text-align: right; }
  .log-section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
  .log-section h2 { font-size: 1rem; margin-bottom: 0.75rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.05em; display: flex; justify-content: space-between; align-items: center; }
  .log-controls { display: flex; gap: 0.5rem; }
  .log-controls button { background: var(--border); color: var(--text); border: none; border-radius: 4px; padding: 0.25rem 0.6rem; font-size: 0.75rem; cursor: pointer; }
  .log-controls button:hover { background: var(--accent); }
  .log-controls select { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 4px; padding: 0.2rem 0.4rem; font-size: 0.75rem; }
  #logBox { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; max-height: 600px; overflow-y: auto; font-family: 'Consolas','SF Mono',monospace; font-size: 0.8rem; line-height: 1.6; }
  .ll { display: flex; gap: 0.5rem; padding: 0.1rem 0; }
  .lt { color: var(--dim); min-width: 70px; }
  .lv { min-width: 50px; font-weight: 600; }
  .lv.info { color: var(--accent); } .lv.warning { color: var(--yellow); } .lv.error { color: var(--red); } .lv.debug { color: var(--dim); }
  .lm { word-break: break-all; } .ls { color: var(--orange); font-size: 0.75rem; }
  .run-badge { font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.4rem; border-radius: 3px; background: var(--purple); color: #fff; white-space: nowrap; letter-spacing: 0.03em; }

  .llm-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin: 0.5rem 0; overflow: hidden; }
  .llm-header { display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 0.75rem; cursor: pointer; user-select: none; }
  .llm-header:hover { background: rgba(59,130,246,0.07); }
  .llm-badge { font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.04em; background: var(--purple); color: #fff; }
  .llm-model { font-size: 0.82rem; color: var(--text); font-weight: 600; }
  .llm-model-real { font-size: 0.72rem; color: var(--dim); }
  .llm-meta { display: flex; gap: 1rem; margin-left: auto; font-size: 0.75rem; color: var(--dim); align-items: center; }
  .llm-meta .dur { color: var(--purple); font-weight: 600; }
  .llm-meta .tok { color: var(--accent); }
  .llm-chevron { color: var(--dim); font-size: 0.7rem; transition: transform 0.15s; }
  .llm-chevron.open { transform: rotate(90deg); }
  .llm-body { display: none; border-top: 1px solid var(--border); }
  .llm-body.open { display: block; }
  .llm-section { padding: 0.5rem 0.75rem; }
  .llm-section + .llm-section { border-top: 1px dashed var(--border); }
  .llm-section-label { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim); margin-bottom: 0.3rem; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 0.3rem; }
  .llm-section-label:hover { color: var(--text); }
  .llm-section-content { display: none; }
  .llm-section-content.open { display: block; }
  .llm-msg { padding: 0.2rem 0; font-size: 0.78rem; }
  .llm-msg-role { font-weight: 600; color: var(--accent); margin-right: 0.3rem; }
  .llm-msg-text { color: var(--dim); white-space: pre-wrap; word-break: break-all; max-height: 80vh; overflow-y: auto; background: var(--bg); padding: 0.4rem 0.5rem; border-radius: 4px; font-size: 0.75rem; }
  .llm-response-text { color: var(--text); white-space: pre-wrap; word-break: break-all; max-height: 80vh; overflow-y: auto; background: var(--bg); padding: 0.5rem; border-radius: 4px; font-size: 0.75rem; border-left: 3px solid var(--purple); }
  .llm-tok-bar { display: flex; gap: 0.5rem; font-size: 0.72rem; color: var(--dim); padding: 0.3rem 0.75rem; border-top: 1px dashed var(--border); }
  .llm-tok-bar span { color: var(--accent); font-weight: 600; }

  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; }
  .badge-pass { background: #14532d; color: #86efac; } .badge-fail { background: #7f1d1d; color: #fca5a5; } .badge-running { background: #1e3a5f; color: #93c5fd; }

  .outputs-section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; display: none; }
  .outputs-section h2 { font-size: 1rem; margin-bottom: 0.75rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.05em; display: flex; justify-content: space-between; align-items: center; }
  .file-tabs { display: flex; gap: 0; flex-wrap: wrap; margin-bottom: 0.75rem; }
  .file-tab { padding: 0.35rem 0.7rem; background: var(--bg); border: 1px solid var(--border); font-size: 0.78rem; color: var(--dim); cursor: pointer; white-space: nowrap; position: relative; }
  .file-tab:first-child { border-radius: 6px 0 0 6px; } .file-tab:last-child { border-radius: 0 6px 6px 0; }
  .file-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .file-tab .badge-count { position: absolute; top: -4px; right: -4px; background: var(--red); color: #fff; font-size: 0.6rem; padding: 0 4px; border-radius: 8px; line-height: 1.4; }
  .file-viewer { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 1.25rem; min-height: 200px; max-height: 70vh; overflow-y: auto; font-size: 0.85rem; line-height: 1.65; }
  .file-viewer h1,.file-viewer h2,.file-viewer h3,.file-viewer h4 { color: var(--text); margin: 1rem 0 0.5rem; }
  .file-viewer h1 { font-size: 1.3rem; } .file-viewer h2 { font-size: 1.1rem; } .file-viewer h3 { font-size: 1rem; }
  .file-viewer p { margin: 0.4rem 0; }
  .file-viewer ul,.file-viewer ol { padding-left: 1.5rem; margin: 0.4rem 0; }
  .file-viewer li { margin: 0.2rem 0; }
  .file-viewer code { background: var(--surface); padding: 0.1rem 0.35rem; border-radius: 3px; font-size: 0.78rem; color: var(--accent); }
  .file-viewer pre { background: var(--surface); padding: 0.75rem; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }
  .file-viewer pre code { background: none; padding: 0; }
  .file-viewer table { width: 100%; border-collapse: collapse; margin: 0.5rem 0; }
  .file-viewer th,.file-viewer td { padding: 0.5rem 0.7rem; border-bottom: 1px solid var(--border); text-align: left; font-size: 0.82rem; }
  .file-viewer th { color: var(--dim); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .file-viewer blockquote { border-left: 3px solid var(--accent); padding-left: 0.75rem; margin: 0.5rem 0; color: var(--dim); }
  .file-viewer .empty { color: var(--dim); text-align: center; padding: 2rem; }
  .file-viewer strong { color: #f1f5f9; }
  .file-viewer hr { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
  .file-viewer a { color: var(--accent); text-decoration: underline; }
  .task-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
  .task-card .tc-label { font-size: 0.72rem; color: var(--dim); text-transform: uppercase; letter-spacing: 0.04em; }
  .task-card .tc-value { font-size: 0.9rem; margin-top: 0.15rem; }
  .ta-header { display:flex; align-items:center; gap:1rem; margin-bottom:1rem; padding-bottom:0.75rem; border-bottom:1px solid var(--border); }
  .ta-key { font-size:1.1rem; font-weight:700; color:var(--accent); }
  .ta-score { font-size:1.5rem; font-weight:800; }
  .ta-status { font-size:0.78rem; padding:0.2rem 0.6rem; border-radius:4px; font-weight:600; }
  .ta-field { margin-bottom:0.75rem; }
  .ta-field-label { font-size:0.7rem; color:var(--dim); text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.15rem; }
  .ta-field-value { font-size:0.88rem; line-height:1.55; }
  .ta-tags { display:flex; gap:0.35rem; flex-wrap:wrap; margin-top:0.5rem; }
  .ta-tag { font-size:0.72rem; padding:0.15rem 0.5rem; border-radius:3px; background:var(--surface); border:1px solid var(--border); color:var(--dim); }
  .ta-tag.missing { background:#2d1b1b; border-color:#7f1d1d; color:#fca5a5; }
  .ta-grid { display:grid; grid-template-columns:1fr 1fr; gap:0.75rem; margin-bottom:1rem; }
  .ta-grid-3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.75rem; margin-bottom:1rem; }
  .severity-critical { color:#ef4444; font-weight:700; }
  .severity-high { color:#f97316; font-weight:600; }
  .severity-medium { color:#eab308; }
  .severity-low { color:#94a3b8; }
  .issue-card { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:0.75rem 1rem; margin-bottom:0.5rem; border-left:3px solid var(--border); }
  .issue-card.sev-critical { border-left-color:#ef4444; }
  .issue-card.sev-high { border-left-color:#f97316; }
  .issue-card.sev-medium { border-left-color:#eab308; }
  .issue-card.sev-low { border-left-color:#94a3b8; }
  .issue-title { font-weight:600; font-size:0.88rem; margin-bottom:0.25rem; }
  .issue-meta { display:flex; gap:0.75rem; font-size:0.75rem; color:var(--dim); }
  .issue-desc { font-size:0.82rem; color:#cbd5e1; margin-top:0.35rem; line-height:1.5; }
  .issue-fix { font-size:0.8rem; margin-top:0.3rem; padding:0.4rem 0.6rem; background:var(--bg); border-radius:4px; }
  .dim-bar { display:flex; gap:0.5rem; flex-wrap:wrap; }
  .dim-item { flex:1; min-width:120px; background:var(--bg); border-radius:6px; padding:0.6rem; text-align:center; }
  .dim-name { font-size:0.65rem; color:var(--dim); text-transform:uppercase; letter-spacing:0.04em; }
  .dim-score { font-size:1.2rem; font-weight:700; }
  .dim-bar-track { height:4px; background:var(--border); border-radius:2px; margin-top:0.25rem; }
  .dim-bar-fill { height:100%; border-radius:2px; transition:width 0.3s; }
  .severity-critical { color: #ef4444; font-weight: 700; }
  .severity-high { color: #f97316; font-weight: 700; }
  .severity-medium { color: #eab308; font-weight: 600; }
  .severity-low { color: #22c55e; }

</style>
</head>
<body>
<nav>
  <div class="brand">DQG</div>
  <a href="/dashboard" class="active">Dashboard</a>
  <a href="/runs">Runs</a>
  <a href="/settings">Settings</a>
  <a href="/smoke">Smoke Test</a>
  <a href="/simulator">Simulator</a>
</nav>
<div class="container">
  <h1>Dashboard</h1>
  <div class="status-bar">
    <div class="status-card"><div class="label">LiteLLM Proxy</div><div class="value" id="proxySt"><span class="dot dot-yellow"></span> Checking...</div></div>
    <div class="status-card"><div class="label">Web Server</div><div class="value" id="webSt"><span class="dot dot-green"></span> Running</div></div>
    <div class="status-card"><div class="label">Active Pipeline</div><div class="value" id="pipeSt">Boşta</div></div>
    <div class="status-card"><div class="label">Son Puan</div><div class="value" id="lastSc">-</div></div>
    <div class="status-card"><div class="label">Süre</div><div class="value" id="durVal">-</div></div>
  </div>
  <div id="cancelBox" style="display:none;margin-bottom:1.5rem;">
    <button id="cancelBtn" onclick="cancelPipeline()" style="background:var(--red);color:#fff;border:none;border-radius:6px;padding:0.6rem 1.2rem;font-size:0.9rem;font-weight:600;cursor:pointer;transition:opacity 0.15s;">
      Pipeline'ı Durdur
    </button>
    <span id="cancelMsg" style="margin-left:0.75rem;font-size:0.85rem;color:var(--dim);"></span>
  </div>

  <div class="progress-section"><h2>Pipeline Stages</h2><div class="stage-list" id="stageList"><div class="stage-row"><div class="stage-name" style="color:var(--dim)">No pipeline running. Submit a review to see stages.</div></div></div></div>
  <div class="outputs-section" id="outputsSection">
    <h2>Pipeline Ciktilari <span id="outputsRunBadge" style="font-size:0.7rem;font-weight:700;padding:0.1rem 0.4rem;border-radius:3px;background:var(--purple);color:#fff;letter-spacing:0.03em;"></span></h2>
    <div class="file-tabs" id="fileTabs"></div>
    <div class="file-viewer" id="fileViewer"><div class="empty">Dosyalar olusturuldukca burada gorunecek...</div></div>
  </div>
  <div class="log-section">
    <h2>Live Logs <div class="log-controls"><select id="logFilter" onchange="filterLogs()"><option value="all">All</option><option value="active">Active Pipeline</option><option value="llm">LLM Calls</option><option value="info">Info+</option><option value="warning">Warn+</option><option value="error">Error</option></select><button onclick="document.getElementById('logBox').innerHTML='';allLogs=[];">Clear</button></div></h2>
    <div id="logBox"></div>
  </div>
</div>
<script>
var STAGES=['jira_fetch','task_analysis','document_generation','ingest','domain_context','cross_reference','deep_analysis','critic_a_multi','critic_a_judge','critic_b_multi','critic_b_judge','dedup','validate','revise','score','meta_judge','fact_check','report'];
var SLABELS={jira_fetch:'Jira Fetch',task_analysis:'Task Analysis',document_generation:'Doc Generation',ingest:'Document Ingestion',domain_context:'Domain Context',cross_reference:'Cross-Reference',deep_analysis:'Deep Analysis',critic_a_multi:'Critic A',critic_a_judge:'Critic A Judge',critic_b_multi:'Critic B',critic_b_judge:'Critic B Judge',dedup:'Deduplication',validate:'Validation',revise:'Revision',score:'Scoring',meta_judge:'Meta-Judge',fact_check:'Fact-Check',report:'Report'};
var stgs={},curRun=null,allLogs=[],logIdCounter=0;
function ft(ts){var d=new Date(ts*1000);return d.toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});}
function lc(l){return l==='error'||l==='critical'?'error':l==='warning'||l==='warn'?'warning':l==='debug'?'debug':'info';}
function lr(l){return l==='error'||l==='critical'?3:l==='warning'||l==='warn'?2:l==='info'?1:0;}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function fmtDuration(ms){if(ms==null)return'';if(ms<1000)return ms+'ms';return(ms/1000).toFixed(1)+'s';}

function renderLLMCard(m){
  var id='llm_'+(++logIdCounter);
  var d=document.createElement('div');
  d.className='llm-card';
  d.dataset.logtype='llm';

  var reqHTML='';
  if(m.request_summary&&m.request_summary.length){
    reqHTML=m.request_summary.map(function(msg){
      return '<div class="llm-msg"><span class="llm-msg-role">'+esc(msg.role)+'：</span></div><div class="llm-msg-text">'+esc(msg.preview)+'</div>';
    }).join('');
  }

  var respHTML='';
  if(m.response_preview){
    respHTML='<div class="llm-response-text">'+esc(m.response_preview)+'</div>';
    if(m.response_length>m.response_preview.length-3){
      respHTML+='<div style="font-size:0.7rem;color:var(--dim);margin-top:0.2rem;">Full response: '+m.response_length+' chars</div>';
    }
  }

  var stageLabel=esc(m.stage||'');
  var modelGroup=esc(m.model_group||'');
  var modelUsed=esc(m.model_used||'');
  var dur=fmtDuration(m.duration_ms);
  var totalTok=m.tokens_total||0;

  d.innerHTML=
    '<div class="llm-header" onclick="toggleLLMBody(\\''+id+'\\')">'+
      '<span class="llm-chevron" id="chv_'+id+'">&#9654;</span>'+
      '<span class="llm-badge">LLM</span>'+
      '<span class="llm-model">'+stageLabel+'</span>'+
      '<span class="llm-model-real">'+modelGroup+' → '+modelUsed+'</span>'+
      '<div class="llm-meta">'+
        '<span class="dur">'+dur+'</span>'+
        '<span class="tok">'+totalTok+' tok</span>'+
      '</div>'+
    '</div>'+
    '<div class="llm-body" id="body_'+id+'">'+
      '<div class="llm-section">'+
        '<div class="llm-section-label" onclick="toggleLLMSection(\\''+id+'_req\\',event)"><span id="chv_'+id+'_req">&#9654;</span> Request ('+(m.request_summary?m.request_summary.length:0)+' messages)</div>'+
        '<div class="llm-section-content" id="sec_'+id+'_req">'+reqHTML+'</div>'+
      '</div>'+
      '<div class="llm-section">'+
        '<div class="llm-section-label" onclick="toggleLLMSection(\\''+id+'_resp\\',event)"><span id="chv_'+id+'_resp">&#9654;</span> Response</div>'+
        '<div class="llm-section-content" id="sec_'+id+'_resp">'+respHTML+'</div>'+
      '</div>'+
      '<div class="llm-tok-bar">'+
        'Prompt: <span>'+(m.tokens_prompt||0)+'</span> &nbsp; Completion: <span>'+(m.tokens_completion||0)+'</span> &nbsp; Total: <span>'+totalTok+'</span>'+
      '</div>'+
    '</div>';

  return d;
}

function toggleLLMBody(id){
  var body=document.getElementById('body_'+id);
  var chv=document.getElementById('chv_'+id);
  if(body.classList.contains('open')){body.classList.remove('open');chv.classList.remove('open');}
  else{body.classList.add('open');chv.classList.add('open');}
}

function toggleLLMSection(id,event){
  event.stopPropagation();
  var sec=document.getElementById('sec_'+id);
  var chv=document.getElementById('chv_'+id);
  if(sec.classList.contains('open')){sec.classList.remove('open');chv.classList.remove('open');}
  else{sec.classList.add('open');chv.classList.add('open');}
}

function rl(m){
  var f=document.getElementById('logFilter').value;
  var mRun=m.run_id||null;
  if(f==='active'){
    if(mRun&&curRun&&mRun!==curRun)return;
    if(!mRun&&curRun)return;
  }
  if(m.type==='llm_call'){
    if(f!=='all'&&f!=='active'&&f!=='llm')return;
    var c=document.getElementById('logBox');
    var el=renderLLMCard(m);
    if(mRun)el.dataset.runid=mRun;
    c.appendChild(el);
    if(c.children.length>300)c.removeChild(c.firstChild);
    c.scrollTop=c.scrollHeight;
    return;
  }
  if(f==='llm')return;
  if(f!=='all'&&f!=='active'&&lr(m.level)<lr(f))return;
  var c=document.getElementById('logBox'),d=document.createElement('div');
  d.className='ll';d.dataset.logtype='log';
  if(mRun)d.dataset.runid=mRun;
  var runBadge=(mRun&&mRun===curRun)?'<span class="run-badge">'+mRun.substring(0,8)+'</span>':'';
  d.innerHTML='<span class="lt">'+ft(m.timestamp)+'</span><span class="lv '+lc(m.level)+'">'+m.level.toUpperCase()+'</span>'+runBadge+'<span class="lm">'+esc(m.message)+'</span>'+(m.source&&m.source!=='system'?'<span class="ls">['+m.source+']</span>':'');
  c.appendChild(d);if(c.children.length>500)c.removeChild(c.firstChild);c.scrollTop=c.scrollHeight;
}

function filterLogs(){
  document.getElementById('logBox').innerHTML='';
  allLogs.forEach(function(m){rl(m);});
}

function us(){
  var l=document.getElementById('stageList');
  if(!curRun){l.innerHTML='<div class="stage-row"><div class="stage-name" style="color:var(--dim)">Çalışan pipeline yok.</div></div>';return;}
  var h='';
  STAGES.forEach(function(s){
    var i=stgs[s];
    if(!i)return;
    var c=i.status==='done'?'done':i.status==='error'?'error':i.status==='running'?'active':i.status==='cancelled'?'error':'';
    var ic=i.status==='done'?'\u2713':i.status==='error'?'\u2717':i.status==='running'?'\u25b6':i.status==='cancelled'?'\u25a0':'\u25cb';
    var dur=i.duration_ms!=null?'<div class="stage-duration">'+fmtDuration(i.duration_ms)+'</div>':'';
    h+='<div class="stage-row '+c+'"><div class="stage-icon">'+ic+'</div><div class="stage-name">'+(SLABELS[s]||s)+'</div>'+dur+'<div class="stage-status">'+i.status+'</div><div class="stage-detail">'+(i.detail||'')+'</div></div>';
  });
  l.innerHTML=h;
}

function showCancelBtn(runId){
  var box=document.getElementById('cancelBox');
  var btn=document.getElementById('cancelBtn');
  box.style.display='block';
  btn.disabled=false;
  btn.dataset.runId=runId;
  document.getElementById('cancelMsg').textContent='';
}
function hideCancelBtn(){
  document.getElementById('cancelBox').style.display='none';
}
async function cancelPipeline(){
  var btn=document.getElementById('cancelBtn');
  var runId=btn.dataset.runId;
  if(!runId)return;
  btn.disabled=true;
  document.getElementById('cancelMsg').innerHTML='<span class="spinner" style="width:12px;height:12px;border-width:2px;"></span>İptal ediliyor...';
  try{
    var resp=await fetch('/api/pipeline/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId})});
    var data=await resp.json();
    if(!resp.ok)throw new Error(data.detail||'İptal başarısız');
    document.getElementById('cancelMsg').textContent='Pipeline iptal ediliyor...';
    setTimeout(hideCancelBtn,3000);
  }catch(e){
    document.getElementById('cancelMsg').innerHTML='<span style="color:var(--red)">Hata: '+e.message+'</span>';
    btn.disabled=false;
  }
}

var pipeStartMs=null;
var pipeTimerId=null;
function startPipeTimer(tsMs){
  pipeStartMs=tsMs||Date.now();
  if(pipeTimerId)clearInterval(pipeTimerId);
  pipeTimerId=setInterval(function(){
    var elapsed=Date.now()-pipeStartMs;
    document.getElementById('durVal').innerHTML='<span style="color:var(--purple);font-weight:700">'+fmtDuration(elapsed)+'</span>';
  },500);
}
function stopPipeTimer(finalMs){
  if(pipeTimerId){clearInterval(pipeTimerId);pipeTimerId=null;}
  pipeStartMs=null;
  if(finalMs!=null){
    var durStr=finalMs<60000?fmtDuration(finalMs):Math.floor(finalMs/60000)+'dk '+Math.round((finalMs%60000)/1000)+'sn';
    document.getElementById('durVal').innerHTML='<span style="color:var(--purple);font-weight:700">'+durStr+'</span>';
  }
}

var es=new EventSource('/api/events');
es.onmessage=function(e){
  try{
    var m=JSON.parse(e.data);
    if(m.type==='log'){
      allLogs.push(m);rl(m);
    }else if(m.type==='llm_call'){
      allLogs.push(m);rl(m);
    }else if(m.type==='pipeline_stage'){
      if(m.run_id&&m.run_id!==curRun){curRun=m.run_id;stgs={};document.getElementById('logBox').innerHTML='';allLogs=[];document.getElementById('logFilter').value='active';document.getElementById('pipeSt').innerHTML='<span class="badge badge-running">'+m.run_id+'</span>';showCancelBtn(m.run_id);startPipeTimer(m.timestamp?m.timestamp*1000:null);startFilePolling(m.run_id);}
      stgs[m.stage]={status:m.status,detail:m.detail||'',duration_ms:m.duration_ms};
      us();
    }else if(m.type==='pipeline_done'){
      hideCancelBtn();
      stopPipeTimer(m.duration_ms);
      fetchFiles(curRun);
      stopFilePolling();
      if(m.score!=null){var c=m.score>=8?'var(--green)':'var(--red)';document.getElementById('lastSc').innerHTML='<span style="color:'+c+';font-weight:700">'+m.score+'/10</span>';}
      if(m.run_id===curRun){var st=m.score==null?'<span class="badge badge-fail">HATA</span>':m.score>=8?'<span class="badge badge-pass">GEÇTİ</span>':'<span class="badge badge-fail">KALDI</span>';document.getElementById('pipeSt').innerHTML=st;}

    }else if(m.type==='setup_step'){
      allLogs.push({level:'info',message:'[Setup '+m.step_number+'/'+m.total_steps+'] '+m.step,timestamp:m.timestamp,source:'setup'});rl(allLogs[allLogs.length-1]);
    }else if(m.type==='setup_done'){
      var l=m.success?'info':'error';
      allLogs.push({level:l,message:m.success?'Setup completed':'Setup failed: '+(m.errors||[]).join(', '),timestamp:m.timestamp,source:'setup'});rl(allLogs[allLogs.length-1]);
    }
  }catch(x){}
};
es.onerror=function(){document.getElementById('webSt').innerHTML='<span class="dot dot-red"></span> Reconnecting...';};
function ck(){fetch('/api/status').then(function(r){return r.json();}).then(function(d){document.getElementById('proxySt').innerHTML=d.proxy&&d.proxy.healthy?'<span class="dot dot-green"></span> Healthy':'<span class="dot dot-red"></span> Down';}).catch(function(){document.getElementById('proxySt').innerHTML='<span class="dot dot-red"></span> Error';});}
ck();setInterval(ck,15000);

var _filePollId=null;
var _knownFiles={};
var _activeFileTab=null;

var FILE_TABS=[
  {key:'task_analysis',label:'Task Analiz',files:['task_analysis.json']},
  {key:'original',label:'Dokuman',files:['original.md']},
  {key:'context',label:'Context',files:['domain_context.md','domain_analysis.md','codebase_context.md']},
  {key:'issues',label:'Sorunlar',files:['issues.json']},
  {key:'validations',label:'Validasyon',files:['validations.json']},
  {key:'revised',label:'Revize',files:['revised.md']},
  {key:'scorecard',label:'Scorecard',files:['scorecard.json']},
  {key:'report',label:'Rapor',files:['report.html','report.md']},
  {key:'factcheck',label:'Fact-Check',files:['fact_check.json','fact_check.md']}
];

function startFilePolling(runId){
  var sec=document.getElementById('outputsSection');
  sec.style.display='block';
  document.getElementById('outputsRunBadge').textContent=runId.substring(0,12);
  _knownFiles={};_activeFileTab=null;
  document.getElementById('fileTabs').innerHTML='';
  document.getElementById('fileViewer').innerHTML='<div class="empty">Dosyalar olusturuldukca burada gorunecek...</div>';
  if(_filePollId)clearInterval(_filePollId);
  _filePollId=setInterval(function(){fetchFiles(runId);},2000);
  fetchFiles(runId);
}
function stopFilePolling(){
  if(_filePollId){clearInterval(_filePollId);_filePollId=null;}
  fetchFiles(curRun);
}

function fetchFiles(runId){
  if(!runId)return;
  fetch('/api/runs/'+runId+'/files').then(function(r){return r.json();}).then(function(data){
    var files=data.files||{};
    var changed=false;
    for(var k in files){if(!_knownFiles[k])changed=true;}
    _knownFiles=files;
    if(changed||!document.getElementById('fileTabs').children.length)renderFileTabs(runId);
  }).catch(function(){});
}

function renderFileTabs(runId){
  var tabsEl=document.getElementById('fileTabs');
  var html='';
  FILE_TABS.forEach(function(tab){
    var exists=tab.files.some(function(f){return _knownFiles[f];});
    if(!exists)return;
    var cls=(_activeFileTab===tab.key)?' active':'';
    var countHtml='';
    if(tab.key==='issues'){
      var ij=_knownFiles['issues.json'];
      if(ij)countHtml='<span class="badge-count">?</span>';
    }
    html+='<div class="file-tab'+cls+'" data-tab="'+tab.key+'" data-run="'+runId+'">'+tab.label+countHtml+'</div>';
  });
  tabsEl.innerHTML=html;
  tabsEl.onclick=function(e){
    var t=e.target.closest('.file-tab');
    if(!t)return;
    switchFileTab(t.getAttribute('data-tab'),t.getAttribute('data-run'));
  };
  if(!_activeFileTab&&tabsEl.children.length){
    var firstTab=tabsEl.children[0].getAttribute('data-tab');
    switchFileTab(firstTab,runId);
  }
}

function switchFileTab(tabKey,runId){
  _activeFileTab=tabKey;
  var tabs=document.querySelectorAll('.file-tab');
  tabs.forEach(function(t){t.classList.toggle('active',t.getAttribute('data-tab')===tabKey);});
  var tabDef=FILE_TABS.find(function(t){return t.key===tabKey;});
  if(!tabDef)return;
  var fileToLoad=null;
  for(var i=0;i<tabDef.files.length;i++){
    if(_knownFiles[tabDef.files[i]]){fileToLoad=tabDef.files[i];break;}
  }
  if(!fileToLoad)return;
  fetch('/api/runs/'+runId+'/file/'+fileToLoad).then(function(r){return r.text();}).then(function(content){
    renderFileContent(tabKey,fileToLoad,content);
  }).catch(function(){});
}

function renderFileContent(tabKey,filename,content){
  var viewer=document.getElementById('fileViewer');
  if(filename.endsWith('.html')){
    var iframe=document.createElement('iframe');
    iframe.style.cssText='width:100%;border:none;border-radius:6px;min-height:80vh;background:#fff;';
    iframe.sandbox='allow-same-origin';
    viewer.innerHTML='';
    viewer.appendChild(iframe);
    var doc=iframe.contentDocument||iframe.contentWindow.document;
    doc.open();doc.write(content);doc.close();
    try{iframe.style.height=doc.documentElement.scrollHeight+'px';}catch(x){iframe.style.height='80vh';}
  }else if(filename.endsWith('.md')){
    viewer.innerHTML=renderMarkdown(content);
  }else if(filename==='task_analysis.json'){
    viewer.innerHTML=renderTaskAnalysis(content);
  }else if(filename==='issues.json'){
    viewer.innerHTML=renderIssues(content);
  }else if(filename==='validations.json'){
    viewer.innerHTML=renderValidations(content);
  }else if(filename==='scorecard.json'){
    viewer.innerHTML=renderScorecard(content);
  }else if(filename==='fact_check.json'){
    viewer.innerHTML=renderFactCheck(content);
  }else if(filename.endsWith('.json')){
    viewer.innerHTML='<pre><code>'+esc(content)+'</code></pre>';
  }else{
    viewer.innerHTML='<pre>'+esc(content)+'</pre>';
  }
}

function renderMarkdown(text){
  if(!text)return '';
  var h=text;
  h=h.replace(/^#### (.+)$/gm,'<h4>$1</h4>');
  h=h.replace(/^### (.+)$/gm,'<h3>$1</h3>');
  h=h.replace(/^## (.+)$/gm,'<h2>$1</h2>');
  h=h.replace(/^# (.+)$/gm,'<h1>$1</h1>');
  h=h.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  h=h.replace(/\*(.+?)\*/g,'<em>$1</em>');
  h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
  h=h.replace(/^\|(.+)\|$/gm,function(m,row){
    var cells=row.split('|').map(function(c){return '<td>'+c.trim()+'</td>';}).join('');
    return '<tr>'+cells+'</tr>';
  });
  h=h.replace(/((?:<tr>.*<\/tr>\\n?)+)/g,function(m){return '<table style="width:100%;border-collapse:collapse;margin:0.5rem 0;">'+m+'</table>';});
  h=h.replace(/^- (.+)$/gm,'<li>$1</li>');
  h=h.replace(/(<li>[\s\S]*?<\/li>(\\n|$))+/g,function(m){return '<ul>'+m+'</ul>';});
  h=h.replace(/^> (.+)$/gm,'<blockquote>$1</blockquote>');
  h=h.replace(/^---$/gm,'<hr style="border:none;border-top:1px solid var(--border);margin:0.75rem 0;">');
  h=h.replace(/\\n{2,}/g,'</p><p>');
  h='<p>'+h+'</p>';
  h=h.replace(/<p>\s*<(h[1-4]|ul|blockquote|hr|table|pre)/g,'<$1');
  h=h.replace(/<\/((h[1-4])|ul|blockquote|table|pre)>\s*<\/p>/g,'</$1>');
  h=h.replace(/<p>\s*<\/p>/g,'');
  return h;
}

function renderTaskAnalysis(raw){
  try{
    var d=JSON.parse(raw);
    var scoreColor=d.clarity_score>=7?'var(--green)':d.clarity_score>=4?'var(--yellow)':'var(--red)';
    var statusBg=d.clarity_status==='clear'?'#14532d':d.clarity_status==='needs_clarification'?'#713f12':'#7f1d1d';
    var statusColor=d.clarity_status==='clear'?'#86efac':d.clarity_status==='needs_clarification'?'#fde047':'#fca5a5';
    var h='<div class="ta-header">';
    h+='<span class="ta-key">'+esc(d.task_key||'-')+'</span>';
    h+='<span class="ta-status" style="background:'+statusBg+';color:'+statusColor+';">'+esc(d.clarity_status||'-').replace(/_/g,' ')+'</span>';
    h+='<span class="ta-score" style="color:'+scoreColor+';">'+(d.clarity_score||0).toFixed(1)+'<span style="font-size:0.8rem;color:var(--dim);">/10</span></span>';
    h+='</div>';
    h+='<div class="ta-grid">';
    h+='<div class="task-card"><div class="tc-label">Oncelik</div><div class="tc-value">'+esc(d.priority||'-')+'</div></div>';
    h+='<div class="task-card"><div class="tc-label">Durum</div><div class="tc-value">'+esc(d.status||'-')+'</div></div>';
    h+='<div class="task-card"><div class="tc-label">Reporter</div><div class="tc-value">'+esc(d.reporter||'-')+'</div></div>';
    h+='<div class="task-card"><div class="tc-label">Assignee</div><div class="tc-value">'+esc(d.assignee||'-')+'</div></div>';
    h+='</div>';
    h+='<div class="ta-field"><div class="ta-field-label">Ozet</div><div class="ta-field-value">'+esc(d.summary||'-')+'</div></div>';
    if(d.description){
      var desc=(d.description||'').substring(0,600);
      h+='<div class="ta-field"><div class="ta-field-label">Aciklama</div><div class="ta-field-value" style="white-space:pre-wrap;max-height:200px;overflow-y:auto;">'+esc(desc)+(d.description.length>600?'...':'')+'</div></div>';
    }
    if(d.acceptance_criteria&&d.acceptance_criteria.length){
      h+='<div class="ta-field"><div class="ta-field-label">Kabul Kriterleri</div><ul style="margin:0.25rem 0 0 1rem;font-size:0.85rem;">';
      d.acceptance_criteria.forEach(function(ac){h+='<li>'+esc(ac)+'</li>';});
      h+='</ul></div>';
    }
    if(d.missing_fields&&d.missing_fields.length){
      h+='<div class="ta-field"><div class="ta-field-label" style="color:var(--red);">Eksik Alanlar</div><div class="ta-tags">';
      d.missing_fields.forEach(function(f){h+='<span class="ta-tag missing">'+esc(f)+'</span>';});
      h+='</div></div>';
    }
    if(d.impacted_areas&&d.impacted_areas.length&&d.impacted_areas[0]!=='ToBePlanned'){
      h+='<div class="ta-field"><div class="ta-field-label">Etkilenen Alanlar</div><div class="ta-tags">';
      d.impacted_areas.forEach(function(a){h+='<span class="ta-tag">'+esc(a)+'</span>';});
      h+='</div></div>';
    }
    if(d.labels&&d.labels.length){
      h+='<div class="ta-field"><div class="ta-field-label">Etiketler</div><div class="ta-tags">';
      d.labels.forEach(function(l){h+='<span class="ta-tag">'+esc(l)+'</span>';});
      h+='</div></div>';
    }
    if(d.dependencies&&d.dependencies!=='none'){
      h+='<div class="ta-field"><div class="ta-field-label">Bagimliliklar</div><div class="ta-field-value">'+esc(d.dependencies)+'</div></div>';
    }
    if(d.created_date){
      h+='<div style="font-size:0.72rem;color:var(--dim);margin-top:0.5rem;">Olusturulma: '+esc(d.created_date)+'</div>';
    }
    return h;
  }catch(e){return '<pre>'+esc(raw)+'</pre>';}
}

function sevClass(s){s=(s||'').toLowerCase();return s==='critical'?'severity-critical':s==='high'?'severity-high':s==='medium'?'severity-medium':'severity-low';}
function sevCardClass(s){s=(s||'').toLowerCase();return s==='critical'?'sev-critical':s==='high'?'sev-high':s==='medium'?'sev-medium':'sev-low';}
function sevDot(s){s=(s||'').toLowerCase();return s==='critical'?'#ef4444':s==='high'?'#f97316':s==='medium'?'#eab308':'#94a3b8';}

function renderIssues(raw){
  try{
    var arr=JSON.parse(raw);
    if(!arr||!arr.length)return '<div class="empty">Sorun bulunamadi.</div>';
    var counts={critical:0,high:0,medium:0,low:0};
    arr.forEach(function(i){var s=(i.severity||'low').toLowerCase();counts[s]=(counts[s]||0)+1;});
    var summaryH='<div style="display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap;">';
    ['critical','high','medium','low'].forEach(function(sev){
      if(counts[sev]){
        summaryH+='<span style="display:inline-flex;align-items:center;gap:0.3rem;padding:0.25rem 0.6rem;border-radius:4px;font-size:0.78rem;font-weight:600;background:'+sevDot(sev)+'22;color:'+sevDot(sev)+';"><span style="width:8px;height:8px;border-radius:50%;background:'+sevDot(sev)+';display:inline-block;"></span>'+sev.toUpperCase()+' '+counts[sev]+'</span>';
      }
    });
    summaryH+='</div>';
    var badges=document.querySelectorAll('.badge-count');
    badges.forEach(function(b){b.textContent=arr.length;});
    var cardsH='';
    arr.forEach(function(issue){
      var sc=sevCardClass(issue.severity);
      cardsH+='<div class="issue-card '+sc+'">';
      cardsH+='<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">';
      cardsH+='<div class="issue-title">'+esc(issue.title||'')+'</div>';
      cardsH+='<span style="flex-shrink:0;font-size:0.68rem;padding:0.15rem 0.45rem;border-radius:3px;font-weight:700;background:'+sevDot(issue.severity)+'22;color:'+sevDot(issue.severity)+';">'+esc((issue.severity||'').toUpperCase())+'</span>';
      cardsH+='</div>';
      cardsH+='<div class="issue-meta">';
      cardsH+='<span style="font-weight:600;color:var(--accent);">'+esc(issue.id||'')+'</span>';
      if(issue.category)cardsH+='<span>'+esc(issue.category).replace(/_/g,' ')+'</span>';
      if(issue.source_pass)cardsH+='<span style="opacity:0.7;">'+esc(issue.source_pass)+'</span>';
      if(issue.affected_section)cardsH+='<span>Bolum: '+esc(issue.affected_section)+'</span>';
      if(issue.consensus_score!=null)cardsH+='<span>Consensus: '+(issue.consensus_score*100).toFixed(0)+'%</span>';
      cardsH+='</div>';
      if(issue.rationale){
        cardsH+='<div class="issue-desc">'+esc(issue.rationale)+'</div>';
      }
      if(issue.evidence_quote){
        cardsH+='<blockquote style="margin-top:0.35rem;font-size:0.8rem;color:var(--dim);border-left:2px solid var(--border);padding-left:0.5rem;white-space:pre-wrap;max-height:80px;overflow-y:auto;">'+esc(issue.evidence_quote)+'</blockquote>';
      }
      if(issue.proposed_fix){
        cardsH+='<div class="issue-fix"><strong style="color:var(--green);">Onerilen Fix:</strong> '+esc(issue.proposed_fix)+'</div>';
      }
      cardsH+='</div>';
    });
    return summaryH+cardsH;
  }catch(e){return '<pre>'+esc(raw)+'</pre>';}
}

function renderValidations(raw){
  try{
    var arr=JSON.parse(raw);
    if(!arr||!arr.length)return '<div class="empty">Validasyon yok.</div>';
    var h='';
    arr.forEach(function(v){
      var dc=v.decision==='valid'?'var(--green)':v.decision==='invalid'?'var(--red)':'var(--yellow)';
      var icon=v.decision==='valid'?'&#10003;':v.decision==='invalid'?'&#10007;':'?';
      h+='<div class="issue-card" style="border-left-color:'+dc+';">';
      h+='<div style="display:flex;align-items:center;gap:0.75rem;">';
      h+='<span style="font-size:1.1rem;color:'+dc+';font-weight:700;">'+icon+'</span>';
      h+='<span style="font-weight:600;color:var(--accent);">'+esc(v.issue_id||'')+'</span>';
      h+='<span style="color:'+dc+';font-weight:600;font-size:0.85rem;">'+esc(v.decision||'').toUpperCase()+'</span>';
      if(v.confidence!=null)h+='<span style="font-size:0.78rem;color:var(--dim);">Guven: '+(v.confidence*100).toFixed(0)+'%</span>';
      h+='</div>';
      if(v.reason)h+='<div style="margin-top:0.35rem;font-size:0.82rem;color:#cbd5e1;">'+esc(v.reason)+'</div>';
      h+='</div>';
    });
    return h;
  }catch(e){return '<pre>'+esc(raw)+'</pre>';}
}

function renderScorecard(raw){
  try{
    var d=JSON.parse(raw);
    var ds=d.dimension_scores||{};
    var dims=['correctness','completeness','implementability','consistency','edge_case_coverage','testability','risk_awareness','clarity'];
    var dimLabels={'correctness':'Dogruluk','completeness':'Tamlk','implementability':'Uygulanabirlik','consistency':'Tutarllk','edge_case_coverage':'Edge Case','testability':'Test Edilebirlrk','risk_awareness':'Risk Farkndal','clarity':'Netlk'};
    var passed=d.overall_score!=null&&d.overall_score>=8;
    var h='<div class="task-card" style="border-left:4px solid '+(passed?'var(--green)':'var(--red)')+';display:flex;justify-content:space-between;align-items:center;">';
    h+='<span class="badge '+(passed?'badge-pass':'badge-fail')+'" style="font-size:1rem;padding:0.3rem 0.8rem;">'+(passed?'GECTI':'KALDI')+'</span>';
    h+='<span style="font-size:2rem;font-weight:700;color:'+(passed?'var(--green)':'var(--red)')+';">'+(d.overall_score||0).toFixed(1)+'/10</span></div>';
    if(d.confidence_in_scoring!=null){
      h+='<div style="font-size:0.78rem;color:var(--dim);margin-top:0.4rem;text-align:right;">Guven: '+(d.confidence_in_scoring*100).toFixed(0)+'%</div>';
    }
    h+='<div class="dim-bar" style="margin-top:0.75rem;">';
    dims.forEach(function(dim){
      var v=ds[dim]||0;
      var c=v>=8?'var(--green)':v>=6?'var(--yellow)':'var(--red)';
      h+='<div class="dim-item">';
      h+='<div class="dim-name">'+(dimLabels[dim]||dim.replace(/_/g,' '))+'</div>';
      h+='<div class="dim-score" style="color:'+c+';">'+v.toFixed(1)+'</div>';
      h+='<div class="dim-bar-track"><div class="dim-bar-fill" style="width:'+v*10+'%;background:'+c+';"></div></div>';
      h+='</div>';
    });
    h+='</div>';
    if(d.blocking_reasons&&d.blocking_reasons.length){
      h+='<div style="margin-top:0.75rem;"><div style="font-size:0.75rem;color:var(--red);font-weight:600;margin-bottom:0.3rem;">Engelleyici Nedenler</div>';
      d.blocking_reasons.forEach(function(r){h+='<div style="font-size:0.82rem;color:#fca5a5;padding:0.2rem 0;padding-left:0.75rem;border-left:2px solid var(--red);">'+esc(r)+'</div>';});
      h+='</div>';
    }
    if(d.key_strengths&&d.key_strengths.length){
      h+='<details style="margin-top:0.75rem;"><summary style="color:var(--green);cursor:pointer;font-size:0.82rem;font-weight:600;">Guc Yonleri ('+d.key_strengths.length+')</summary>';
      d.key_strengths.forEach(function(s){h+='<div style="font-size:0.82rem;color:#86efac;padding:0.25rem 0 0.25rem 0.75rem;border-left:2px solid var(--green);">'+esc(s)+'</div>';});
      h+='</details>';
    }
    if(d.remaining_concerns&&d.remaining_concerns.length){
      h+='<details style="margin-top:0.5rem;"><summary style="color:var(--yellow);cursor:pointer;font-size:0.82rem;font-weight:600;">Eksikler ('+d.remaining_concerns.length+')</summary>';
      d.remaining_concerns.forEach(function(c2){h+='<div style="font-size:0.82rem;color:#fde047;padding:0.25rem 0 0.25rem 0.75rem;border-left:2px solid var(--yellow);">'+esc(c2)+'</div>';});
      h+='</details>';
    }
    if(d.meta_judge_result){
      var mj=d.meta_judge_result;
      h+='<details style="margin-top:0.5rem;"><summary style="color:var(--dim);cursor:pointer;font-size:0.82rem;">Meta Judge: '+esc((mj.verdict||'').toUpperCase())+'</summary>';
      if(mj.reasoning)h+='<div style="font-size:0.82rem;color:#cbd5e1;margin-top:0.3rem;white-space:pre-wrap;">'+esc(mj.reasoning)+'</div>';
      h+='</details>';
    }
    return h;
  }catch(e){return '<pre>'+esc(raw)+'</pre>';}
}

function renderFactCheck(raw){
  try{
    var d=JSON.parse(raw);
    if(!d.items||!d.items.length){
      var summary=d.summary||'';
      if(summary){
        return '<div class="task-card"><div class="tc-label">Ozet</div><div class="tc-value" style="white-space:pre-wrap;">'+esc(summary)+'</div></div>';
      }
      return '<div class="empty">Fact-check verisi yok.</div>';
    }
    var confirmed=d.confirmed_count||0;
    var refuted=d.refuted_count||0;
    var uncertain=d.uncertain_count||0;
    var h='<div style="display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap;">';
    if(confirmed)h+='<span style="padding:0.2rem 0.6rem;border-radius:4px;font-size:0.78rem;font-weight:600;background:#14532d;color:#86efac;">Onaylandi '+confirmed+'</span>';
    if(refuted)h+='<span style="padding:0.2rem 0.6rem;border-radius:4px;font-size:0.78rem;font-weight:600;background:#7f1d1d;color:#fca5a5;">Cirsti '+refuted+'</span>';
    if(uncertain)h+='<span style="padding:0.2rem 0.6rem;border-radius:4px;font-size:0.78rem;font-weight:600;background:#713f12;color:#fde047;">Belirsiz '+uncertain+'</span>';
    h+='</div>';
    d.items.forEach(function(item){
      var vc=item.reality_verdict==='confirmed'?'var(--green)':item.reality_verdict==='refuted'?'var(--red)':'var(--yellow)';
      h+='<div class="issue-card" style="border-left-color:'+vc+';">';
      h+='<div style="display:flex;align-items:center;gap:0.75rem;">';
      h+='<span style="font-weight:600;color:var(--accent);">'+esc(item.issue_id||'')+'</span>';
      h+='<span style="color:'+vc+';font-weight:600;">'+esc((item.reality_verdict||'').toUpperCase())+'</span>';
      if(item.reality_score!=null)h+='<span style="font-size:0.78rem;color:var(--dim);">'+(item.reality_score*100).toFixed(0)+'%</span>';
      h+='</div>';
      if(item.rationale||item.reasoning)h+='<div style="margin-top:0.3rem;font-size:0.82rem;color:#cbd5e1;">'+esc(item.rationale||item.reasoning)+'</div>';
      h+='</div>';
    });
    if(d.approved_fix_ids&&d.approved_fix_ids.length){
      h+='<div style="margin-top:0.75rem;font-size:0.82rem;color:var(--green);">Onaylanan Fix IDleri: '+d.approved_fix_ids.map(esc).join(', ')+'</div>';
    }
    return h;
  }catch(e){return '<pre>'+esc(raw)+'</pre>';}
}
</script>
</body>
</html>"""


def _simulator_html() -> str:
    return """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Simulator - Doc Quality Gate</title>
<style>
  :root { --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; --orange: #f97316; --purple: #a855f7; --cyan: #06b6d4; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  nav { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--accent); }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.9rem; }
  nav a:hover, nav a.active { color: var(--text); }
  .container { max-width: 1200px; margin: 1.5rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
  .subtitle { color: var(--dim); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .controls { display: grid; grid-template-columns: 280px 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
  .panel h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim); margin-bottom: 1rem; }
  .opt-group { margin-bottom: 1rem; }
  .opt-group label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.88rem; cursor: pointer; padding: 0.3rem 0; }
  .opt-group input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); }
  .opt-group select { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 0.5rem; color: var(--text); font-size: 0.85rem; margin-top: 0.5rem; }
  .opt-desc { font-size: 0.78rem; color: var(--dim); margin-top: 0.15rem; padding-left: 1.5rem; }
  .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
  .metric-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; text-align: center; }
  .metric-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim); margin-bottom: 0.3rem; }
  .metric-value { font-size: 1.6rem; font-weight: 700; }
  .metric-sub { font-size: 0.75rem; color: var(--dim); margin-top: 0.2rem; }
  .gantt-section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .gantt-section h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim); margin-bottom: 1rem; }
  .gantt-container { position: relative; min-height: 300px; }
  .gantt-row { display: grid; grid-template-columns: 140px 1fr 80px; gap: 0.5rem; align-items: center; padding: 0.35rem 0; border-bottom: 1px solid rgba(51,65,85,0.5); }
  .gantt-row:last-child { border-bottom: none; }
  .gantt-label { font-size: 0.78rem; color: var(--dim); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gantt-bar-area { position: relative; height: 24px; }
  .gantt-bar { position: absolute; height: 100%; border-radius: 4px; min-width: 2px; display: flex; align-items: center; padding-left: 6px; font-size: 0.68rem; font-weight: 600; color: #fff; overflow: hidden; white-space: nowrap; transition: all 0.3s; cursor: pointer; }
  .gantt-bar:hover { filter: brightness(1.2); }
  .gantt-bar.skipped { background: var(--border) !important; opacity: 0.3; }
  .gantt-bar.early-exit { border: 2px dashed var(--yellow); }
  .gantt-dur { font-size: 0.78rem; color: var(--dim); text-align: right; }
  .gantt-time-axis { display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--dim); margin-top: 0.5rem; padding-left: 148px; }
  .comparison-section { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .comparison-section h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--dim); margin-bottom: 1rem; }
  .comp-table { width: 100%; border-collapse: collapse; }
  .comp-table th, .comp-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); text-align: left; font-size: 0.85rem; }
  .comp-table th { color: var(--dim); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .comp-table tr:hover { background: rgba(59,130,246,0.05); }
  .bar-h { height: 8px; background: var(--border); border-radius: 4px; width: 100%; min-width: 80px; }
  .bar-h-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
  .tag { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.7rem; font-weight: 600; }
  .tag-green { background: #14532d; color: #86efac; }
  .tag-yellow { background: #713f12; color: #fde047; }
  .tag-red { background: #7f1d1d; color: #fca5a5; }
  .tag-blue { background: #1e3a5f; color: #93c5fd; }
  .tag-purple { background: #3b1f6e; color: #c4b5fd; }
</style>
</head>
<body>
<nav>
  <div class="brand">DQG</div>
  <a href="/dashboard">Dashboard</a>
  <a href="/runs">Calismalar</a>
  <a href="/settings">Ayarlar</a>
  <a href="/smoke">Smoke Test</a>
  <a href="/simulator" class="active">Simulator</a>
</nav>
<div class="container">
  <h1>Pipeline Simulator</h1>
  <p class="subtitle">Optimizasyon stratejilerinin latency ve kalite uzerindeki etkisini gorun.</p>

  <div class="controls">
    <div class="panel">
      <h2>Stratejiler</h2>
      <div class="opt-group">
        <label><input type="radio" name="mode" value="preset" checked onchange="onModeChange()"> Hazir Profil</label>
        <select id="presetProfile" onchange="recalculate()">
          <option value="current">Mevcut Pipeline (14 asama)</option>
          <option value="fast_track">Fast Track (hafif degisiklikler)</option>
          <option value="standard" selected>Standard (dengeli)</option>
          <option value="deep">Deep (tam analiz)</option>
        </select>
      </div>
      <div class="opt-group">
        <label><input type="radio" name="mode" value="custom" onchange="onModeChange()"> Ozel Konfigurasyon</label>
      </div>
      <div id="customOpts" style="display:none; margin-top:0.75rem;">
        <div class="opt-group">
          <label><input type="checkbox" id="optEarlyExit" checked onchange="recalculate()"> A. Early Exit</label>
          <div class="opt-desc">Kritik hata varsa pipeline'i erken durdur</div>
        </div>
        <div class="opt-group">
          <label><input type="checkbox" id="optFanOut" checked onchange="recalculate()"> B. Fan-out Paralelizasyon</label>
          <div class="opt-desc">4 asamayi ayni anda calistir</div>
        </div>
        <div class="opt-group">
          <label><input type="checkbox" id="optPruning" checked onchange="recalculate()"> C. Budama (Meta-Judge + Fact-Check)</label>
          <div class="opt-desc">Azalan verimli asamalari kaldir</div>
        </div>
        <div class="opt-group">
          <label><input type="checkbox" id="optProject" checked onchange="recalculate()"> Proje cross-reference var</label>
          <div class="opt-desc">Proje yolu verildiginde domain analizi yapilir</div>
        </div>
      </div>
    </div>

    <div>
      <div class="metrics">
        <div class="metric-card">
          <div class="metric-label">Tahmini Sure</div>
          <div class="metric-value" id="metricLatency" style="color:var(--purple);">-</div>
          <div class="metric-sub" id="metricLatencySub"></div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Tasarruf</div>
          <div class="metric-value" id="metricSavings" style="color:var(--green);">-</div>
          <div class="metric-sub" id="metricSavingsSub"></div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Kalite Guveni</div>
          <div class="metric-value" id="metricQuality">-</div>
          <div class="metric-sub" id="metricQualitySub"></div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Asama Sayisi</div>
          <div class="metric-value" id="metricStages" style="color:var(--cyan);">-</div>
          <div class="metric-sub">toplam calisan</div>
        </div>
      </div>
    </div>
  </div>

  <div class="gantt-section">
    <h2>Pipeline Timeline (Gantt Chart)</h2>
    <div class="gantt-container" id="ganttChart">
      <div style="color:var(--dim);text-align:center;padding:2rem;">Hesaplaniyor...</div>
    </div>
  </div>

  <div class="comparison-section">
    <h2>Profil Karsilastirma</h2>
    <table class="comp-table">
      <thead><tr><th>Profil</th><th>Tahmini Sure</th><th>Tasarruf</th><th>Kalite Guveni</th><th>Asama</th><th>Stratejiler</th></tr></thead>
      <tbody id="compBody"></tbody>
    </table>
  </div>
</div>
<script>
var CURRENT_DATA = null;
var STAGE_COLORS = {
  ingest: '#3b82f6', complexity_router: '#06b6d4',
  domain_context: '#8b5cf6', cross_reference: '#6366f1', deep_analysis: '#7c3aed',
  critic_a_multi: '#f97316', critic_b_multi: '#fb923c',
  critic_a_judge: '#a855f7', critic_b_judge: '#c084fc',
  dedupe: '#64748b', validate: '#22c55e', revise: '#10b981',
  score: '#eab308', meta_judge: '#ef4444', fact_check: '#f43f5e', report: '#94a3b8'
};
var STAGE_LABELS = {
  ingest: 'Ingest', complexity_router: 'Complexity Router',
  domain_context: 'Domain Context', cross_reference: 'Cross Reference', deep_analysis: 'Deep Analysis',
  critic_a_multi: 'Critic A (multi)', critic_b_multi: 'Critic B (multi)',
  critic_a_judge: 'Critic A Judge', critic_b_judge: 'Critic B Judge',
  dedupe: 'Dedup', validate: 'Validate', revise: 'Revise',
  score: 'Score', meta_judge: 'Meta Judge', fact_check: 'Fact Check', report: 'Report'
};

function onModeChange() {
  var mode = document.querySelector('input[name="mode"]:checked').value;
  document.getElementById('customOpts').style.display = mode === 'custom' ? 'block' : 'none';
  document.getElementById('presetProfile').disabled = mode === 'custom';
  recalculate();
}

async function recalculate() {
  var mode = document.querySelector('input[name="mode"]:checked').value;
  var payload;
  if (mode === 'preset') {
    payload = { profile: document.getElementById('presetProfile').value, has_project: true };
  } else {
    payload = {
      profile: 'custom',
      early_exit: document.getElementById('optEarlyExit').checked,
      fan_out: document.getElementById('optFanOut').checked,
      pruning: document.getElementById('optPruning').checked,
      has_project: document.getElementById('optProject').checked,
    };
  }

  try {
    var resp = await fetch('/api/simulator/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CURRENT_DATA = await resp.json();
    renderMetrics(CURRENT_DATA);
    renderGantt(CURRENT_DATA);
  } catch (e) {
    console.error(e);
  }
}

function fmtTime(seconds) {
  if (seconds < 60) return seconds.toFixed(1) + 's';
  var m = Math.floor(seconds / 60);
  var s = Math.round(seconds % 60);
  return m + 'dk ' + s + 's';
}

function renderMetrics(d) {
  var latencyEl = document.getElementById('metricLatency');
  var savingsEl = document.getElementById('metricSavings');
  var qualityEl = document.getElementById('metricQuality');
  var stagesEl = document.getElementById('metricStages');

  latencyEl.textContent = fmtTime(d.total_latency_seconds);
  document.getElementById('metricLatencySub').textContent = d.profile + ' profili';

  var savings = d.savings_vs_current || 0;
  savingsEl.textContent = savings > 0 ? '%' + savings : '-%0';
  savingsEl.style.color = savings > 40 ? 'var(--green)' : savings > 20 ? 'var(--yellow)' : 'var(--dim)';
  document.getElementById('metricSavingsSub').textContent = savings > 0 ? 'mevcut pipeline\'a gore' : '';

  var q = d.quality_confidence || 0;
  qualityEl.textContent = '%' + Math.round(q * 100);
  qualityEl.style.color = q >= 0.95 ? 'var(--green)' : q >= 0.85 ? 'var(--yellow)' : 'var(--red)';
  document.getElementById('metricQualitySub').textContent = q >= 0.95 ? 'Yuksek guven' : q >= 0.85 ? 'Orta guven' : 'Dusuk guven';

  stagesEl.textContent = d.stages_count || 0;
}

function renderGantt(d) {
  var container = document.getElementById('ganttChart');
  var timeline = d.timeline || [];
  if (!timeline.length) { container.innerHTML = '<div style="color:var(--dim);text-align:center;padding:2rem;">Veri yok</div>'; return; }

  var maxTime = 0;
  timeline.forEach(function(s) { var end = s.start + s.duration; if (end > maxTime) maxTime = end; });
  maxTime = Math.max(maxTime, 1);

  var allStages = ['ingest','complexity_router','domain_context','cross_reference','deep_analysis','critic_a_multi','critic_b_multi','critic_a_judge','critic_b_judge','dedupe','validate','revise','score','meta_judge','fact_check','report'];
  var activeSet = new Set(d.active_stages || []);

  var html = '';
  allStages.forEach(function(stageId) {
    var isActive = activeSet.has(stageId);
    var stageData = timeline.find(function(s) { return s.stage === stageId; });
    var label = STAGE_LABELS[stageId] || stageId;
    var color = STAGE_COLORS[stageId] || '#64748b';

    if (!isActive) {
      html += '<div class="gantt-row" style="opacity:0.25;">';
      html += '<div class="gantt-label">' + label + '</div>';
      html += '<div class="gantt-bar-area"></div>';
      html += '<div class="gantt-dur" style="font-size:0.7rem;">atlandi</div>';
      html += '</div>';
      return;
    }

    if (!stageData) return;

    var leftPct = (stageData.start / maxTime * 100).toFixed(2);
    var widthPct = (stageData.duration / maxTime * 100).toFixed(2);
    var durText = stageData.duration < 1 ? (stageData.duration * 1000).toFixed(0) + 'ms' : stageData.duration.toFixed(1) + 's';
    var cls = stageData.early_exit ? ' early-exit' : '';
    var title = label + ': ' + durText + ' (' + stageData.start.toFixed(1) + 's - ' + (stageData.start + stageData.duration).toFixed(1) + 's)';

    html += '<div class="gantt-row">';
    html += '<div class="gantt-label">' + label + '</div>';
    html += '<div class="gantt-bar-area">';
    html += '<div class="gantt-bar' + cls + '" style="left:' + leftPct + '%;width:' + widthPct + '%;background:' + color + ';" title="' + title + '">';
    if (stageData.duration / maxTime > 0.08) html += durText;
    html += '</div></div>';
    html += '<div class="gantt-dur">' + durText + '</div>';
    html += '</div>';
  });

  var axisTicks = 5;
  var axisHtml = '<div class="gantt-time-axis">';
  for (var i = 0; i <= axisTicks; i++) {
    axisHtml += '<span>' + fmtTime(maxTime / axisTicks * i) + '</span>';
  }
  axisHtml += '</div>';

  container.innerHTML = html + axisHtml;
}

async function loadComparison() {
  try {
    var resp = await fetch('/api/simulator/comparison');
    var data = await resp.json();
    var tbody = document.getElementById('compBody');
    var maxLatency = 0;
    Object.values(data).forEach(function(d) { if (d.total_latency_seconds > maxLatency) maxLatency = d.total_latency_seconds; });
    maxLatency = Math.max(maxLatency, 1);

    var labels = { current: 'Mevcut Pipeline', fast_track: 'Fast Track', standard: 'Standard', deep: 'Deep', custom_all: 'Ozel (Tumu)' };
    var html = '';
    Object.entries(data).forEach(function(entry) {
      var key = entry[0], d = entry[1];
      var latency = d.total_latency_seconds;
      var savings = d.savings_vs_current || 0;
      var quality = d.quality_confidence || 0;
      var stages = d.stages_count || 0;
      var barWidth = (latency / maxLatency * 100).toFixed(1);
      var barColor = savings > 40 ? 'var(--green)' : savings > 20 ? 'var(--yellow)' : 'var(--red)';
      var qColor = quality >= 0.95 ? 'tag-green' : quality >= 0.85 ? 'tag-yellow' : 'tag-red';
      var savingsTag = savings > 40 ? 'tag-green' : savings > 20 ? 'tag-yellow' : 'tag-blue';
      var strategies = [];
      if (key === 'current') strategies.push('<span class="tag tag-blue">Mevcut</span>');
      if (key === 'fast_track') strategies.push('<span class="tag tag-green">Dynamic Route</span><span class="tag tag-purple">Budama</span>');
      if (key === 'standard') strategies.push('<span class="tag tag-green">Fan-out</span><span class="tag tag-yellow">Early Exit</span><span class="tag tag-purple">Budama</span>');
      if (key === 'deep') strategies.push('<span class="tag tag-blue">Tam Pipeline</span>');
      if (key === 'custom_all') strategies.push('<span class="tag tag-green">Fan-out</span><span class="tag tag-yellow">Early Exit</span><span class="tag tag-purple">Budama</span>');

      html += '<tr>';
      html += '<td><strong>' + (labels[key] || key) + '</strong></td>';
      html += '<td><div style="display:flex;align-items:center;gap:0.5rem;"><div class="bar-h"><div class="bar-h-fill" style="width:' + barWidth + '%;background:' + barColor + ';"></div></div><span style="white-space:nowrap;">' + fmtTime(latency) + '</span></div></td>';
      html += '<td><span class="tag ' + savingsTag + '">' + (savings > 0 ? '%' + savings : '-') + '</span></td>';
      html += '<td><span class="tag ' + qColor + '">% ' + Math.round(quality * 100) + '</span></td>';
      html += '<td>' + stages + '</td>';
      html += '<td>' + strategies.join(' ') + '</td>';
      html += '</tr>';
    });
    tbody.innerHTML = html;
  } catch (e) {
    console.error(e);
  }
}

recalculate();
loadComparison();
</script>
</body>
</html>"""


def _smoke_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smoke Test - Doc Quality Gate</title>
<style>
  :root { --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  nav { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--accent); }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.9rem; }
  nav a:hover, nav a.active { color: var(--text); }
  .container { max-width: 960px; margin: 2rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.6rem; margin-bottom: 1.5rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
  button { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 0.7rem 1.5rem; font-size: 0.95rem; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
  button:hover { opacity: 0.9; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 0.5rem; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  th, td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); text-align: left; font-size: 0.9rem; }
  th { color: var(--dim); font-weight: 500; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  .ok { color: var(--green); }
  .fail { color: var(--red); }
  .pending { color: var(--dim); }
</style>
</head>
<body>
<nav>
  <div class="brand">DQG</div>
  <a href="/dashboard">Dashboard</a>
  <a href="/runs">Runs</a>
  <a href="/settings">Settings</a>
  <a href="/smoke" class="active">Smoke Test</a>
  <a href="/simulator">Simulator</a>
</nav>
<div class="container">
  <h1>Smoke Test</h1>
  <div class="card">
    <p style="color:var(--dim);margin-bottom:1rem;">Verify LiteLLM proxy connectivity, model availability, and Promptfoo integration.</p>
    <button id="runBtn" onclick="runSmoke()">Run Smoke Test</button>
    <div id="statusMsg" style="margin-top:1rem;font-size:0.9rem;"></div>
  </div>
  <div id="resultsCard" class="card" style="display:none;">
    <table>
      <thead><tr><th>Check</th><th>Status</th><th>Details</th></tr></thead>
      <tbody id="resultsBody"></tbody>
    </table>
  </div>
</div>
<script>
async function runSmoke() {
  var btn = document.getElementById('runBtn');
  var status = document.getElementById('statusMsg');
  var card = document.getElementById('resultsCard');
  var tbody = document.getElementById('resultsBody');
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span>Running checks...';
  tbody.innerHTML = '';
  card.style.display = 'none';
  try {
    var resp = await fetch('/api/smoke');
    var data = await resp.json();
    var rows = '';
    Object.entries(data).forEach(function(entry) {
      var k = entry[0], v = entry[1];
      var ok = v.status === 'ok' || v.available === true;
      var cls = ok ? 'ok' : 'fail';
      var icon = ok ? '\\u2713' : '\\u2717';
      var detail = '';
      if (v.error) detail = v.error;
      else if (v.model) detail = v.model;
      else if (v.version) detail = 'v' + v.version;
      rows += '<tr><td><code>' + k + '</code></td><td class="' + cls + '">' + icon + ' ' + (ok ? 'OK' : 'FAIL') + '</td><td style="color:var(--dim);">' + detail + '</td></tr>';
    });
    tbody.innerHTML = rows;
    card.style.display = 'block';
    status.textContent = 'Done.';
  } catch(err) {
    status.innerHTML = '<span class="fail">Error: ' + err.message + '</span>';
  } finally {
    btn.disabled = false;
  }
}
</script>
</body>
</html>"""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smoke Test - Doc Quality Gate</title>
<style>
  :root { --bg: #0f172a; --surface: #1e293b; --border: #334155; --text: #e2e8f0; --dim: #94a3b8; --accent: #3b82f6; --green: #22c55e; --red: #ef4444; --yellow: #eab308; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  nav { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--accent); }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.9rem; }
  nav a:hover, nav a.active { color: var(--text); }
  .container { max-width: 960px; margin: 2rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.6rem; margin-bottom: 1.5rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
  button { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: 0.7rem 1.5rem; font-size: 0.95rem; font-weight: 600; cursor: pointer; transition: opacity 0.15s; }
  button:hover { opacity: 0.9; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 0.5rem; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  th, td { padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); text-align: left; font-size: 0.9rem; }
  th { color: var(--dim); font-weight: 500; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  .ok { color: var(--green); }
  .fail { color: var(--red); }
  .pending { color: var(--dim); }
</style>
</head>
<body>
<nav>
  <div class="brand">DQG</div>
  <a href="/dashboard">Dashboard</a>
  <a href="/runs">Runs</a>
  <a href="/settings">Settings</a>
  <a href="/smoke" class="active">Smoke Test</a>
</nav>
<div class="container">
  <h1>Smoke Test</h1>
  <div class="card">
    <p style="color:var(--dim);margin-bottom:1rem;">Verify LiteLLM proxy connectivity, model availability, and Promptfoo integration.</p>
    <button id="runBtn" onclick="runSmoke()">Run Smoke Test</button>
    <div id="statusMsg" style="margin-top:1rem;font-size:0.9rem;"></div>
  </div>
  <div id="resultsCard" class="card" style="display:none;">
    <table>
      <thead><tr><th>Check</th><th>Status</th><th>Details</th></tr></thead>
      <tbody id="resultsBody"></tbody>
    </table>
  </div>
</div>
<script>
async function runSmoke() {
  var btn = document.getElementById('runBtn');
  var status = document.getElementById('statusMsg');
  var card = document.getElementById('resultsCard');
  var tbody = document.getElementById('resultsBody');
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span>Running checks...';
  tbody.innerHTML = '';
  card.style.display = 'none';
  try {
    var resp = await fetch('/api/smoke');
    var data = await resp.json();
    var rows = '';
    Object.entries(data).forEach(function(entry) {
      var k = entry[0], v = entry[1];
      var ok = v.status === 'ok' || v.available === true;
      var cls = ok ? 'ok' : 'fail';
      var icon = ok ? '\\u2713' : '\\u2717';
      var detail = '';
      if (v.error) detail = v.error;
      else if (v.model) detail = v.model;
      else if (v.version) detail = 'v' + v.version;
      rows += '<tr><td><code>' + k + '</code></td><td class="' + cls + '">' + icon + ' ' + (ok ? 'OK' : 'FAIL') + '</td><td style="color:var(--dim);">' + detail + '</td></tr>';
    });
    tbody.innerHTML = rows;
    card.style.display = 'block';
    status.textContent = 'Done.';
  } catch(err) {
    status.innerHTML = '<span class="fail">Error: ' + err.message + '</span>';
  } finally {
    btn.disabled = false;
  }
}
</script>
</body>
</html>"""
