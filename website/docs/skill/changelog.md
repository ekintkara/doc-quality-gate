---
sidebar_position: 11
title: Changelog
---

# Changelog

dev-pipeline skill'in tum degisiklikleri burada belgelenir.

Her degisiklik icin changelog girdisi **zorunludur**. PR merge edilmeden once changelog kontrolu yapilir.

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
