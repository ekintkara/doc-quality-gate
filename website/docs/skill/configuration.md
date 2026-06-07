---
sidebar_position: 10
title: Yapilandirma
---

# Yapilandirma

dev-pipeline skill'i projenizin `AGENTS.md` (veya `CLAUDE.md`) dosyasindan yapilandirma okur.

## Pipeline Config

`AGENTS.md` icinde `## Pipeline Config` bolumu olusturun:

```markdown
## Pipeline Config

task_source: jira                # jira | azure-devops | github | manual
dqg_repo: https://github.com/ekintkara/doc-quailty-gate.git
dqg_path: C:\repos\doc-quailty-gate
# azure_devops_org: myorg
# azure_devops_project: MyProject
# github_repo: owner/repo
context_path: .context/
review_agents: 3
max_review_iterations: 2
```

## Config Alanlari

| Alan | Zorunlu | Varsayilan | Aciklama |
|------|---------|------------|----------|
| `task_source` | Hayir | `jira` | Task kaynagi turu |
| `jira_tool` | Hayir | `auto` | Jira okuma yontemi: `auto`, `mcp`, `acli`, `api` |
| `dqg_repo` | Hayir | GitHub URL | DQG clone adresi |
| `dqg_path` | Hayir | OS'e gore | DQG kurulum dizini |
| `context_path` | Hayir | `.context/` | Context dosyalari yolu |
| `review_agents` | Hayir | `3` | Paralel review agent sayisi |
| `max_review_iterations` | Hayir | `2` | Maksimum DQG iterasyonu |
| `azure_devops_org` | Koşullu | - | Azure DevOps org adi |
| `azure_devops_project` | Koşullu | - | Azure DevOps proje adi |
| `github_repo` | Koşullu | - | GitHub repo (owner/repo) |

## Varsayilan Degerler

Config bulunamazsa su varsayilanlar kullanilir:

- **Windows:** `dqg_path` = `C:\repos\doc-quailty-gate`
- **Linux/macOS:** `dqg_path` = `~/doc-quality-gate`
- `review_agents` = 3
- `max_review_iterations` = 2

## DQG Konfigurasyonu

DQG'nin kendi yapilandirmasi `config/` dizininde bulunur. Detaylar icin:

- [DQG Configuration](/dqg/configuration) — app.yaml, pipeline profilleri
- [Pipeline Optimization](/dqg/pipeline-optimization) — fast track, early exit, complexity router
- [LiteLLM Proxy](/dqg/litellm-proxy) — proxy kurulumu ve model ayarlari

## Pipeline Profilleri

DQG farkli hiz/kalite profilleri destekler. Varsayilan `standard` profildir.

| Profil | Sure | Aciklama |
|--------|------|----------|
| `fast_track` | ~2-3dk | Kucuk degisiklikler, on bellege alma |
| `standard` | ~10dk | Genel kullanim, derin analiz atlar |
| `deep` | ~20-30dk | Kritik degisiklikler, tum analizler |

Profil secimi DQG tarafindan complexity router ile otomatik yapilabilir. Detaylar icin [Pipeline Optimization](/dqg/pipeline-optimization) dokumanina bakin.

## Task Kaynagi Kurulumu

Her task kaynagi icin ek kurulum gerekebilir:

### Jira

Jira icin 3 yontem desteklenir. `jira_tool` config'i ile zorlayabilir veya `auto` ile otomatik secime birakabilirsiniz.

**Yontem 1 — MCP (varsayilan):**
MCP Jira server kuruluysa otomatik kullanilir.

**Yontem 2 — Atlassian CLI (`acli`):**
```bash
# macOS
brew install acli

# Windows
winget install Atlassian.CLI

# Authenticate
acli jira auth login --site "mysite.atlassian.net" --email "user@email.com" --token
```

**Yontem 3 — REST API:**
`.env` dosyasina ekleyin:

```
DQG_JIRA_BASE_URL=https://your-domain.atlassian.net
DQG_JIRA_EMAIL=your@email.com
DQG_JIRA_API_TOKEN=your-api-token
DQG_JIRA_PROJECT=PROJ
```

Detaylar: [Jira Entegrasyonu](/dqg/jira-integration)

### Azure DevOps

```bash
az extension add --name azure-devops
az devops configure --defaults organization=https://dev.azure.com/{org} project={project}
```

### GitHub Issues

```bash
gh auth login
```

## Context Dosyalari

Context dizini su dosyalari icerebilir:

```
.context/
├── architecture.md    → Sistem mimarisi
├── conventions.md     → Coding convention'lari
├── domain.md          → Domain model
└── patterns.md        → Framework pattern'leri
```

Context yoksa pipeline otomatik olusturur (Faz 1.5). Detaylar icin [Task Intake ve Context](./task-intake) sayfasina bakin.
