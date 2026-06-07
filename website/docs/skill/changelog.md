---
sidebar_position: 11
title: Changelog
---

# Changelog

dev-pipeline skill'in tum degisiklikleri burada belgelenir.

Her degisiklik icin changelog girdisi **zorunludur**. PR merge edilmeden once changelog kontrolu yapilir.

## [0.5.0] - 2026-06-08

### Fixed
- **Kritik:** DQG cross-reference C#/.NET projelerde false positive uretiyordu
  - Sebep: `codebase_context.py` C# pattern destegi yoktu — ASP.NET controller, endpoint, entity, interface bulunamiyordu
  - C# ASP.NET route pattern'leri eklendi: `[HttpGet]`, `[HttpPost]`, `[Route]`, `MapGet`/`MapPost`
  - C# entity/model algilama eklendi: `class`, `record` + property cikarma
  - `_extract_csharp_properties()` yardimci fonksiyonu eklendi
  - `.csproj` dependency cikarma eklendi (`<PackageReference>` parsing)
  - `.cs` dosya uzantisi taramaya eklendi
- **Kritik:** DQG review sonuclari dogrulanmadan kullaniciya sunuluyordu
  - Critical Rule #5 eklendi: DQG sonuclarini dogrula, false positive'lari isaretle
  - Phase 3.1 (VALIDATE_XREF) eklendi: "eksik" denen ogeleri kodda ara, dogrula

## [0.4.0] - 2026-06-08

### Changed
- **`prompts/` → `references/`** klasor yeniden adlandirildi (Anthropic skill standardi)
- `## Rules` → `## Critical Rules` (kritik talimatlar vurgulandi)
- SKILL.md referanslari guncellendi (`prompts/` → `references/`)
- Description'a negative triggers eklendi ("Do NOT use for: ...")

### Fixed
- **Kritik:** DQG review yanlis codebase'i referans aliyordu (kendi Python kodu, hedef proje yerine)
  - Sebep: `--project` parametresi `launch` komutuna gecilmiyordu
  - Cozum: Critical Rule #4 eklendi — DQG'ye HER ZAMAN `--project` gecirilmeli
  - Cozum: `scripts/dqg_run.py` eksik `--project` durumunda otomatik CWD'yi kullaniyor
  - Cozum: `scripts/dqg_run.py` `--project` DQG'nin kendi dizinine mi diye dogruluyor
  - Cozum: Phase 3 aciklamasinda ornek komut ve uyari eklendi

### Added
- YAML frontmatter: `license`, `metadata` (author, version, category, tags, docs), `compatibility`
- `## Examples` bolumu: 4 kullanim senaryosu (Jira, Azure, Serbest metin, Resume)
- `## When to Use` altina "Do NOT use when" alt bolumu
- `## Troubleshooting` bolumu (DQG baslatma, Jira auth, review takilmasi, context hatasi)
- `## Composability` notu (diger skill'lerle birlikte kullanim)
- `scripts/dqg_run.py` wrapper (DQG kurulumunu otomatik bulur)
- `assets/impl-doc-template.md` (standart implementasyon dokumani sablonu)
- DQG yol aramasi artik `~/Desktop/doc-quality-gate` konumunu da iceriyor

### Removed
- `## Version` bolumu SKILL.md'den kaldirildi (sadece developer-notu, kullaniciya gorunmemeli)

## [0.3.0] - 2026-06-08

### Changed
- **SKILL.md 686→116 satir:** Faz detaylari `prompts/` dosyalarina tasindi (progressive disclosure)
- Golden Rules 7→3 madde
- Kullanici sunum sablonlari kaldirildi (Claude formati kendisi belirler)
- 100+ satirlik prompt dosyalarina TOC eklendi
- Tum Windows backslash path'leri forward slash'a cevrildi

### Added
- Atlassian CLI (`acli`) destegi: Jira okuma fallback (MCP → `acli` → REST API)
- `jira_tool` config secenegi: `auto | mcp | acli | api`
- Tum task kaynagi kullanim ornekleri dokumanlara eklendi

### Removed
- Tum obilet-spesifik referanslar (hardcoded URL'ler, path'ler, proje key'leri, emailler)
- Hardcoded Jira default'lari — artik env var veya config zorunlu

## [0.2.0] - 2026-06-07

### Added
- GitHub Pages deployment workflow
- GitHub Pages aktif edildi (GitHub Actions build)
- Docusaurus `baseUrl` duzeltmesi (`/doc-quality-gate/` → `/doc-quailty-gate/`)
- Repo adindaki typo duzeltmeleri (`doc-quality-gate` → `doc-quailty-gate`)

## [0.1.0] - 2026-06-07

### Added
- Ilk skill release: 10 fazli human-in-the-loop pipeline
- Task kaynaklari: Jira (MCP), Azure DevOps, GitHub Issues, Dosya, Serbest metin
- DQG engine entegrasyonu (multi-agent dokuman review)
- Context auto-generation (codebase analizi)
- Multi-agent TODO review (completeness, order, practicality + judge)
- Multi-agent implementation review (compliance, quality, pattern + judge)
- Test planlama ve calistirma fazlari
- Pipeline state file ile resume destegi
- 11 prompt dosyasi (`prompts/` dizini)
