from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.integrations.litellm_client import LiteLLMClient
from app.schemas import (
    FactCheckItem,
    FactCheckResult,
    Issue,
    ProposedFix,
    RealityVerdict,
    Validation,
)
from app.utils.text import extract_json_array

logger = structlog.get_logger("fact_check")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FACT_CHECK_PROMPT_FILE = str(_PROJECT_ROOT / "config" / "prompts" / "fact_check.md")


def _load_prompt() -> str:
    p = Path(FACT_CHECK_PROMPT_FILE)
    if p.exists():
        return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt file not found: {FACT_CHECK_PROMPT_FILE}")


def _load_json_safe(path: Path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return default
    return default


def _load_text_safe(path: Path, default="") -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return default


def _build_domain_violations_summary(domain_analysis: dict) -> str:
    violations = domain_analysis.get("domain_violations", [])
    if not violations:
        return "Domain ihlali bulunamadı."
    lines = []
    for v in violations:
        rule = v.get("rule", "Bilinmeyen kural")
        desc = v.get("description", "")
        evidence = v.get("evidence", "")
        lines.append(f"- **{rule}**: {desc}\n  Kanıt: {evidence}")
    return "\n".join(lines)


def _build_intentional_patterns_summary(domain_analysis: dict) -> str:
    patterns = domain_analysis.get("intentional_patterns", [])
    if not patterns:
        return "Kasıtlı desen bulunamadı."
    lines = []
    for p in patterns:
        pattern = p.get("pattern", "")
        evidence = p.get("domain_evidence", "")
        confidence = p.get("confidence", 0.0)
        lines.append(f"- **{pattern}** (güven: {confidence})\n  Kanıt: {evidence}")
    return "\n".join(lines)


def _build_validations_summary(validations: list[Validation]) -> str:
    if not validations:
        return "Önceki doğrulama sonucu bulunamadı."
    lines = []
    for v in validations:
        lines.append(
            f"- {v.issue_id}: {v.decision.value} (güven: {v.confidence:.2f}) — {v.reason}"
        )
    return "\n".join(lines)


def run_fact_check(
    client: LiteLLMClient,
    run_dir: Path,
) -> FactCheckResult:
    template = _load_prompt()

    issues_data = _load_json_safe(run_dir / "issues.json", [])
    issues = [Issue(**i) for i in issues_data]

    if not issues:
        logger.info("no_issues_to_fact_check")
        return FactCheckResult(
            items=[],
            confirmed_count=0,
            refuted_count=0,
            uncertain_count=0,
            summary="Değerlendirilecek sorun bulunamadı.",
        )

    domain_analysis = _load_json_safe(run_dir / "domain_analysis.json", {})
    meta_judge = _load_json_safe(run_dir / "meta_judge.json", {})
    scorecard = _load_json_safe(run_dir / "scorecard.json", {})
    validations_data = _load_json_safe(run_dir / "validations.json", [])
    validations = [Validation(**v) for v in validations_data]
    document_content = _load_text_safe(run_dir / "original.md")

    domain_violations_summary = _build_domain_violations_summary(domain_analysis)
    intentional_patterns_summary = _build_intentional_patterns_summary(domain_analysis)
    validations_summary = _build_validations_summary(validations)

    remaining_concerns = scorecard.get("remaining_concerns", [])
    if remaining_concerns:
        remaining_concerns_str = "\n".join(
            f"- {c}" for c in remaining_concerns
        )
    else:
        remaining_concerns_str = "Kalan endişe belirtilmedi."

    meta_judge_str = (
        json.dumps(meta_judge, indent=2, ensure_ascii=False)
        if meta_judge
        else "Meta-judge sonucu bulunamadı."
    )

    issues_json = json.dumps(
        [issue.model_dump() for issue in issues],
        indent=2,
        ensure_ascii=False,
    )

    prompt_text = (
        template.replace("{{issues_json}}", issues_json)
        .replace("{{domain_violations_json}}", domain_violations_summary)
        .replace("{{intentional_patterns_json}}", intentional_patterns_summary)
        .replace("{{meta_judge_json}}", meta_judge_str)
        .replace("{{remaining_concerns_json}}", remaining_concerns_str)
        .replace("{{validations_json}}", validations_summary)
        .replace("{{document_content}}", document_content)
    )

    messages = [
        {"role": "system", "content": "Sen bir doküman değerlendirme denetçisisin. SADECE geçerli JSON dizisi döndür."},
        {"role": "user", "content": prompt_text},
    ]

    model = client.resolve_model("meta_judge")
    logger.info("fact_check_start", model=model, issue_count=len(issues))

    response = client.chat_completion(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=8192,
        stage="fact_check",
    )

    content = response.get("content", "")
    raw_items = extract_json_array(content)

    fact_check_items: list[FactCheckItem] = []
    for raw in raw_items:
        try:
            verdict_str = raw.get("reality_verdict", "uncertain").lower()
            verdict = (
                RealityVerdict(verdict_str)
                if verdict_str in [v.value for v in RealityVerdict]
                else RealityVerdict.UNCERTAIN
            )

            score = float(raw.get("reality_score", 0.5))
            score = max(0.0, min(1.0, score))

            fix_data = raw.get("proposed_fix")
            proposed_fix = None
            if fix_data and verdict == RealityVerdict.CONFIRMED:
                proposed_fix = ProposedFix(
                    section=fix_data.get("section", ""),
                    current_text=fix_data.get("current_text", ""),
                    suggested_text=fix_data.get("suggested_text", ""),
                    fix_description=fix_data.get("fix_description", ""),
                )

            auto_applicable = raw.get("auto_applicable", False)
            if verdict != RealityVerdict.CONFIRMED or score < 0.8:
                auto_applicable = False

            item = FactCheckItem(
                issue_id=raw.get("issue_id", ""),
                reality_verdict=verdict,
                reality_score=score,
                evidence_for=raw.get("evidence_for", []),
                evidence_against=raw.get("evidence_against", []),
                proposed_fix=proposed_fix,
                auto_applicable=bool(auto_applicable),
            )
            fact_check_items.append(item)
        except Exception as e:
            logger.warning("fact_check_parse_error", error=str(e), raw=raw)

    confirmed = [i for i in fact_check_items if i.reality_verdict == RealityVerdict.CONFIRMED]
    refuted = [i for i in fact_check_items if i.reality_verdict == RealityVerdict.REFUTED]
    uncertain = [i for i in fact_check_items if i.reality_verdict == RealityVerdict.UNCERTAIN]

    result = FactCheckResult(
        items=fact_check_items,
        confirmed_count=len(confirmed),
        refuted_count=len(refuted),
        uncertain_count=len(uncertain),
        summary=_generate_summary(confirmed, refuted, uncertain, issues),
    )

    logger.info(
        "fact_check_done",
        total=len(fact_check_items),
        confirmed=len(confirmed),
        refuted=len(refuted),
        uncertain=len(uncertain),
    )

    return result


def _generate_summary(
    confirmed: list[FactCheckItem],
    refuted: list[FactCheckItem],
    uncertain: list[FactCheckItem],
    issues: list[Issue],
) -> str:
    lines = []
    lines.append(f"Toplam {len(issues)} sorun değerlendirildi.")
    lines.append(f"  ✅ {len(confirmed)} sorun ONAYLANDI (gerçek)")
    lines.append(f"  ❌ {len(refuted)} sorun ÇÜRÜTÜLDÜ (yanlış pozitif)")
    lines.append(f"  ❓ {len(uncertain)} sorun BELİRSİZ")

    if confirmed:
        lines.append("")
        lines.append("Onaylanan sorunlar:")
        issue_map = {i.id: i for i in issues}
        for c in confirmed:
            issue = issue_map.get(c.issue_id)
            title = issue.title if issue else c.issue_id
            lines.append(f"  - [{c.issue_id}] {title} (gerçeklik: {c.reality_score:.0%})")

    if refuted:
        lines.append("")
        lines.append("Çürütülen sorunlar (yanlış pozitif):")
        for r in refuted:
            reasons = "; ".join(r.evidence_against[:2]) if r.evidence_against else "Kasıtlı tasarım kararı"
            lines.append(f"  - [{r.issue_id}] {reasons}")

    return "\n".join(lines)


def generate_fact_check_report_md(result: FactCheckResult) -> str:
    lines = []
    lines.append("# Sorun Gerçeklik Değerlendirmesi")
    lines.append("")
    lines.append(f"**Onaylanan:** {result.confirmed_count} | "
                 f"**Çürütülen:** {result.refuted_count} | "
                 f"**Belirsiz:** {result.uncertain_count}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for item in result.items:
        verdict_emoji = {
            RealityVerdict.CONFIRMED: "✅ ONAYLANDI",
            RealityVerdict.REFUTED: "❌ ÇÜRÜTÜLDÜ",
            RealityVerdict.UNCERTAIN: "❓ BELİRSİZ",
        }
        lines.append(f"## {item.issue_id} — {verdict_emoji[item.reality_verdict]}")
        lines.append(f"**Gerçeklik Skoru:** {item.reality_score:.0%}")
        lines.append("")

        if item.evidence_for:
            lines.append("**Destekleyen Kanıtlar:**")
            for e in item.evidence_for:
                lines.append(f"- {e}")
            lines.append("")

        if item.evidence_against:
            lines.append("**Karşı Kanıtlar:**")
            for e in item.evidence_against:
                lines.append(f"- {e}")
            lines.append("")

        if item.proposed_fix:
            lines.append("**Önerilen Düzeltme:**")
            lines.append(f"- **Bölüm:** {item.proposed_fix.section}")
            lines.append(f"- **Açıklama:** {item.proposed_fix.fix_description}")
            if item.proposed_fix.current_text:
                lines.append(f"- **Mevcut Metin:** {item.proposed_fix.current_text}")
            if item.proposed_fix.suggested_text:
                lines.append(f"- **Önerilen Metin:** {item.proposed_fix.suggested_text}")
            lines.append(f"- **Otomatik Uygulanabilir:** {'Evet' if item.auto_applicable else 'Hayır'}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Özet")
    lines.append(result.summary)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Düzeltme Uygulama")
    lines.append("")
    lines.append("Onaylanan düzeltmeleri uygulamak için:")
    lines.append("1. Aşağıdaki dosyayı oluşturun: `approved_fixes.json`")
    lines.append("2. Onayladığınız sorun ID'lerini ekleyin")
    lines.append("3. `dqg apply-fixes <run_id>` komutunu çalıştırın")
    lines.append("")
    lines.append("Örnek `approved_fixes.json`:")
    lines.append("```json")
    lines.append('{')
    lines.append('  "run_id": "<run_id>",')
    confirmed_ids = [i.issue_id for i in result.items if i.reality_verdict == RealityVerdict.CONFIRMED]
    lines.append(f'  "approved_fix_ids": {json.dumps(confirmed_ids)}')
    lines.append('}')
    lines.append("```")

    return "\n".join(lines)


def apply_approved_fixes(
    client: LiteLLMClient,
    run_dir: Path,
    approved_fix_ids: list[str],
) -> str:
    fact_check_data = _load_json_safe(run_dir / "fact_check.json", {})
    if not fact_check_data:
        raise ValueError(f"Fact check sonucu bulunamadı: {run_dir}")

    fact_check_result = FactCheckResult(**fact_check_data)
    fix_map = {item.issue_id: item for item in fact_check_result.items}

    fixes_to_apply = []
    for fix_id in approved_fix_ids:
        item = fix_map.get(fix_id)
        if not item:
            logger.warning("fix_id_not_found", fix_id=fix_id)
            continue
        if item.reality_verdict != RealityVerdict.CONFIRMED:
            logger.warning("fix_not_confirmed", fix_id=fix_id, verdict=item.reality_verdict.value)
            continue
        if not item.proposed_fix:
            logger.warning("fix_no_proposal", fix_id=fix_id)
            continue
        fixes_to_apply.append(item)

    if not fixes_to_apply:
        logger.info("no_fixes_to_apply")
        original = _load_text_safe(run_dir / "original.md")
        return original

    original_content = _load_text_safe(run_dir / "original.md")

    fixes_json = json.dumps(
        [
            {
                "issue_id": f.issue_id,
                "section": f.proposed_fix.section,
                "fix_description": f.proposed_fix.fix_description,
                "current_text": f.proposed_fix.current_text,
                "suggested_text": f.proposed_fix.suggested_text,
            }
            for f in fixes_to_apply
        ],
        indent=2,
        ensure_ascii=False,
    )

    prompt = f"""Sen bir doküman düzelticisin. Aşağıdaki dokümana SADECE belirtilen düzeltmeleri uygula.

KURALLAR:
1. Orijinal doküman yapısını ve başlıklarını koru
2. Orijinal tonu ve üslubu koru — aşırı yeniden yazma yapma
3. Her bir düzeltmeyi uygula, başka değişiklik yapma
4. Çıktı olarak SADECE düzeltilmiş markdown dokümanını ver
5. Meta yorum ekleme — sadece düzeltilmiş dokümanı ver

ORİJİNAL DOKÜMAN:
{original_content}

UYGULANACAK DÜZELTMELER:
{fixes_json}

Düzeltilmiş dokümanı çıktı olarak ver."""

    messages = [
        {
            "role": "system",
            "content": (
                "Sen bir doküman düzelticisin. "
                "SADECE düzeltilmiş markdown dokümanını çıktı ver."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    model = client.resolve_model("reviser")
    logger.info("apply_fixes_start", model=model, fix_count=len(fixes_to_apply))

    response = client.chat_completion(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=16384,
        stage="apply_fixes",
    )

    fixed = response.get("content", original_content)

    if fixed.strip().startswith("```"):
        lines = fixed.strip().split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        fixed = "\n".join(lines)

    logger.info("apply_fixes_done", original_length=len(original_content), fixed_length=len(fixed))
    return fixed
