---
sidebar_position: 4
title: 'Faz 1-1.5: Task Intake ve Context'
---

# Faz 1: TASK_INTAKE

Task'i kaynaktan okur ve analiz eder.

## Input Detection

Pipeline giris degerine gore task kaynagini otomatik tespit eder:

| Input Pattern | Kaynak | Arac |
|---------------|--------|------|
| `[A-Z]+-\d+` (orn: `PDB-12345`) | Jira | `jira_jira_get_issue` |
| `AB#\d+` veya `#\d+` (Azure config varsa) | Azure DevOps | `az boards work-item show` |
| `owner/repo#XXX` | GitHub Issues | `gh issue view` |
| `.md`, `.txt`, `.json` ile biten yol | Dosya | `read` araci |
| Diger her sey | Serbest metin | Oldugu gibi kullanilir |

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

Jira task'lari icin otomatik olarak:
- ADF (Atlassian Document Format) aciklamasi parse edilir
- Yorumlar okunur (son 20 yorum)
- Label'lar, assignee, priority bilgileri alinir

Detayli Jira kurulumu icin [DQG Jira Entegrasyonu](/dqg/jira-integration) dokumanina bakin.

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
