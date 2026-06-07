from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from app.integrations.litellm_client import LiteLLMClient
from app.schemas import TaskAnalysis, TaskClarityStatus
from app.stages.domain_context import _load_structured_context, index_context_files, load_context_files
from app.utils.files import write_text
from app.utils.text import extract_json_array, extract_json_object

logger = structlog.get_logger("document_generator")


_ALWAYS_INCLUDE = {"architecture.md", "conventions.md", "common-patterns.md", "api-pipeline.md"}


def _select_relevant_context(
    client: LiteLLMClient,
    context_path: str,
    analysis: TaskAnalysis,
    max_chars: int = 50000,
) -> str:
    cp = Path(context_path).resolve()
    if not cp.exists() or not cp.is_dir():
        logger.warning("context_path_invalid", path=str(cp))
        return ""

    file_index = index_context_files(cp)
    if not file_index:
        logger.warning("context_path_empty", path=str(cp))
        return ""

    if len(file_index) <= 5:
        logger.info("context_small_skip_filter", files=len(file_index))
        all_paths = [f["path"] for f in file_index]
        return load_context_files(cp, all_paths, max_chars=max_chars)

    task_desc = (analysis.description or "")[:500]
    task_summary = analysis.summary or ""
    impacted = ", ".join(analysis.impacted_areas or [])
    labels = ", ".join(analysis.labels or [])
    components = ", ".join(analysis.components or [])

    file_list_json = json.dumps(
        [{"path": f["path"], "lines": f["lines"], "preview": f["preview"][:200]} for f in file_index],
        indent=2,
        ensure_ascii=False,
    )

    prompt = f"""Bir yazilim task'i icin domain context dosyalarindan hangileri ilgili?

Task: {analysis.task_key}
Baslik: {task_summary}
Etkilenen Alanlar: {impacted}
Label'lar: {labels}
Bilesenler: {components}
Aciklama: {task_desc}

Kullanilabilir dosyalar:
{file_list_json}

KURALLAR:
1. Task ile dogrudan ilgili domain dosyalarini sec (orn: flight task'i icin flight.md)
2. Mimari ve pattern dosyalari (architecture.md, conventions.md, api-pipeline.md) her zaman ilgili
3. Yeni kod yazilacaksa rehber dosyalar (new-controller.md, new-service.md vb.) ilgili
4. payments.md, notifications.md, localization.md gibi cross-cutting konulara dikkat et
5. Ilgisiz domain dosyalarini (orn: flight task'i icin hotel.md, sea.md) ISARETLEME

JSON formatinda yanit ver - bir array:
[{{"path": "dosya/yolu.md", "relevant": true, "reason": "kisa aciklama"}}]

SADECE JSON döndür."""

    model = client.resolve_model("critic_a")

    response = client.chat_completion(
        model=model,
        messages=[
            {"role": "system", "content": "Sen bir dosya iliskilendirme asistanisin. Sadece JSON döndür."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
        stage="context_filter",
    )

    content = response.get("content", "")

    classifications = extract_json_array(content)
    if not classifications:
        logger.warning("context_filter_parse_failed", snippet=content[:300])
        all_paths = [f["path"] for f in file_index]
        return load_context_files(cp, all_paths, max_chars=max_chars)

    selected_paths: list[str] = []
    for item in classifications:
        if item.get("relevant"):
            selected_paths.append(item["path"])

    always_paths = [f["path"] for f in file_index if f["filename"] in _ALWAYS_INCLUDE]
    for p in always_paths:
        if p not in selected_paths:
            selected_paths.insert(0, p)

    if not selected_paths:
        logger.warning("context_filter_nothing_selected")
        all_paths = [f["path"] for f in file_index]
        return load_context_files(cp, all_paths, max_chars=max_chars)

    logger.info(
        "context_filtered",
        total_files=len(file_index),
        selected=len(selected_paths),
        paths=selected_paths,
    )

    return load_context_files(cp, selected_paths, max_chars=max_chars)


_TEMPLATE = """# {title}

**Task:** {task_url}
**Öncelik:** {priority} | **Durum:** {status}
**Atanan:** {assignee} | **Raporlayan:** {reporter}
**Oluşturulma:** {created_date}

---

## 1. Özet

{summary}

{clarity_warning}

## 2. Arka Plan ve Bağlam

{background}

## 3. Teknik Gereksinimler

{requirements}

## 4. Kabul Kriterleri

{acceptance_criteria}

## 5. Etkilenen Alanlar

{impacted_areas}

## 6. Uygulama Adımları

{implementation_steps}

## 7. Bağımlılıklar ve Engelleyiciler

{dependencies}

## 8. Risk Değerlendirmesi

{risk_assessment}

## 9. Test Stratejisi

{test_strategy}

## 10. Geri Alma Planı

{rollback_plan}

---

*Bu döküman otomatik olarak Doc Quality Gate tarafından Jira task'tan üretilmiştir.*
*Task Analiz Skoru: {clarity_score}/10 | Netlik Durumu: {clarity_status}*
*Üretim Tarihi: {generation_date}*
"""


def _generate_with_llm(
    client: LiteLLMClient,
    analysis: TaskAnalysis,
    context_path: Optional[str] = None,
) -> dict:
    context_snippet = ""
    if context_path:
        try:
            context_snippet = _select_relevant_context(client, context_path, analysis)
        except Exception as e:
            logger.warning("context_filter_failed_using_fallback", error=str(e))
            cp = Path(context_path).resolve()
            context_snippet = _load_structured_context(cp)
            if context_snippet and len(context_snippet) > 8000:
                context_snippet = context_snippet[:8000] + "\n\n[... context truncated ...]"

    context_block = ""
    if context_snippet:
        context_block = f"""
## PROJE DOMAIN CONTEXT

Asagida bu projenin domain context bilgisi yer almaktadir.
Implementasyon dökümanini bu context'e uygun, spesifik ve implementasyon için kullanilabilir şekilde yaz.
Mevcut pattern'leri, sinif isimlerini, API yapilarini ve mimari kararlarini referans al.

{context_snippet}
"""

    prompt = f"""Bir Jira task'indan implementasyon dökümani bölümleri üret.

Task: {analysis.task_key}
Baslik: {analysis.summary}
Aciklama:
{analysis.enriched_description[:4000]}

Kabul Kriterleri: {', '.join(analysis.acceptance_criteria) or 'Belirtilmemis'}
Etkilenen Alanlar: {', '.join(analysis.impacted_areas) or 'Belirtilmemis'}
Hedef Ortam: {analysis.target_environment or 'Belirtilmemis'}
Bagimliliklar: {analysis.dependencies or 'Belirtilmemis'}
Label'lar: {', '.join(analysis.labels) or 'Yok'}
Bilesenler: {', '.join(analysis.components) or 'Yok'}
Oncelik: {analysis.priority}
Atanan: {analysis.assignee}

{f"Yorumlar/Tartismalar: {analysis.comments_summary}" if analysis.comments_summary else ""}
{context_block}
Bu task için implementasyon dökümaninin asagidaki bölümlerini doldur.
Her bölümü detayli ve implementasyon için kullanilabilir sekilde yaz.
Teknik terimler kullan, somut adimlar belirt.
Domain context'te belirtilen sinif isimlerini, API endpoint'lerini, veritabani tablolarini
ve mimari pattern'leri dogrudan referans al.
{"Özellikle context'teki mevcut kod yapisina uygun adimlar ve dosya isimleri belirt." if context_snippet else ""}

JSON formatinda yanit ver:
{{
    "background": "Arka plan ve baglam aciklamasi (2-4 paragraf, domain context'teki bilgiyi kullan)",
    "requirements": "Teknik gereksinimler (madde madde, detayli, domain context'teki API/model referanslarini iceren)",
    "implementation_steps": "Uygulama adimlari (numarali, her adim alt görevleriyle birlikte, spesifik dosya/sinif isimleriyle)",
    "risk_assessment": "Risk degerlendirmesi (riskler, olasilik, etki, azaltma stratejileri, domain-specific riskler)",
    "test_strategy": "Test stratejisi (birim, entegrasyon, E2E, manuel test senaryolar, domain context'teki yapiya uygun)",
    "rollback_plan": "Geri alma plani (adimlar, kosullar, sorumluluklar, domain-specific geri alma adimlari)"
}}

SADECE JSON döndür, baska metin ekleme."""

    model = client.resolve_model("critic_a")

    system_msg = (
        "Sen bir yazilim mimarasin. Detayli implementasyon "
        "dökümanlari yazarsin. JSON formatinda yanit ver."
    )
    if context_snippet:
        system_msg = (
            "Sen bu projenin yazilim mimarasin. Verilen domain context bilgisini "
            "kullanarak, projenin mevcut kod yapisina, mimarisine ve pattern'lerine "
            "uygun detayli implementasyon dökümanlari yazarsin. "
            "Mevcut sinif isimlerini, API endpoint'lerini, veritabani tablolarini "
            "dogrudan referans al. Generic/placeholder metin yazma. "
            "JSON formatinda yanit ver."
        )

    response = client.chat_completion(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_msg,
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
        stage="document_generator",
    )
    content = response.get("content", "")
    logger.debug(
        "llm_raw_response",
        length=len(content),
        first_200=content[:200],
    )
    parsed = extract_json_object(content)
    if parsed:
        for key, val in parsed.items():
            if not isinstance(val, str):
                parsed[key] = str(val)
        logger.info("llm_sections_parsed", keys=list(parsed.keys()))
    else:
        logger.warning(
            "llm_json_parse_failed",
            length=len(content),
            snippet=content[:500],
        )
    return parsed or {}


def _build_fallback_sections(analysis: TaskAnalysis) -> dict:
    return {
        "background": (
            analysis.enriched_description or analysis.description
            or "Bu bölüm Jira task açıklamasından oluşturulmuştur."
        ),
        "requirements": (
            "- Task açıklamasındaki gereksinimler uygulanacaktır.\n"
            "- Detaylı gereksinim analizi için task ile iletişime geçiniz.\n"
            f"- Label'lar: {', '.join(analysis.labels) or 'Yok'}\n"
            f"- Bileşenler: {', '.join(analysis.components) or 'Yok'}"
        ),
        "implementation_steps": (
            "1. Task detaylarını analiz et\n"
            "2. Etkilenen kod bölgelerini belirle\n"
            "3. Değişiklikleri uygula\n"
            "4. Birim testleri yaz/çalıştır\n"
            "5. Code review gönder\n"
            "6. Stage ortamına deploy et\n"
            "7. QA doğrulaması yap\n"
            "8. Preprod/Prod dağıtımını tamamla"
        ),
        "risk_assessment": (
            "- **Düşük Risk**: Standart geliştirme süreci\n"
            f"- Etkilenen alanlar: {', '.join(analysis.impacted_areas[:3]) or 'Belirsiz'}\n"
            "- Geri alma: feature branch üzerinden revert"
        ),
        "test_strategy": (
            "- Birim testleri: Etkilenen modüller için yazılmalı\n"
            f"- Entegrasyon testleri: {', '.join(analysis.impacted_areas[:2]) or 'İlgili'} "
            "katmanı için\n"
            "- Manuel test: Kabul kriterlerine göre doğrulanmalı"
        ),
        "rollback_plan": (
            "- Feature branch üzerinden revert commit\n"
            "- Stage ortamında doğrulama\n"
            "- Hotfix süreci gerekirse uygulanır"
        ),
    }


def _format_parsed_obj(parsed: object) -> str:
    if isinstance(parsed, list):
        lines = []
        for i, item in enumerate(parsed, 1):
            if isinstance(item, dict):
                sub = "; ".join(f"**{k}:** {v}" for k, v in item.items())
                lines.append(f"{i}. {sub}")
            else:
                lines.append(f"{i}. {item}")
        return "\n".join(lines)
    if isinstance(parsed, dict):
        return "\n".join(f"- **{k}:** {v}" for k, v in parsed.items())
    return str(parsed)


def _normalize_llm_text(value: str) -> str:
    if not isinstance(value, str):
        value = str(value)

    stripped = value.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        parsed = None
        try:
            import json

            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            try:
                import ast

                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                pass
        if parsed is not None:
            return _format_parsed_obj(parsed)

    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    value = value.replace("\\n", "\n")
    value = value.replace("\\t", "\t")
    value = value.replace('\\"', '"')

    return value


def generate_document(
    client: Optional[LiteLLMClient],
    analysis: TaskAnalysis,
    output_dir: Optional[str] = None,
    context_path: Optional[str] = None,
) -> tuple[str, str]:
    logger.info("document_generation_start", key=analysis.task_key, context_path=context_path)

    llm_sections = {}
    if client is not None:
        try:
            llm_sections = _generate_with_llm(client, analysis, context_path=context_path)
            logger.info("document_generation_llm_done", sections=len(llm_sections))
        except Exception as e:
            logger.warning("document_generation_llm_failed", error=str(e))

    fallback = _build_fallback_sections(analysis)

    background = llm_sections.get("background", "") or fallback["background"]
    requirements = llm_sections.get("requirements", "") or fallback["requirements"]
    implementation_steps = (
        llm_sections.get("implementation_steps", "")
        or fallback["implementation_steps"]
    )
    risk_assessment = (
        llm_sections.get("risk_assessment", "")
        or fallback["risk_assessment"]
    )
    test_strategy = llm_sections.get("test_strategy", "") or fallback["test_strategy"]
    rollback_plan = llm_sections.get("rollback_plan", "") or fallback["rollback_plan"]

    background = _normalize_llm_text(background)
    requirements = _normalize_llm_text(requirements)
    implementation_steps = _normalize_llm_text(implementation_steps)
    risk_assessment = _normalize_llm_text(risk_assessment)
    test_strategy = _normalize_llm_text(test_strategy)
    rollback_plan = _normalize_llm_text(rollback_plan)

    clarity_warning = ""
    if analysis.clarity_status != TaskClarityStatus.CLEAR:
        missing_str = (
            ", ".join(analysis.missing_fields)
            if analysis.missing_fields
            else "Belirsiz"
        )
        clarity_warning = (
            f"\n> **⚠️ Netlik Uyarısı:** Bu task "
            f"{analysis.clarity_status.value} durumunda.\n"
            f"> Analiz Skoru: {analysis.clarity_score:.1f}/10\n"
            f"> Eksik alanlar: {missing_str}\n"
            "> Üretilen döküman bu eksiklikleri içerebilir. "
            "Tamamlanması önerilir.\n"
        )

    if analysis.acceptance_criteria:
        ac_lines = "\n".join(
            f"- [ ] {ac}" for ac in analysis.acceptance_criteria
        )
    else:
        ac_lines = "- Belirtilmemiş — geliştirici tarafından tanımlanmalı"

    if analysis.impacted_areas:
        areas_lines = "\n".join(
            f"- {area}" for area in analysis.impacted_areas
        )
    else:
        areas_lines = "- Belirtilmemiş"

    summary_text = (
        analysis.enriched_description[:500]
        if analysis.enriched_description
        else (analysis.description[:500] or "Özet mevcut değil.")
    )

    document = _TEMPLATE.format(
        title=analysis.summary or analysis.task_key,
        task_url=f"https://jira.example.com/browse/{analysis.task_key}",
        priority=analysis.priority or "N/A",
        status=analysis.status or "N/A",
        assignee=analysis.assignee or "N/A",
        reporter=analysis.reporter or "N/A",
        created_date=analysis.created_date or "N/A",
        summary=summary_text,
        clarity_warning=clarity_warning,
        background=background,
        requirements=requirements,
        acceptance_criteria=ac_lines,
        impacted_areas=areas_lines,
        implementation_steps=implementation_steps,
        dependencies=analysis.dependencies or "Belirtilmemiş",
        risk_assessment=risk_assessment,
        test_strategy=test_strategy,
        rollback_plan=rollback_plan,
        clarity_score=f"{analysis.clarity_score:.1f}",
        clarity_status=analysis.clarity_status.value,
        generation_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    filename = f"jira-{analysis.task_key}-impl-plan.md"

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / filename
        write_text(file_path, document)
        logger.info("document_saved", path=str(file_path))
        return str(file_path), document

    return filename, document
