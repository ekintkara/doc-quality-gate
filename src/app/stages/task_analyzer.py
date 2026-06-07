from __future__ import annotations

from typing import Optional

import structlog

from app.integrations.jira_reader import JiraComment, JiraIssueData
from app.integrations.litellm_client import LiteLLMClient
from app.schemas import TaskAnalysis, TaskClarityStatus
from app.utils.text import extract_json_object

logger = structlog.get_logger("task_analyzer")


_REQUIRED_FIELDS = {
    "summary": "Görev başlığı/özeti eksik",
    "description": "Görev açıklaması eksik veya yetersiz",
    "acceptance_criteria": "Kabul kriterleri belirtilmemiş",
    "impacted_areas": "Etkilenen alanlar/kapsam belirtilmemiş",
    "target_environment": "Hedef ortam (stage/preprod/prod) belirtilmemiş",
    "dependencies": "Bağımlılıklar/blocker'lar belirtilmemiş",
}


def _evaluate_static_clarity(issue: JiraIssueData) -> tuple[float, list[str]]:
    missing: list[str] = []
    score = 10.0

    if not issue.summary.strip():
        missing.append("summary")
        score -= 2.0
    elif len(issue.summary.strip()) < 10:
        score -= 1.0

    if not issue.description.strip():
        missing.append("description")
        score -= 3.0
    elif len(issue.description.strip()) < 50:
        score -= 1.5

    if not issue.acceptance_criteria:
        missing.append("acceptance_criteria")
        score -= 2.0

    if not issue.impacted_areas:
        missing.append("impacted_areas")
        score -= 1.0

    if not issue.target_environment:
        score -= 0.5
        if not missing:
            missing.append("target_environment")

    if issue.dependencies == "none" or not issue.dependencies:
        score -= 0.5

    return max(score, 0.0), missing


def _enrich_with_comments(
    issue: JiraIssueData,
    comments: list[JiraComment],
) -> str:
    if not comments:
        return issue.description

    relevant_comments = []
    for c in comments:
        if c.body.startswith(("🤖", "❓")):
            continue
        relevant_comments.append(f"[{c.author}]: {c.body}")

    if not relevant_comments:
        return issue.description

    comments_text = "\n\n---\n### Yorumlar / Tartışmalar\n" + "\n".join(
        f"- {c}" for c in relevant_comments[:10]
    )
    return issue.description + comments_text


def _evaluate_with_llm(
    client: LiteLLMClient,
    issue: JiraIssueData,
    enriched_desc: str,
) -> Optional[dict]:
    prompt = f"""Bir Jira task'ını analiz et ve netliğini değerlendir.

Task: {issue.key}
Başlık: {issue.summary}
Açıklama:
{enriched_desc[:3000]}

Kabul Kriterleri: {', '.join(issue.acceptance_criteria) or 'Belirtilmemiş'}
Etkilenen Alanlar: {', '.join(issue.impacted_areas) or 'Belirtilmemiş'}
Hedef Ortam: {issue.target_environment or 'Belirtilmemiş'}
Bağımlılıklar: {issue.dependencies or 'Belirtilmemiş'}
Label'lar: {', '.join(issue.labels) or 'Yok'}
Öncelik: {issue.priority}
Atanan: {issue.assignee}

Bu task'ın implementasyon dökümanı hazırlamak için yeterliliğini 0-10 puanla.
Eksik veya belirsiz noktaları belirt.

JSON formatında yanıt ver:
{{
    "clarity_score": <0-10 arası puan>,
    "missing_fields": ["eksik_alan_1", "eksik_alan_2"],
    "missing_details": ["eksik_alan_1: detay", "eksik_alan_2: detay"],
    "strengths": ["güçlü_yön_1", "güçlü_yön_2"],
    "suggested_questions": ["geliştiriciye sorulacak soru 1", "soru 2"],
    "overall_assessment": "kısa değerlendirme"
}}

SADECE JSON döndür."""

    model = client.resolve_model("critic_a")
    try:
        response = client.chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": "Sen bir yazılım task analisti sin. JSON formatında yanıt ver."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
            stage="task_analyzer",
        )
        content = response.get("content", "")
        return extract_json_object(content)
    except Exception as e:
        logger.warning("llm_clarity_evaluation_failed", error=str(e))
        return None


def analyze_task(
    client: Optional[LiteLLMClient],
    issue: JiraIssueData,
    comments: Optional[list[JiraComment]] = None,
) -> TaskAnalysis:
    comments = comments or []

    static_score, missing = _evaluate_static_clarity(issue)
    enriched_desc = _enrich_with_comments(issue, comments)

    llm_result = None
    if client is not None:
        llm_result = _evaluate_with_llm(client, issue, enriched_desc)

    if llm_result:
        clarity_score = float(llm_result.get("clarity_score", static_score))
        llm_missing = llm_result.get("missing_fields", [])
        for field_name in llm_missing:
            if field_name not in missing:
                missing.append(field_name)
    else:
        clarity_score = static_score

    if clarity_score >= 7.0 and not missing:
        clarity_status = TaskClarityStatus.CLEAR
    elif clarity_score >= 4.0:
        clarity_status = TaskClarityStatus.NEEDS_CLARIFICATION
    else:
        clarity_status = TaskClarityStatus.INSUFFICIENT

    comments_summary = ""
    if comments:
        non_ai = [c for c in comments if not c.body.startswith(("🤖", "❓"))]
        if non_ai:
            comments_summary = "\n".join(f"[{c.author}]: {c.body[:200]}" for c in non_ai[:5])

    analysis = TaskAnalysis(
        task_key=issue.key,
        summary=issue.summary,
        description=issue.description,
        clarity_status=clarity_status,
        clarity_score=clarity_score,
        missing_fields=missing,
        acceptance_criteria=issue.acceptance_criteria,
        impacted_areas=issue.impacted_areas,
        target_environment=issue.target_environment,
        dependencies=issue.dependencies,
        labels=issue.labels,
        components=issue.components,
        reporter=issue.reporter,
        assignee=issue.assignee,
        priority=issue.priority,
        status=issue.status,
        created_date=issue.created,
        comments_summary=comments_summary,
        enriched_description=enriched_desc,
    )

    logger.info(
        "task_analyzed",
        key=issue.key,
        status=clarity_status.value,
        score=clarity_score,
        missing=missing,
    )

    return analysis
