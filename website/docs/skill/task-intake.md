---
sidebar_position: 4
title: 'Faz 1-1.5: Task Intake ve Context'
---

# Faz 1: TASK_INTAKE

Task'i kaynaktan okur ve analiz eder.

## Input Detection

Pipeline giris degerine gore task kaynagini otomatik tespit eder:

| Input Pattern | Kaynak | Arac (oncelik sirasi) |
|---------------|--------|------|
| `[A-Z]+-\d+` (orn: `PDB-12345`) | Jira | MCP tool → `acli` → REST API |
| `AB#\d+` veya `#\d+` (Azure config varsa) | Azure DevOps | `az boards work-item show` |
| `owner/repo#XXX` | GitHub Issues | `gh issue view` |
| `.md`, `.txt`, `.json` ile biten yol | Dosya | `read` araci |
| Diger her sey | Serbest metin | Oldugu gibi kullanilir |

## Kullanim Ornekleri

Pipeline'i farkli task kaynaklari ile baslatmak icin:

| Komut | Kaynak | Aciklama |
|-------|--------|----------|
| `implement PDB-12345` | Jira | Jira task'ini otomatik okur |
| `implement AB#456` | Azure DevOps | Azure DevOps work item'ini okur |
| `implement ekintkara/repo#42` | GitHub Issues | GitHub issue'yu okur |
| `/dev-pipeline docs/task.md` | Dosya | Dosya icerigini kullanir |
| `/dev-pipeline Login sayfasina checkbox ekle` | Serbest Metin | Metni task olarak kullanir |

Detayli kurulum ornekleri icin [Hizli Baslangic](./quick-start#adim-3-pipeline-baslatin) sayfasina bakin.

## Adimlar

1. Input parse edilir ve kaynak tespit edilir
2. Task kaynaktan okunur (baslik, aciklama, yorumlar, oncelik, tip)
3. Mevcut kod tabani `augmentcode_codebase-retrieval` ile incelenir
4. Kullaniciya ozet sunulur

## Kullaniciya Sunulan Format

```
📋 TASK OZETI
Kaynak: Jira | Key: PDB-12345 | Tip: Story | Oncelik: High

Ne yapilmasi gerekiyor:
- Kullanici profil sayfasina avatar yukleme ozelligi eklenmeli

Teknik durum:
- Profil sayfasi mevcut (`src/pages/Profile.tsx`)
- Backend API endpoint'i mevcut degil

Riskler:
- Dosya yukleme icin storage gerekiyor

Yantla: "Onayliyorum" → implementasyon dokumanina gecerim
         "Sunu degistir: ..." → degisikligi uygularim
         "Durdur" → pipeline'i durdururum
```

## Jira Entegrasyonu

Jira task'''lari icin 3 farkli yontem desteklenir (oncelik sirasina gore otomatik secilir):

| Oncelik | Yontem | Arac | Kosul |
|---------|--------|------|-------|
| 1 | MCP | `jira_jira_get_issue` | MCP Jira server kurulu |
| 2 | Atlassian CLI | `acli jira workitem view` | `acli` kurulu ve authenticate |
| 3 | REST API | `curl` | `.env` dosyasinda credentials |

**Ayarla:** `AGENTS.md` icinde `jira_tool: auto|mcp|acli|api` ile belirli bir yontemi zorlayabilirsiniz.

**Atlassian CLI (`acli`) ile kurulum:**
```bash
# macOS
brew install acli

# Windows
winget install Atlassian.CLI

# Authenticate
acli jira auth login --site "mysite.atlassian.net" --email "user@email.com" --token
```

Detayli Jira kurulumu icin [DQG Jira Entegrasyonu](/dqg/jira-integration) dokumanina bakin.

## Azure DevOps Entegrasyonu

Azure DevOps work item'lari icin:
- `AB#456` formati otomatik tespit edilir
- `az boards work-item show` ile okunur
- Azure config (`azure_devops_org`, `azure_devops_project`) tanimliysa `#456` formati da calisir

Kurulum icin `az extension add --name azure-devops` calistirin. Detaylar icin [Yapilandirma](./configuration#azure-devops) sayfasina bakin.

## GitHub Issues Entegrasyonu

GitHub issue'lar icin:
- `owner/repo#42` formati otomatik tespit edilir
- `gh issue view` ile okunur
- Baslik, govde, label'lar, assignee bilgileri alinir

Kurulum icin `gh auth login` calistirin. Detaylar icin [Yapilandirma](./configuration#github-issues) sayfasina bakin.

## Dosya ve Serbest Metin

Dosya veya serbest metin kullanimi icin herhangi bir ek kurulum gerekmez:
- Dosya yolu (`.md`, `.txt`, `.json`) verildiginde dosya icerigi okunur
- Serbest metin dogrudan task aciklamasi olarak kullanilir

---

# Faz 1.5: CONTEXT_CHECK / GENERATE_CONTEXT

DQG review ve implementasyon icin context'in mevcut olup olmadigini kontrol eder.

## Context Nedir?

Context, projenin mimarisi, domain bilgisi, coding convention'lari gibi bilgileri iceren dosya kumesidir. DQG review sirasinda dokumaninizi kod tabanina karsi dogrulamak icin kullanilir.

## Akis

```
CONTEXT_CHECK
  │
  ├─ Context mevcut mu? (AGENTS.md → CLAUDE.md → .context/ → README.md)
  │   │
  │   ├─ EVET → Context yolunu kaydet → [Faz 2: IMPL_DOC]
  │   │
  │   └─ HAYIR → Kullaniciya sor
  │       │
  │       ├─ Kullanici yol yapistirir → o yolu kullan
  │       │
  │       └─ Kullanici Enter'a basar → GENERATE_CONTEXT calisir
  │           │
  │           ▼
  │       Kod tabani analizi (augmentcode_codebase-retrieval)
  │           │
  │           ▼
  │       .pipeline/context/ dosyalari olusturulur
  │           │
  │           ▼
  │       ◀ USER ONAY
  │           │
  │           ▼
  │       [Faz 2: IMPL_DOC]
```

## Otomatik Olusturulan Context Dosyalari

Context yoksa, pipeline kod tabanini analiz edip su dosyalari olusturur:

```
.pipeline/context/
├── architecture.md    → Sistem mimarisi, moduller, veri akisi
├── conventions.md     → Coding convention'lari, pattern'ler, stil
├── domain.md          → Domain model, entity'ler, is kurallari
└── patterns.md        → Framework pattern'leri, yaygin yaklasimlar
```

## Context Auto-Discovery Sirasi

1. `AGENTS.md` (proje root)
2. `CLAUDE.md` (proje root)
3. `.context/` dizini
4. `GEMINI.md` (proje root)
5. `README.md` (proje root)
6. `augmentcode_codebase-retrieval` ile teknik analiz
7. Hicbiri bulunamazsa → kullaniciya sorulur

Context dosyalari DQG'ye `--cp {context_path}` parametresiyle aktarilir.
