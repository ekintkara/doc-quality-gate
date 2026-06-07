from __future__ import annotations

from typing import Optional

from app.config import get_pipeline_profile, load_pipeline_profile_config


ALL_STAGES = [
    {"id": "ingest", "name": "Ingest", "category": "setup", "llm": False},
    {"id": "complexity_router", "name": "Complexity Router", "category": "setup", "llm": True},
    {"id": "domain_context", "name": "Domain Context", "category": "analysis", "llm": True},
    {"id": "cross_reference", "name": "Cross Reference", "category": "analysis", "llm": True},
    {"id": "deep_analysis", "name": "Deep Analysis", "category": "analysis", "llm": True},
    {"id": "critic_a_multi", "name": "Critic A (multi)", "category": "critic", "llm": True},
    {"id": "critic_b_multi", "name": "Critic B (multi)", "category": "critic", "llm": True},
    {"id": "critic_a_judge", "name": "Critic A Judge", "category": "critic", "llm": True},
    {"id": "critic_b_judge", "name": "Critic B Judge", "category": "critic", "llm": True},
    {"id": "dedupe", "name": "Deduplication", "category": "merge", "llm": False},
    {"id": "validate", "name": "Validation", "category": "review", "llm": True},
    {"id": "revise", "name": "Revision", "category": "review", "llm": True},
    {"id": "score", "name": "Scoring", "category": "evaluation", "llm": True},
    {"id": "meta_judge", "name": "Meta Judge", "category": "evaluation", "llm": True},
    {"id": "fact_check", "name": "Fact Check", "category": "evaluation", "llm": True},
    {"id": "report", "name": "Report", "category": "output", "llm": False},
]


PARALLEL_GROUPS_CONFIG = {
    "fan_out_group_1": {
        "stages": ["domain_context", "cross_reference", "critic_a_multi", "critic_b_multi"],
        "color": "#3b82f6",
    },
    "critic_judges": {
        "stages": ["critic_a_judge", "critic_b_judge"],
        "color": "#a855f7",
    },
}


def get_all_stages() -> list[dict]:
    return ALL_STAGES.copy()


def get_profiles() -> dict:
    config = load_pipeline_profile_config()
    return config.get("profiles", {})


def get_stage_durations() -> dict[str, float]:
    config = load_pipeline_profile_config()
    return config.get("stage_durations", {})


def simulate_pipeline(
    profile_name: str,
    enable_early_exit: bool = True,
    enable_fan_out: bool = True,
    enable_pruning: bool = True,
    has_project: bool = True,
) -> dict:
    config = load_pipeline_profile_config()
    profiles = config.get("profiles", {})
    durations = config.get("stage_durations", {})
    parallel_groups = config.get("parallel_groups", {})

    if profile_name == "current":
        return _simulate_current(durations, has_project)
    elif profile_name == "custom":
        return _simulate_custom(config, enable_early_exit, enable_fan_out, enable_pruning, has_project)
    elif profile_name in profiles:
        return _simulate_profile(profile_name, profiles[profile_name], durations, has_project)
    else:
        return _simulate_profile("deep", profiles.get("deep", {}), durations, has_project)


