---
slug: /
sidebar_position: 1
title: Genel Bakis
---

# dev-pipeline Skill

**Human-in-the-loop** development pipeline. Kod yazmadan once implementasyon dokumaninizi review edin, planlayin, uygulayin ve test edin.

## Ne Yapar?

dev-pipeline, bir task'i (Jira, Azure DevOps, GitHub Issues, dosya veya serbest metin) alir ve asagidaki sureci otomatik yonetir:

1. Task'i okur ve analiz eder
2. Implementasyon dokumani olusturur
3. DQG (Doc Quality Gate) ile dokumani kod tabanina karsi review eder
4. TODO listesi olusturur ve multi-agent ile review eder
5. Kodu yazar
6. Implementation'i multi-agent ile review eder
7. Test plani olusturur ve test calistirir

**Her adimda durur, ozet sunar, sizin onayinizi bekler.**

## Pipeline Akisi

```
DQG_ENSURE → TASK_INTAKE → [USER] → CONTEXT_CHECK → [USER] →
IMPL_DOC → [USER] → REVIEW_DOC(DQG) → VALIDATE_XREF → [USER] → PLAN → [USER] →
REVIEW_TODO → [USER] → IMPLEMENT → REVIEW_IMPL → [USER] →
TEST_PLAN → [USER] → TEST → [USER] → DONE
```

Her `[USER]` noktasinda AI durur ve sizin onayinizi bekler.

## Kritik Kurallar

1. **AI asla kod pushlamaz/commit etmez** — siz soylemedikce
2. **AI asla faz atlamaz** — her checkpoint'te onayiniz gerekli
3. **AI kullanici degisikliklerine adapte olur** — degisiklik yaparsaniz entegre eder
4. **DQG'ye her zaman `--project` gecirilir** — hedef proje yolu (CWD), asla DQG'nin dizini degil
5. **DQG sonuclari dogrulanir** — cross-reference bulgulari kod tabaninda grep ile dogrulanir, false positive'ler filtrelenir

## Desteklenen Task Kaynaklari

| Kaynak | Pattern | Ornek |
|--------|---------|-------|
| Jira | `[A-Z]+-\d+` | `PDB-12345` | MCP → `acli` → REST API |
| Azure DevOps | `AB#\d+` | `AB#456` |
| GitHub Issues | `owner/repo#XXX` | `ekintkara/dqg#42` |
| Dosya | `.md`, `.txt`, `.json` yolu | `docs/task.md` |
| Serbest Metin | Diger her sey | Aciklama metni |

## DQG Engine

Pipeline'in review motoru [Doc Quality Gate (DQG)](/dqg/architecture) engine'dir. DQG, implementasyon dokumaninizi kod tabaniniza karsi dogrular, multi-critic review yapar ve 8 boyutta skorlar.

DQG'nin calisma detaylari icin [DQG Engine dokumantasyonuna](/dqg/overview) bakabilirsiniz.

## Ne Zaman Kullanilir?

Asistaniniza asagidaki komutlardan herhangi birini soylediginizde pipeline baslar:

| Komut | Aciklama |
|-------|----------|
| `implement PDB-12345` | Jira task'ini uygular |
| `implement AB#456` | Azure DevOps work item'ini uygular |
| `implement ekintkara/repo#42` | GitHub issue'yu uygular |
| `/dev-pipeline docs/task.md` | Dosyadan task uygular |
| `/dev-pipeline Login sayfasina checkbox ekle` | Serbest metin ile task uygular |
| `continue pipeline` | Durdurulan pipeline'i devam ettirir |
| `resume pipeline` | Durdurulan pipeline'i devam ettirir |
| `bu taski implement et` | Dogal dil ile pipeline baslatir |

Detayli kullanim ornekleri icin [Hizli Baslangic](./quick-start#adim-3-pipeline-baslatin) sayfasina bakin.
