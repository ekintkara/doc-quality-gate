from __future__ import annotations

import json
import threading
import time
import traceback as _traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from app.config import (
    AppConfig,
    load_app_config,
    load_model_routing,
    load_threshold_config,
)
from app.integrations.litellm_client import LiteLLMClient
from app.integrations.promptfoo_runner import PromptfooRunner
from app.schemas import (
    RunArtifacts,
    RunMetadata,
)
from app.stages.complexity_router import ComplexityLevel, route_complexity
from app.stages.critic import run_critic_a_multi, run_critic_b_multi
from app.stages.critic_judge import judge_critic_runs
from app.stages.cross_reference import run_cross_reference
from app.stages.dedupe import deduplicate_issues
from app.stages.deep_analysis import format_analysis_for_validator, run_deep_analysis
from app.stages.document_generator import generate_document
from app.stages.domain_context import extract_domain_context
from app.stages.fact_check import (
    apply_approved_fixes,
    generate_fact_check_report_md,
    run_fact_check,
)
from app.stages.ingest import ingest_document
from app.stages.meta_judge import apply_meta_judge_adjustments, run_meta_judge
from app.stages.report import generate_reports
from app.stages.revise import get_valid_issues, revise_document
from app.stages.score import score_document
from app.stages.task_analyzer import analyze_task
from app.stages.validate import validate_issues
from app.utils.files import (
    create_run_dir,
    write_json,
    write_text,
)
from app.utils.token_tracker import TokenTracker
from app.web.log_stream import LogBroadcaster


class PipelineCancelledError(Exception):
    pass


def _check_cancel(cancel_event: Optional[threading.Event], run_id: str, stage: str):
    if cancel_event and cancel_event.is_set():
        _broadcast_stage(run_id, stage, "cancelled")
        _broadcast_done(run_id)
        raise PipelineCancelledError(f"Pipeline cancelled at stage: {stage}")


logger = structlog.get_logger("orchestrator")


def _broadcast_stage(run_id: str, stage: str, status: str, detail: str = ""):
    try:
        LogBroadcaster.get().push_pipeline_stage(run_id, stage, status, detail)
    except Exception:
        pass


def _broadcast_done(run_id: str, score=None, passed=None, turkish_summary=""):
    try:
        LogBroadcaster.get().push_pipeline_done(run_id, score, passed, turkish_summary)
    except Exception:
        pass


def _generate_turkish_summary(
    client: "LiteLLMClient",
    scorecard: "Scorecard",  # noqa: F821
    issues: list,
    validations: list,
    document_content: str,
) -> str:
    try:
        from app.schemas import ValidationDecision

        valid_count = sum(1 for v in validations if v.decision == ValidationDecision.VALID)
        critical_count = sum(1 for i in issues if i.severity.value == "critical")
        high_count = sum(1 for i in issues if i.severity.value == "high")
        ds = scorecard.dimension_scores.model_dump()
        weakest_dims = sorted(ds.items(), key=lambda x: x[1])[:3]
        weakest_str = ", ".join(f"{k.replace('_', ' ')}: {v}/10" for k, v in weakest_dims)

        issue_titles = [f"- [{i.severity.value}] {i.title}" for i in issues[:10]]

        meta_verdict = ""
        if scorecard.meta_judge_result:
            meta_verdict = f"\nMeta-Judge: {scorecard.meta_judge_result.verdict}"

        prompt = f"""Bu bir doküman kalite değerlendirme raporunun verileridir.
Bunu Türkçe olarak, kısa ve öz bir şekilde özetle.

SKOR: {scorecard.overall_score}/10
SONUÇ: {"GEÇTİ" if scorecard.passed else "KALDI"}
SONRAKİ ADIM: {scorecard.recommended_next_action.value}
TOPLAM SORUN: {len(issues)}
GEÇERLİ SORUNLAR: {valid_count}
KRİTİK: {critical_count}, YÜKSEK: {high_count}
EN ZAYIF BOYUTLAR: {weakest_str}
SCORER ÇALIŞMA SAYISI: {scorecard.scorer_run_count}
{meta_verdict}

SONUÇLAR:
{chr(10).join(issue_titles)}

Engelleyici nedenler: {", ".join(scorecard.blocking_reasons) if scorecard.blocking_reasons else "Yok"}

Lütfen şunu yaz:
1. Tek cümlede genel durum (geçti/kaldı, skor)
2. En önemli 3-5 sorunu madde olarak
3. Ne yapılması gerektiğini bir cümleyle

Sadece Türkçe yaz, İngilizce kelime kullanma."""

        model = client.resolve_model("critic_a")
        response = client.chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": "Sen bir doküman kalite uzmanısın. Türkçe kısa özetler yazarsın."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
            stage="turkish_summary",
        )
        summary = response.get("content", "").strip()
        if summary:
            return summary
    except Exception as e:
        logger.warning("turkish_summary_failed", error=str(e))
    score = scorecard.overall_score
    passed = "GEÇTİ" if scorecard.passed else "KALDI"
    return f"Skor: {score}/10 - {passed} | {len(issues)} sorun bulundu | {scorecard.recommended_next_action.value}"