def _simulate_current(durations: dict, has_project: bool) -> dict:
    stages_timeline = []
    t = 0.0

    stages_timeline.append({"stage": "ingest", "start": t, "duration": durations.get("ingest", 0.5), "status": "active"})
    t += durations.get("ingest", 0.5)

    if has_project:
        dc_dur = durations.get("domain_context", 30)
        xref_dur = durations.get("cross_reference", 35)
        stages_timeline.append({"stage": "domain_context", "start": t, "duration": dc_dur, "status": "active"})
        stages_timeline.append({"stage": "cross_reference", "start": t, "duration": xref_dur, "status": "active"})
        t += max(dc_dur, xref_dur)

        deep_dur = durations.get("deep_analysis", 25)
        stages_timeline.append({"stage": "deep_analysis", "start": t, "duration": deep_dur, "status": "active"})
        t += deep_dur

    ca_dur = durations.get("critic_a_multi", 60)
    cb_dur = durations.get("critic_b_multi", 60)
    stages_timeline.append({"stage": "critic_a_multi", "start": t, "duration": ca_dur, "status": "active"})
    stages_timeline.append({"stage": "critic_b_multi", "start": t, "duration": cb_dur, "status": "active"})
    t += max(ca_dur, cb_dur)

    ja_dur = durations.get("critic_a_judge", 20)
    jb_dur = durations.get("critic_b_judge", 20)
    stages_timeline.append({"stage": "critic_a_judge", "start": t, "duration": ja_dur, "status": "active"})
    stages_timeline.append({"stage": "critic_b_judge", "start": t, "duration": jb_dur, "status": "active"})
    t += max(ja_dur, jb_dur)

    for s in ["dedupe", "validate", "revise", "score", "meta_judge", "fact_check", "report"]:
        dur = durations.get(s, 5)
        stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
        t += dur

    return {
        "profile": "current",
        "total_latency_seconds": t,
        "quality_confidence": 1.0,
        "stages_count": len(stages_timeline),
        "active_stages": [s["stage"] for s in stages_timeline],
        "timeline": stages_timeline,
        "savings_vs_current": 0.0,
        "parallel_groups": [
            {"name": "domain+xref", "stages": ["domain_context", "cross_reference"]},
            {"name": "critic_a+b", "stages": ["critic_a_multi", "critic_b_multi"]},
            {"name": "judge_a+b", "stages": ["critic_a_judge", "critic_b_judge"]},
        ],
    }


def _simulate_profile(
    profile_name: str, profile: dict, durations: dict, has_project: bool
) -> dict:
    active_stages = set(profile.get("stages", []))
    skip_stages = set(profile.get("skip_stages", []))
    early_exit = profile.get("early_exit", False)
    early_exit_stages = set(profile.get("early_exit_stages", []))
    quality_confidence = profile.get("quality_confidence", 0.95)
    est_latency = profile.get("estimated_latency_seconds", 300)

    stages_timeline = []
    t = 0.0
    run_stages = []

    stages_timeline.append({"stage": "ingest", "start": t, "duration": durations.get("ingest", 0.5), "status": "active"})
    t += durations.get("ingest", 0.5)
    run_stages.append("ingest")

    if has_project:
        analysis_tasks = []
        for s in ["domain_context", "cross_reference", "critic_a_multi", "critic_b_multi"]:
            if s in active_stages and s not in skip_stages:
                analysis_tasks.append(s)

        if analysis_tasks:
            max_dur = 0
            for s in analysis_tasks:
                dur = durations.get(s, 30)
                stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
                max_dur = max(max_dur, dur)
                run_stages.append(s)
            t += max_dur

        if "deep_analysis" in active_stages and "deep_analysis" not in skip_stages and has_project:
            deep_dur = durations.get("deep_analysis", 25)
            stages_timeline.append({"stage": "deep_analysis", "start": t, "duration": deep_dur, "status": "active"})
            t += deep_dur
            run_stages.append("deep_analysis")
    else:
        for s in ["critic_a_multi", "critic_b_multi"]:
            if s in active_stages and s not in skip_stages:
                dur = durations.get(s, 60)
                stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
                run_stages.append(s)
                if s == "critic_b_multi":
                    t += dur

    judge_tasks = []
    for s in ["critic_a_judge", "critic_b_judge"]:
        if s in active_stages and s not in skip_stages:
            judge_tasks.append(s)

    if judge_tasks:
        max_dur = 0
        for s in judge_tasks:
            dur = durations.get(s, 20)
            stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
            max_dur = max(max_dur, dur)
            run_stages.append(s)
        t += max_dur

    for s in ["dedupe", "validate", "revise", "score", "meta_judge", "fact_check", "report"]:
        if s in active_stages and s not in skip_stages:
            dur = durations.get(s, 5)
            stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
            t += dur
            run_stages.append(s)

    current_latency = _get_current_latency(durations, has_project)

    return {
        "profile": profile_name,
        "total_latency_seconds": round(t, 1),
        "quality_confidence": quality_confidence,
        "stages_count": len(stages_timeline),
        "active_stages": run_stages,
        "timeline": stages_timeline,
        "savings_vs_current": round((1 - t / current_latency) * 100, 1) if current_latency > 0 else 0,
        "early_exit": early_exit,
        "early_exit_stages": list(early_exit_stages),
    }


def _simulate_custom(
    config: dict,
    enable_early_exit: bool,
    enable_fan_out: bool,
    enable_pruning: bool,
    has_project: bool,
) -> dict:
    durations = config.get("stage_durations", {})

    active = [
        "ingest", "domain_context", "cross_reference", "deep_analysis",
        "critic_a_multi", "critic_b_multi", "critic_a_judge", "critic_b_judge",
        "dedupe", "validate", "revise", "score", "meta_judge", "fact_check", "report",
    ]

    if enable_pruning:
        active = [s for s in active if s not in ("meta_judge", "fact_check")]

    stages_timeline = []
    t = 0.0
    run_stages = []

    stages_timeline.append({"stage": "ingest", "start": t, "duration": durations.get("ingest", 0.5), "status": "active"})
    t += durations.get("ingest", 0.5)
    run_stages.append("ingest")

    if has_project:
        if enable_fan_out:
            fan_out = [s for s in ["domain_context", "cross_reference", "critic_a_multi", "critic_b_multi"] if s in active]
            if fan_out:
                max_dur = 0
                for s in fan_out:
                    dur = durations.get(s, 30)
                    stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
                    max_dur = max(max_dur, dur)
                    run_stages.append(s)
                t += max_dur
        else:
            for s in ["domain_context", "cross_reference"]:
                if s in active:
                    dur = durations.get(s, 30)
                    stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
                    t += dur
                    run_stages.append(s)
            dc_ctx_dur = max(
                durations.get("domain_context", 30),
                durations.get("cross_reference", 35),
            )
            for s in ["critic_a_multi", "critic_b_multi"]:
                if s in active:
                    dur = durations.get(s, 60)
                    stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
                    run_stages.append(s)
            critic_dur = max(
                durations.get("critic_a_multi", 60),
                durations.get("critic_b_multi", 60),
            )
            t += critic_dur

        if "deep_analysis" in active:
            dur = durations.get("deep_analysis", 25)
            stages_timeline.append({"stage": "deep_analysis", "start": t, "duration": dur, "status": "active"})
            t += dur
            run_stages.append("deep_analysis")

            if enable_early_exit:
                stages_timeline[-1]["early_exit"] = True
    else:
        for s in ["critic_a_multi", "critic_b_multi"]:
            if s in active:
                stages_timeline.append({"stage": s, "start": t, "duration": durations.get(s, 60), "status": "active"})
                run_stages.append(s)
        t += max(durations.get("critic_a_multi", 60), durations.get("critic_b_multi", 60))

    judge_tasks = [s for s in ["critic_a_judge", "critic_b_judge"] if s in active]
    if judge_tasks:
        max_dur = 0
        for s in judge_tasks:
            dur = durations.get(s, 20)
            stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
            max_dur = max(max_dur, dur)
            run_stages.append(s)
        t += max_dur

    for s in ["dedupe", "validate", "revise", "score", "report"]:
        if s in active:
            dur = durations.get(s, 5)
            stages_timeline.append({"stage": s, "start": t, "duration": dur, "status": "active"})
            t += dur
            run_stages.append(s)

    current_latency = _get_current_latency(durations, has_project)
    quality = 0.92 if enable_pruning else 0.98

    return {
        "profile": "custom",
        "total_latency_seconds": round(t, 1),
        "quality_confidence": quality,
        "stages_count": len(stages_timeline),
        "active_stages": run_stages,
        "timeline": stages_timeline,
        "savings_vs_current": round((1 - t / current_latency) * 100, 1) if current_latency > 0 else 0,
        "optimizations": {
            "early_exit": enable_early_exit,
            "fan_out": enable_fan_out,
            "pruning": enable_pruning,
        },
    }


def _get_current_latency(durations: dict, has_project: bool) -> float:
    result = _simulate_current(durations, has_project)
    return result["total_latency_seconds"]


def get_comparison() -> dict:
    config = load_pipeline_profile_config()
    durations = config.get("stage_durations", {})
    profiles = config.get("profiles", {})

    current = _simulate_current(durations, True)
    results = {"current": current}

    for name, profile in profiles.items():
        results[name] = _simulate_profile(name, profile, durations, True)

    custom = _simulate_custom(config, True, True, True, True)
    results["custom_all"] = custom

    return results