class Orchestrator:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or load_app_config()
        self.token_tracker = TokenTracker()
        self.client = LiteLLMClient(self.config, token_tracker=self.token_tracker)
        pf_model = self.config.model_aliases.get("scorer_promptfoo", "fallback_general")
        self.promptfoo_runner = PromptfooRunner(self.config.config_dir, model_alias=pf_model)

    def run(
        self,
        file_path: str,
        doc_type: Optional[str] = None,
        project_path: Optional[str] = None,
        context_path: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        run_id: Optional[str] = None,
        run_dir: Optional[Path] = None,
        profile: Optional[str] = None,
    ) -> RunArtifacts:
        if not run_id or not run_dir:
            run_id, run_dir = create_run_dir(self.config.output_base_dir)
        pipeline_start = time.monotonic()

        logger.info(
            "pipeline_start",
            run_id=run_id,
            file=file_path,
            doc_type=doc_type,
            project_path=project_path,
            context_path=context_path,
            profile=profile,
        )

        model_aliases_used = dict(self.config.model_aliases)
        actual_models_used: dict[str, Optional[str]] = {}
        warnings: list[str] = []

        try:
            _check_cancel(cancel_event, run_id, "ingest")
            _broadcast_stage(run_id, "ingest", "running")
            content, resolved_type = ingest_document(file_path, doc_type)
            write_text(run_dir / "original.md", content)
            _broadcast_stage(run_id, "ingest", "done")

            threshold_config = load_threshold_config(self.config.config_dir, resolved_type.value)

            from app.config import get_pipeline_profile, load_pipeline_profile_config

            profile_config = load_pipeline_profile_config(self.config.config_dir)
            default_profile_name = profile_config.get("default_profile", "deep")

            selected_profile = profile or default_profile_name

            if selected_profile == "auto":
                _broadcast_stage(run_id, "complexity_router", "running")
                logger.info("stage_complexity_router", run_id=run_id)
                complexity_result = route_complexity(self.client, content, resolved_type.value)
                selected_profile = complexity_result.profile
                write_json(run_dir / "complexity_router.json", complexity_result.model_dump())
                actual_models_used["complexity_router"] = self.client.resolve_model("critic_a")
                _broadcast_stage(
                    run_id, "complexity_router", "done",
                    f"level={complexity_result.level.value} profile={selected_profile}",
                )
                logger.info(
                    "complexity_routed",
                    run_id=run_id,
                    level=complexity_result.level.value,
                    profile=selected_profile,
                    score=complexity_result.score,
                )

            pipeline_profile = get_pipeline_profile(selected_profile, self.config.config_dir)
            active_stages = set(pipeline_profile.get("stages", []))
            skip_stages = set(pipeline_profile.get("skip_stages", []))
            early_exit_enabled = pipeline_profile.get("early_exit", False)
            early_exit_stages = set(pipeline_profile.get("early_exit_stages", []))
            early_exit_rules = profile_config.get("early_exit_rules", {})
            parallel_groups = profile_config.get("parallel_groups", {})

            logger.info(
                "pipeline_profile_selected",
                run_id=run_id,
                profile=selected_profile,
                active_stages=list(active_stages),
                skipped=list(skip_stages),
                early_exit=early_exit_enabled,
            )

            write_json(run_dir / "pipeline_profile.json", {
                "profile": selected_profile,
                "active_stages": list(active_stages),
                "skip_stages": list(skip_stages),
                "early_exit": early_exit_enabled,
            })

            cross_ref_issues: list = []
            codebase_context: Optional[str] = None
            domain_context_str: str = ""
            domain_analysis_str: str = ""

            has_project = bool(project_path)
            has_domain_ctx = "domain_context" in active_stages and "domain_context" not in skip_stages
            has_xref = "cross_reference" in active_stages and "cross_reference" not in skip_stages
            has_critic_a = "critic_a_multi" in active_stages and "critic_a_multi" not in skip_stages
            has_critic_b = "critic_b_multi" in active_stages and "critic_b_multi" not in skip_stages
            has_deep = "deep_analysis" in active_stages and "deep_analysis" not in skip_stages
            has_meta_judge = "meta_judge" in active_stages and "meta_judge" not in skip_stages
            has_fact_check = "fact_check" in active_stages and "fact_check" not in skip_stages

            fan_out_tasks = []
            fan_out_max = 4

            if has_project and (has_domain_ctx or has_xref or has_critic_a or has_critic_b):
                _broadcast_stage(run_id, "fan_out_group_1", "running")
                logger.info("stage_fan_out_group_1_start", run_id=run_id)

                domain_ctx_result = [""]
                domain_docs_result = [[]]
                xref_result = [([], None)]
                runs_a_result = [None]
                runs_b_result = [None]

                if has_domain_ctx:
                    _broadcast_stage(run_id, "domain_context", "running")

                    def _run_domain_context():
                        ctx, docs = extract_domain_context(
                            self.client, project_path, resolved_type.value, context_path=context_path,
                        )
                        domain_ctx_result[0] = ctx
                        domain_docs_result[0] = docs

                    fan_out_tasks.append(("domain_context", _run_domain_context))

                if has_xref:
                    _broadcast_stage(run_id, "cross_reference", "running")

                    def _run_cross_reference():
                        issues, ctx = run_cross_reference(
                            self.client, content, resolved_type.value, project_path,
                        )
                        xref_result[0] = (issues, ctx)

                    fan_out_tasks.append(("cross_reference", _run_cross_reference))

                if has_critic_a:
                    _broadcast_stage(run_id, "critic_a_multi", "running")

                    def _run_critic_a():
                        runs = run_critic_a_multi(
                            self.client, content, resolved_type.value,
                            n_runs=self.config.critic_runs,
                            max_workers=self.config.critic_max_workers,
                            delay_seconds=self.config.critic_delay_seconds,
                        )
                        runs_a_result[0] = runs

                    fan_out_tasks.append(("critic_a_multi", _run_critic_a))

                if has_critic_b:
                    _broadcast_stage(run_id, "critic_b_multi", "running")

                    def _run_critic_b():
                        runs = run_critic_b_multi(
                            self.client, content, resolved_type.value,
                            n_runs=self.config.critic_runs,
                            max_workers=self.config.critic_max_workers,
                            delay_seconds=self.config.critic_delay_seconds,
                        )
                        runs_b_result[0] = runs

                    fan_out_tasks.append(("critic_b_multi", _run_critic_b))

                with ThreadPoolExecutor(max_workers=min(len(fan_out_tasks), fan_out_max)) as executor:
                    futs = [executor.submit(fn) for _, fn in fan_out_tasks]
                    for f in futs:
                        f.result()

                if has_domain_ctx:
                    domain_context_str = domain_ctx_result[0]
                    domain_docs = domain_docs_result[0]
                    actual_models_used["domain_context"] = self.client.resolve_model("critic_a")
                    if domain_context_str:
                        write_text(run_dir / "domain_context.md", domain_context_str)
                        write_json(run_dir / "domain_docs.json", domain_docs)
                        logger.info("domain_context_found", docs=len(domain_docs))
                    _broadcast_stage(run_id, "domain_context", "done", f"{len(domain_docs_result[0])} docs")

                if has_xref:
                    cross_ref_issues, codebase_context = xref_result[0]
                    actual_models_used["cross_ref"] = self.client.resolve_model("critic_a")
                    if codebase_context:
                        write_text(run_dir / "codebase_context.md", codebase_context)
                        write_json(run_dir / "cross_ref_issues.json", [i.model_dump() for i in cross_ref_issues])
                        logger.info("cross_ref_issues_found", count=len(cross_ref_issues))
                    _broadcast_stage(run_id, "cross_reference", "done", f"{len(cross_ref_issues)} issues")

                    if early_exit_enabled and "cross_reference" in early_exit_stages:
                        xref_rules = early_exit_rules.get("cross_reference", {})
                        fatal_sevs = xref_rules.get("fatal_severities", ["critical"])
                        min_count = xref_rules.get("min_fatal_count", 1)
                        fatal_xref = [i for i in cross_ref_issues if i.severity.value in fatal_sevs]
                        if len(fatal_xref) >= min_count:
                            abort_msg = xref_rules.get("abort_message", "Fatal cross-reference errors detected")
                            logger.warning("early_exit_triggered", stage="cross_reference", fatal=len(fatal_xref), run_id=run_id)
                            _broadcast_stage(run_id, "early_exit", "done", abort_msg)
                            warnings.append(f"EARLY EXIT: {abort_msg} ({len(fatal_xref)} fatal issues)")
                            write_json(run_dir / "early_exit.json", {
                                "stage": "cross_reference",
                                "fatal_count": len(fatal_xref),
                                "message": abort_msg,
                            })

                            pipeline_duration_ms = round((time.monotonic() - pipeline_start) * 1000)
                            token_summary = self.token_tracker.get_summary()
                            write_json(run_dir / "token_report.json", token_summary)

                            early_artifacts = RunArtifacts(
                                run_id=run_id,
                                output_dir=str(run_dir),
                                original_content=content,
                                revised_content=content,
                                issues=cross_ref_issues,
                                validations=[],
                                scorecard=None,
                                promptfoo_raw=None,
                                fact_check=None,
                                metadata=RunMetadata(
                                    timestamp=datetime.now(timezone.utc).isoformat(),
                                    document_type=resolved_type,
                                    model_aliases_used=model_aliases_used,
                                    actual_models_used=actual_models_used,
                                    proxy_base_url=self.config.proxy_base_url,
                                    execution_status="early_exit",
                                    token_usage={
                                        "total": token_summary["total_tokens"],
                                        "total_prompt_tokens": token_summary["total_prompt_tokens"],
                                        "total_completion_tokens": token_summary["total_completion_tokens"],
                                        "total_calls": token_summary["total_calls"],
                                        "by_model": token_summary["by_model"],
                                        "by_stage": token_summary["by_stage"],
                                    },
                                    estimated_cost=0.0,
                                    warnings=warnings,
                                    duration_ms=pipeline_duration_ms,
                                ),
                            )
                            write_json(run_dir / "metadata.json", early_artifacts.metadata.model_dump())
                            _broadcast_done(run_id)
                            return early_artifacts

                if has_critic_a:
                    actual_models_used["critic_a"] = self.client.resolve_model("critic_a")
                    _broadcast_stage(run_id, "critic_a_multi", "done")

                if has_critic_b:
                    actual_models_used["critic_b"] = self.client.resolve_model("critic_b")
                    _broadcast_stage(run_id, "critic_b_multi", "done")

                _broadcast_stage(run_id, "fan_out_group_1", "done")

                if has_deep and domain_context_str:
                    _check_cancel(cancel_event, run_id, "deep_analysis")
                    _broadcast_stage(run_id, "deep_analysis", "running")
                    logger.info("stage_deep_analysis", run_id=run_id)
                    analysis_raw = run_deep_analysis(
                        self.client, content, resolved_type.value,
                        domain_context_str, codebase_context or "",
                    )
                    if analysis_raw:
                        write_json(run_dir / "domain_analysis.json", analysis_raw)
                        domain_analysis_str = format_analysis_for_validator(analysis_raw)
                        write_text(run_dir / "domain_analysis.md", domain_analysis_str)
                    actual_models_used["deep_analysis"] = self.client.resolve_model("critic_a")
                    _broadcast_stage(
                        run_id, "deep_analysis", "done",
                        f"{len(analysis_raw.get('domain_violations', []))} violations" if analysis_raw else "empty",
                    )

                    if early_exit_enabled and "deep_analysis" in early_exit_stages and analysis_raw:
                        da_rules = early_exit_rules.get("deep_analysis", {})
                        fatal_sevs = da_rules.get("fatal_severities", ["critical"])
                        min_count = da_rules.get("min_fatal_count", 2)
                        violations = analysis_raw.get("domain_violations", [])
                        fatal_violations = [v for v in violations if v.get("severity") in fatal_sevs]
                        if len(fatal_violations) >= min_count:
                            abort_msg = da_rules.get("abort_message", "Critical architectural violations detected")
                            logger.warning("early_exit_triggered", stage="deep_analysis", fatal=len(fatal_violations), run_id=run_id)
                            _broadcast_stage(run_id, "early_exit", "done", abort_msg)
                            warnings.append(f"EARLY EXIT: {abort_msg} ({len(fatal_violations)} fatal violations)")
                            write_json(run_dir / "early_exit.json", {
                                "stage": "deep_analysis",
                                "fatal_count": len(fatal_violations),
                                "message": abort_msg,
                            })

                            pipeline_duration_ms = round((time.monotonic() - pipeline_start) * 1000)
                            token_summary = self.token_tracker.get_summary()
                            write_json(run_dir / "token_report.json", token_summary)

                            early_artifacts = RunArtifacts(
                                run_id=run_id,
                                output_dir=str(run_dir),
                                original_content=content,
                                revised_content=content,
                                issues=cross_ref_issues,
                                validations=[],
                                scorecard=None,
                                promptfoo_raw=None,
                                fact_check=None,
                                metadata=RunMetadata(
                                    timestamp=datetime.now(timezone.utc).isoformat(),
                                    document_type=resolved_type,
                                    model_aliases_used=model_aliases_used,
                                    actual_models_used=actual_models_used,
                                    proxy_base_url=self.config.proxy_base_url,
                                    execution_status="early_exit",
                                    token_usage={
                                        "total": token_summary["total_tokens"],
                                        "total_prompt_tokens": token_summary["total_prompt_tokens"],
                                        "total_completion_tokens": token_summary["total_completion_tokens"],
                                        "total_calls": token_summary["total_calls"],
                                        "by_model": token_summary["by_model"],
                                        "by_stage": token_summary["by_stage"],
                                    },
                                    estimated_cost=0.0,
                                    warnings=warnings,
                                    duration_ms=pipeline_duration_ms,
                                ),
                            )
                            write_json(run_dir / "metadata.json", early_artifacts.metadata.model_dump())
                            _broadcast_done(run_id)
                            return early_artifacts

            elif not has_project:
                logger.info("stage_cross_reference_skipped", reason="no_project_path")
                _broadcast_stage(run_id, "cross_reference", "skipped", "no project path")

                if has_critic_a or has_critic_b:
                    _broadcast_stage(run_id, "critic_a_multi", "running")
                    _broadcast_stage(run_id, "critic_b_multi", "running")
                    logger.info("stage_critic_a_b_parallel_no_project", run_id=run_id)

                    runs_a_result = [None]
                    runs_b_result = [None]

                    def _run_critic_a():
                        runs_a_result[0] = run_critic_a_multi(
                            self.client, content, resolved_type.value,
                            n_runs=self.config.critic_runs,
                            max_workers=self.config.critic_max_workers,
                            delay_seconds=self.config.critic_delay_seconds,
                        )

                    def _run_critic_b():
                        runs_b_result[0] = run_critic_b_multi(
                            self.client, content, resolved_type.value,
                            n_runs=self.config.critic_runs,
                            max_workers=self.config.critic_max_workers,
                            delay_seconds=self.config.critic_delay_seconds,
                        )

                    with ThreadPoolExecutor(max_workers=2) as executor:
                        fut_a = executor.submit(_run_critic_a)
                        fut_b = executor.submit(_run_critic_b)
                        fut_a.result()
                        fut_b.result()

                    actual_models_used["critic_a"] = self.client.resolve_model("critic_a")
                    actual_models_used["critic_b"] = self.client.resolve_model("critic_b")
                    _broadcast_stage(run_id, "critic_a_multi", "done")
                    _broadcast_stage(run_id, "critic_b_multi", "done")

            runs_a = runs_a_result[0] if has_critic_a else []
            runs_b = runs_b_result[0] if has_critic_b else []

            if has_critic_a and has_critic_b:
                _check_cancel(cancel_event, run_id, "critic_judges_parallel")
                _broadcast_stage(run_id, "critic_a_judge", "running")
                _broadcast_stage(run_id, "critic_b_judge", "running")
                logger.info("stage_critic_judges_parallel", run_id=run_id)

                issues_a_result = [None]
                issues_b_result = [None]

                def _run_critic_a_judge():
                    issues_a_result[0] = judge_critic_runs(
                        self.client, runs_a, content, resolved_type.value, "critic_a",
                    )

                def _run_critic_b_judge():
                    issues_b_result[0] = judge_critic_runs(
                        self.client, runs_b, content, resolved_type.value, "critic_b",
                    )

                with ThreadPoolExecutor(max_workers=2) as executor:
                    fut_ja = executor.submit(_run_critic_a_judge)
                    fut_jb = executor.submit(_run_critic_b_judge)
                    fut_ja.result()
                    fut_jb.result()

                issues_a = issues_a_result[0] or []
                issues_b = issues_b_result[0] or []

                actual_models_used["critic_judge_a"] = self.client.resolve_model("critic_judge")
                actual_models_used["critic_judge_b"] = self.client.resolve_model("critic_judge")
                _broadcast_stage(run_id, "critic_a_judge", "done", f"{len(issues_a)} issues")
                _broadcast_stage(run_id, "critic_b_judge", "done", f"{len(issues_b)} issues")

                _check_cancel(cancel_event, run_id, "dedup")
                _broadcast_stage(run_id, "dedup", "running")
                logger.info("stage_dedup", run_id=run_id)
                merged_issues = deduplicate_issues(issues_a, issues_b)
                _broadcast_stage(run_id, "dedup", "done", f"{len(merged_issues)} merged")

                all_issues = cross_ref_issues + merged_issues
            elif has_critic_a or has_critic_b:
                issues_a = []
                issues_b = []
                if has_critic_a:
                    _check_cancel(cancel_event, run_id, "critic_a_judge")
                    _broadcast_stage(run_id, "critic_a_judge", "running")
                    issues_a = judge_critic_runs(
                        self.client, runs_a, content, resolved_type.value, "critic_a",
                    )
                    actual_models_used["critic_judge_a"] = self.client.resolve_model("critic_judge")
                    _broadcast_stage(run_id, "critic_a_judge", "done", f"{len(issues_a)} issues")
                if has_critic_b:
                    _check_cancel(cancel_event, run_id, "critic_b_judge")
                    _broadcast_stage(run_id, "critic_b_judge", "running")
                    issues_b = judge_critic_runs(
                        self.client, runs_b, content, resolved_type.value, "critic_b",
                    )
                    actual_models_used["critic_judge_b"] = self.client.resolve_model("critic_judge")
                    _broadcast_stage(run_id, "critic_b_judge", "done", f"{len(issues_b)} issues")

                if has_critic_a and has_critic_b:
                    _check_cancel(cancel_event, run_id, "dedup")
                    _broadcast_stage(run_id, "dedup", "running")
                    merged_issues = deduplicate_issues(issues_a, issues_b)
                    _broadcast_stage(run_id, "dedup", "done", f"{len(merged_issues)} merged")
                else:
                    merged_issues = issues_a + issues_b

                all_issues = cross_ref_issues + merged_issues
            else:
                all_issues = cross_ref_issues
                logger.info("critic_stages_skipped", run_id=run_id)

            write_json(run_dir / "issues.json", [i.model_dump() for i in all_issues])

            _check_cancel(cancel_event, run_id, "validate")
            _broadcast_stage(run_id, "validate", "running")
            logger.info("stage_validate", run_id=run_id)
            validations = validate_issues(
                self.client,
                all_issues,
                content,
                domain_context=domain_context_str,
                codebase_context=codebase_context or "",
                domain_analysis=domain_analysis_str,
            )
            actual_models_used["validator"] = self.client.resolve_model("validator")
            write_json(run_dir / "validations.json", [v.model_dump() for v in validations])
            valid_issues = get_valid_issues(all_issues, validations)
            _broadcast_stage(run_id, "validate", "done", f"{len(valid_issues)} valid")

            _check_cancel(cancel_event, run_id, "revise")
            _broadcast_stage(run_id, "revise", "running")
            logger.info("stage_revise", run_id=run_id)
            revised = revise_document(self.client, content, resolved_type.value, valid_issues)
            actual_models_used["reviser"] = self.client.resolve_model("reviser")
            write_text(run_dir / "revised.md", revised)
            _broadcast_stage(run_id, "revise", "done")

            _check_cancel(cancel_event, run_id, "score")
            _broadcast_stage(run_id, "score", "running")
            logger.info("stage_score", run_id=run_id)
            proxy_url = f"{self.config.proxy_base_url}/v1"

            scorecard, promptfoo_raw = score_document(
                client=self.client,
                promptfoo_runner=self.promptfoo_runner,
                revised_content=revised,
                document_type=resolved_type.value,
                original_content=content,
                issues=all_issues,
                validations=validations,
                threshold_config=threshold_config,
                proxy_base_url=proxy_url,
                proxy_api_key=self.config.proxy_api_key,
                scorer_runs=self.config.scorer_runs,
                scorer_max_workers=self.config.scorer_max_workers,
            )
            actual_models_used["scorer"] = self.client.resolve_model("scorer")
            actual_models_used["scorer_promptfoo"] = self.client.resolve_model("scorer_promptfoo")
            write_json(run_dir / "scorecard.json", scorecard.model_dump())

            if promptfoo_raw:
                write_json(run_dir / "promptfoo_raw.json", promptfoo_raw)
            _broadcast_stage(run_id, "score", "done", f"{scorecard.overall_score}/10")

            meta_result = None
            if has_meta_judge:
                _check_cancel(cancel_event, run_id, "meta_judge")
                skip_meta = (
                    scorecard.confidence_in_scoring >= 0.85
                    and scorecard.promptfoo_agreement in ("agree", None)
                    and not scorecard.blocking_reasons
                )
                if skip_meta:
                    logger.info("meta_judge_skipped", run_id=run_id, confidence=scorecard.confidence_in_scoring)
                    _broadcast_stage(run_id, "meta_judge", "done", "skipped (high confidence)")
                else:
                    _broadcast_stage(run_id, "meta_judge", "running")
                    logger.info("stage_meta_judge", run_id=run_id)
                    unresolved_critical = scorecard.unresolved_critical_issues_count
                    meta_result = run_meta_judge(
                        self.client,
                        scorecard,
                        revised,
                        resolved_type.value,
                    )
                    actual_models_used["meta_judge"] = self.client.resolve_model("meta_judge")
                    scorecard = apply_meta_judge_adjustments(scorecard, meta_result, threshold_config, unresolved_critical)
                    write_json(run_dir / "scorecard.json", scorecard.model_dump())
                    write_json(run_dir / "meta_judge.json", meta_result.model_dump())
                    _broadcast_stage(
                        run_id,
                        "meta_judge",
                        "done",
                        f"verdict={meta_result.verdict} score={scorecard.overall_score}",
                    )
            else:
                logger.info("meta_judge_skipped_by_profile", run_id=run_id)
                _broadcast_stage(run_id, "meta_judge", "skipped", "not in profile")

            _check_cancel(cancel_event, run_id, "report")
            _broadcast_stage(run_id, "report", "running")
            logger.info("stage_report", run_id=run_id)

            fact_check_result = None
            if has_fact_check:
                _check_cancel(cancel_event, run_id, "fact_check")
                _broadcast_stage(run_id, "fact_check", "running")
                logger.info("stage_fact_check", run_id=run_id)
                try:
                    fact_check_result = run_fact_check(self.client, run_dir)
                    actual_models_used["fact_check"] = self.client.resolve_model("meta_judge")
                    write_json(run_dir / "fact_check.json", fact_check_result.model_dump())
                    fact_check_md = generate_fact_check_report_md(fact_check_result)
                    write_text(run_dir / "fact_check.md", fact_check_md)
                    _broadcast_stage(
                        run_id,
                        "fact_check",
                        "done",
                        f"{fact_check_result.confirmed_count} confirmed, {fact_check_result.refuted_count} refuted",
                    )
                except Exception as e:
                    logger.warning("fact_check_failed", error=str(e))
                    _broadcast_stage(run_id, "fact_check", "failed", str(e))
            else:
                logger.info("fact_check_skipped_by_profile", run_id=run_id)
                _broadcast_stage(run_id, "fact_check", "skipped", "not in profile")

            pipeline_duration_ms = round((time.monotonic() - pipeline_start) * 1000)

            token_summary = self.token_tracker.get_summary()
            write_json(run_dir / "token_report.json", token_summary)

            artifacts = RunArtifacts(
                run_id=run_id,
                output_dir=str(run_dir),
                original_content=content,
                revised_content=revised,
                issues=all_issues,
                validations=validations,
                scorecard=scorecard,
                promptfoo_raw=promptfoo_raw,
                fact_check=fact_check_result,
                metadata=RunMetadata(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    document_type=resolved_type,
                    model_aliases_used=model_aliases_used,
                    actual_models_used=actual_models_used,
                    proxy_base_url=self.config.proxy_base_url,
                    execution_status="completed",
                    token_usage={
                        "total": token_summary["total_tokens"],
                        "total_prompt_tokens": token_summary["total_prompt_tokens"],
                        "total_completion_tokens": token_summary["total_completion_tokens"],
                        "total_calls": token_summary["total_calls"],
                        "by_model": token_summary["by_model"],
                        "by_stage": token_summary["by_stage"],
                    },
                    estimated_cost=0.0,
                    warnings=warnings,
                    duration_ms=pipeline_duration_ms,
                ),
            )

            md_report, html_report = generate_reports(artifacts, threshold_config)
            write_text(run_dir / "report.md", md_report)
            write_text(run_dir / "report.html", html_report)
            write_json(run_dir / "metadata.json", artifacts.metadata.model_dump())

            _broadcast_stage(run_id, "report", "done")

            logger.info(
                "pipeline_done",
                run_id=run_id,
                score=scorecard.overall_score,
                passed=scorecard.passed,
                action=scorecard.recommended_next_action.value,
                meta_judge_verdict=meta_result.verdict if meta_result else None,
                profile=selected_profile,
                duration_ms=pipeline_duration_ms,
            )

            turkish_summary = _generate_turkish_summary(self.client, scorecard, all_issues, validations, content)

            _broadcast_done(run_id, scorecard.overall_score, scorecard.passed, turkish_summary)

            return artifacts

        except PipelineCancelledError:
            pipeline_duration_ms = round((time.monotonic() - pipeline_start) * 1000)
            cancelled_meta = RunMetadata(
                timestamp=datetime.now(timezone.utc).isoformat(),
                document_type=resolved_type if "resolved_type" in dir() else "custom",
                execution_status="cancelled",
                duration_ms=pipeline_duration_ms,
                warnings=warnings if "warnings" in dir() else [],
            )
            write_json(run_dir / "metadata.json", cancelled_meta.model_dump())
            logger.warning("pipeline_cancelled", run_id=run_id, duration_ms=pipeline_duration_ms)
            raise
        except Exception as e:
            pipeline_duration_ms = round((time.monotonic() - pipeline_start) * 1000)
            try:
                error_meta = RunMetadata(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    document_type=resolved_type if "resolved_type" in dir() else "custom",
                    execution_status="failed",
                    duration_ms=pipeline_duration_ms,
                    warnings=warnings if "warnings" in dir() else [],
                )
                write_json(run_dir / "metadata.json", error_meta.model_dump())
            except Exception:
                pass
            logger.exception("pipeline_error", run_id=run_id, error=str(e), exc_info=True)
            tb_str = _traceback.format_exc()
            logger.error("pipeline_error_traceback", run_id=run_id, traceback=tb_str)
            _broadcast_done(run_id)
            raise

    def run_eval_only(self, run_id: str) -> RunArtifacts:
        run_dir = Path(self.config.output_base_dir) / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_id}")

        original = (run_dir / "original.md").read_text(encoding="utf-8") if (run_dir / "original.md").exists() else ""
        revised = (
            (run_dir / "revised.md").read_text(encoding="utf-8") if (run_dir / "revised.md").exists() else original
        )

        import json

        issues_data = json.loads((run_dir / "issues.json").read_text()) if (run_dir / "issues.json").exists() else []
        from app.schemas import Issue, Validation

        issues = [Issue(**i) for i in issues_data]
        validations_data = (
            json.loads((run_dir / "validations.json").read_text()) if (run_dir / "validations.json").exists() else []
        )
        validations = [Validation(**v) for v in validations_data]

        metadata_data = (
            json.loads((run_dir / "metadata.json").read_text()) if (run_dir / "metadata.json").exists() else {}
        )
        doc_type = metadata_data.get("document_type", "custom")

        threshold_config = load_threshold_config(self.config.config_dir, doc_type)

        logger.info("eval_only_start", run_id=run_id)
        proxy_url = f"{self.config.proxy_base_url}/v1"

        scorecard, promptfoo_raw = score_document(
            client=self.client,
            promptfoo_runner=self.promptfoo_runner,
            revised_content=revised,
            document_type=doc_type,
            original_content=original,
            issues=issues,
            validations=validations,
            threshold_config=threshold_config,
            proxy_base_url=proxy_url,
            proxy_api_key=self.config.proxy_api_key,
        )

        unresolved_critical = scorecard.unresolved_critical_issues_count
        meta_result = run_meta_judge(self.client, scorecard, revised, doc_type)
        scorecard = apply_meta_judge_adjustments(scorecard, meta_result, threshold_config, unresolved_critical)

        write_json(run_dir / "scorecard.json", scorecard.model_dump())
        write_json(run_dir / "meta_judge.json", meta_result.model_dump())
        if promptfoo_raw:
            write_json(run_dir / "promptfoo_raw.json", promptfoo_raw)

        artifacts = RunArtifacts(
            run_id=run_id,
            output_dir=str(run_dir),
            original_content=original,
            revised_content=revised,
            issues=issues,
            validations=validations,
            scorecard=scorecard,
            promptfoo_raw=promptfoo_raw,
            metadata=RunMetadata(
                timestamp=datetime.now(timezone.utc).isoformat(),
                document_type=doc_type,
                execution_status="eval_only_completed",
            ),
        )

        md_report, html_report = generate_reports(artifacts, threshold_config)
        write_text(run_dir / "report.md", md_report)
        write_text(run_dir / "report.html", html_report)
        write_json(run_dir / "metadata.json", artifacts.metadata.model_dump())

        logger.info("eval_only_done", run_id=run_id, score=scorecard.overall_score)
        return artifacts

    def run_rescore(
        self,
        previous_run_dir: str,
        revised_file_path: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> RunArtifacts:
        prev_dir = Path(previous_run_dir)
        if not prev_dir.exists():
            raise FileNotFoundError(f"Previous run directory not found: {previous_run_dir}")

        run_id, run_dir = create_run_dir(self.config.output_base_dir)
        pipeline_start = time.monotonic()
        logger.info("rescore_start", run_id=run_id, previous_run=str(prev_dir))

        _broadcast_stage(run_id, "rescore", "running")

        original = (prev_dir / "original.md").read_text(encoding="utf-8") if (prev_dir / "original.md").exists() else ""

        if revised_file_path:
            revised = Path(revised_file_path).read_text(encoding="utf-8")
        else:
            revised = (prev_dir / "revised.md").read_text(encoding="utf-8") if (prev_dir / "revised.md").exists() else original

        import json as _json
        from app.schemas import Issue, Validation

        issues_data = _json.loads((prev_dir / "issues.json").read_text()) if (prev_dir / "issues.json").exists() else []
        issues = [Issue(**i) for i in issues_data]
        validations_data = _json.loads((prev_dir / "validations.json").read_text()) if (prev_dir / "validations.json").exists() else []
        validations = [Validation(**v) for v in validations_data]
        metadata_data = _json.loads((prev_dir / "metadata.json").read_text()) if (prev_dir / "metadata.json").exists() else {}
        doc_type = metadata_data.get("document_type", "custom")
        threshold_config = load_threshold_config(self.config.config_dir, doc_type)

        write_text(run_dir / "original.md", original)
        write_text(run_dir / "revised.md", revised)
        write_json(run_dir / "issues.json", issues_data)
        write_json(run_dir / "validations.json", validations_data)

        _check_cancel(cancel_event, run_id, "score")
        _broadcast_stage(run_id, "score", "running")
        logger.info("rescore_scoring", run_id=run_id)
        proxy_url = f"{self.config.proxy_base_url}/v1"

        scorecard, promptfoo_raw = score_document(
            client=self.client,
            promptfoo_runner=self.promptfoo_runner,
            revised_content=revised,
            document_type=doc_type,
            original_content=original,
            issues=issues,
            validations=validations,
            threshold_config=threshold_config,
            proxy_base_url=proxy_url,
            proxy_api_key=self.config.proxy_api_key,
            scorer_runs=max(1, self.config.scorer_runs),
            scorer_max_workers=self.config.scorer_max_workers,
        )
        write_json(run_dir / "scorecard.json", scorecard.model_dump())
        if promptfoo_raw:
            write_json(run_dir / "promptfoo_raw.json", promptfoo_raw)
        _broadcast_stage(run_id, "score", "done", f"{scorecard.overall_score}/10")

        _check_cancel(cancel_event, run_id, "meta_judge")
        meta_result = None
        skip_meta = (
            scorecard.confidence_in_scoring >= 0.85
            and scorecard.promptfoo_agreement in ("agree", None)
            and not scorecard.blocking_reasons
        )
        if skip_meta:
            _broadcast_stage(run_id, "meta_judge", "done", "skipped (high confidence)")
        else:
            _broadcast_stage(run_id, "meta_judge", "running")
            unresolved_critical = scorecard.unresolved_critical_issues_count
            meta_result = run_meta_judge(self.client, scorecard, revised, doc_type)
            scorecard = apply_meta_judge_adjustments(scorecard, meta_result, threshold_config, unresolved_critical)
            write_json(run_dir / "scorecard.json", scorecard.model_dump())
            write_json(run_dir / "meta_judge.json", meta_result.model_dump())
            _broadcast_stage(run_id, "meta_judge", "done", f"verdict={meta_result.verdict} score={scorecard.overall_score}")

        _broadcast_stage(run_id, "report", "running")
        pipeline_duration_ms = round((time.monotonic() - pipeline_start) * 1000)
        token_summary = self.token_tracker.get_summary()
        write_json(run_dir / "token_report.json", token_summary)

        artifacts = RunArtifacts(
            run_id=run_id,
            output_dir=str(run_dir),
            original_content=original,
            revised_content=revised,
            issues=issues,
            validations=validations,
            scorecard=scorecard,
            promptfoo_raw=promptfoo_raw,
            fact_check=None,
            metadata=RunMetadata(
                timestamp=datetime.now(timezone.utc).isoformat(),
                document_type=doc_type,
                execution_status="rescore_completed",
                duration_ms=pipeline_duration_ms,
            ),
        )

        md_report, html_report = generate_reports(artifacts, threshold_config)
        write_text(run_dir / "report.md", md_report)
        write_text(run_dir / "report.html", html_report)
        write_json(run_dir / "metadata.json", artifacts.metadata.model_dump())
        _broadcast_stage(run_id, "report", "done")

        turkish_summary = _generate_turkish_summary(self.client, scorecard, issues, validations, original)
        _broadcast_done(run_id, scorecard.overall_score, scorecard.passed, turkish_summary)

        logger.info("rescore_done", run_id=run_id, score=scorecard.overall_score, duration_ms=pipeline_duration_ms)
        return artifacts

    def run_fact_check_only(self, run_id: str) -> RunArtifacts:
        run_dir = Path(self.config.output_base_dir) / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_id}")

        self.token_tracker.reset()

        original = (run_dir / "original.md").read_text(encoding="utf-8") if (run_dir / "original.md").exists() else ""
        revised = (
            (run_dir / "revised.md").read_text(encoding="utf-8") if (run_dir / "revised.md").exists() else original
        )

        import json

        issues_data = json.loads((run_dir / "issues.json").read_text()) if (run_dir / "issues.json").exists() else []
        from app.schemas import Issue, Validation

        issues = [Issue(**i) for i in issues_data]
        validations_data = (
            json.loads((run_dir / "validations.json").read_text()) if (run_dir / "validations.json").exists() else []
        )
        validations = [Validation(**v) for v in validations_data]

        metadata_data = (
            json.loads((run_dir / "metadata.json").read_text()) if (run_dir / "metadata.json").exists() else {}
        )
        doc_type = metadata_data.get("document_type", "custom")

        scorecard_data = (
            json.loads((run_dir / "scorecard.json").read_text()) if (run_dir / "scorecard.json").exists() else None
        )
        from app.schemas import Scorecard

        scorecard = Scorecard(**scorecard_data) if scorecard_data else None

        logger.info("fact_check_only_start", run_id=run_id)

        fact_check_result = run_fact_check(self.client, run_dir)

        write_json(run_dir / "fact_check.json", fact_check_result.model_dump())
        fact_check_md = generate_fact_check_report_md(fact_check_result)
        write_text(run_dir / "fact_check.md", fact_check_md)

        token_summary = self.token_tracker.get_summary()
        write_json(run_dir / "token_report.json", token_summary)

        promptfoo_raw = None

        artifacts = RunArtifacts(
            run_id=run_id,
            output_dir=str(run_dir),
            original_content=original,
            revised_content=revised,
            issues=issues,
            validations=validations,
            scorecard=scorecard,
            promptfoo_raw=promptfoo_raw,
            fact_check=fact_check_result,
            metadata=RunMetadata(
                timestamp=datetime.now(timezone.utc).isoformat(),
                document_type=doc_type,
                execution_status="fact_check_completed",
            ),
        )

        logger.info(
            "fact_check_only_done",
            run_id=run_id,
            confirmed=fact_check_result.confirmed_count,
            refuted=fact_check_result.refuted_count,
        )
        return artifacts

    def run_apply_fixes(self, run_id: str, approved_fix_ids: list[str]) -> str:
        run_dir = Path(self.config.output_base_dir) / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_id}")

        logger.info("apply_fixes_start", run_id=run_id, fix_count=len(approved_fix_ids))

        fixed_content = apply_approved_fixes(self.client, run_dir, approved_fix_ids)
        write_text(run_dir / "fixed.md", fixed_content)

        fact_check_path = run_dir / "fact_check.json"
        fact_check_data = (
            json.loads(fact_check_path.read_text(encoding="utf-8"))
            if fact_check_path.exists()
            else {}
        )
        if fact_check_data:
            fact_check_data["approved_fix_ids"] = approved_fix_ids
            write_json(run_dir / "fact_check.json", fact_check_data)

        logger.info("apply_fixes_done", run_id=run_id, fixes_applied=len(approved_fix_ids))
        return str(run_dir / "fixed.md")

    def smoke_test(self) -> dict:
        results: dict[str, dict] = {}

        logger.info("smoke_test_start")

        health = self.client.health_check()
        results["proxy_health"] = health
        logger.info("smoke_proxy", status=health.get("status"))

        routing = load_model_routing(self.config.config_dir)

        for group_name, group_config in routing.model_groups.items():
            logger.info("smoke_testing_group", group=group_name, model=group_config.model)
            test_result = self.client.test_model(group_config.model)
            results[f"model_{group_name}"] = test_result

        promptfoo_available = False
        try:
            import shutil
            import subprocess
            import sys

            npx_cmd = shutil.which("npx")
            if npx_cmd:
                r = subprocess.run(
                    [npx_cmd, "promptfoo", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    shell=(sys.platform == "win32"),
                )
                promptfoo_available = r.returncode == 0
            results["promptfoo"] = {
                "available": promptfoo_available,
                "version": r.stdout.strip() if promptfoo_available else None,
            }
        except Exception as e:
            results["promptfoo"] = {"available": False, "error": str(e)}

        logger.info("smoke_test_done")
        return results

    def run_from_jira(
        self,
        task_key: str,
        context_path: Optional[str] = None,
        project_path: Optional[str] = None,
        generate_only: bool = False,
        cancel_event: Optional[threading.Event] = None,
    ) -> RunArtifacts:
        from app.integrations.jira_reader import JiraReader, JiraReaderConfig

        jira_cfg = self.config.jira
        if not jira_cfg.is_configured:
            raise ValueError(
                "Jira credentials not configured. "
                "Set DQG_JIRA_EMAIL and DQG_JIRA_API_TOKEN in .env or config."
            )

        run_id, run_dir = create_run_dir(self.config.output_base_dir)
        LogBroadcaster.get().set_active_run(run_id)

        reader = JiraReader(JiraReaderConfig(
            base_url=jira_cfg.base_url,
            email=jira_cfg.email,
            api_token=jira_cfg.api_token,
            project=jira_cfg.project,
        ))

        _broadcast_stage(run_id, "jira_fetch", "running")
        logger.info("jira_fetch_start", key=task_key, run_id=run_id)
        issue = reader.fetch_issue(task_key)
        if issue is None:
            _broadcast_stage(run_id, "jira_fetch", "failed", f"Could not fetch {task_key}")
            raise ValueError(f"Could not fetch Jira issue: {task_key}")
        comments = reader.fetch_comments(task_key)
        logger.info("jira_fetch_done", key=task_key, comments=len(comments), run_id=run_id)
        _broadcast_stage(run_id, "jira_fetch", "done", f"{task_key} ({len(comments)} comments)")

        _broadcast_stage(run_id, "task_analysis", "running")
        logger.info("task_analyze_start", key=task_key, run_id=run_id)
        analysis = analyze_task(self.client, issue, comments)
        logger.info(
            "task_analyze_done",
            key=task_key,
            status=analysis.clarity_status.value,
            score=analysis.clarity_score,
            run_id=run_id,
        )
        _broadcast_stage(run_id, "task_analysis", "done", f"clarity={analysis.clarity_score}")

        if not context_path and jira_cfg.default_context_path:
            context_path = jira_cfg.default_context_path
            logger.info("using_default_context_path", path=context_path, run_id=run_id)

        if not project_path and context_path:
            project_path = str(Path.cwd())

        write_json(run_dir / "task_analysis.json", analysis.model_dump())

        _broadcast_stage(run_id, "document_generation", "running")
        logger.info("document_generate_start", key=task_key, run_id=run_id)
        doc_path, doc_content = generate_document(
            client=self.client,
            analysis=analysis,
            output_dir=str(run_dir),
            context_path=context_path,
        )
        logger.info("document_generate_done", key=task_key, path=doc_path, run_id=run_id)
        write_text(run_dir / "original.md", doc_content)
        _broadcast_stage(run_id, "document_generation", "done", str(doc_path))

        if generate_only:
            _broadcast_stage(run_id, "generate_only", "done")
            logger.info("generate_only_mode", key=task_key, run_id=run_id)
            metadata = RunMetadata(
                timestamp=datetime.now(timezone.utc).isoformat(),
                document_type="implementation_plan",
                execution_status="generate_only",
                warnings=[],
            )
            write_json(run_dir / "metadata.json", metadata.model_dump())
            turkish_summary = f"{task_key}: Doküman üretildi (skorlama atlandı)"
            _broadcast_done(run_id, turkish_summary=turkish_summary)
            return RunArtifacts(
                run_id=run_id,
                output_dir=str(run_dir),
                original_content=doc_content,
                revised_content=doc_content,
                metadata=metadata,
                task_analysis=analysis,
            )

        logger.info("jira_pipeline_start", run_id=run_id, key=task_key)
        artifacts = self.run(
            str(run_dir / "original.md"),
            doc_type="implementation_plan",
            project_path=project_path,
            context_path=context_path,
            cancel_event=cancel_event,
            run_id=run_id,
            run_dir=run_dir,
        )
        artifacts.task_analysis = analysis
        write_json(run_dir / "task_analysis.json", analysis.model_dump())

        return artifacts
