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
DQG_ENSURE → TASK_INTAKE → [USER] → CONTEXT_CHECK → (GENERATE_CONTEXT → [USER]) →
IMPL_DOC → [USER] → REVIEW_DOC(DQG) → [USER] → PLAN → [USER] → REVIEW_TODO → [USER] →
IMPLEMENT → REVIEW_IMPL → [USER] → TEST_PLAN → [USER] → TEST → [USER] → DONE
```

Her `[USER]` noktasinda AI durur ve sizin onayinizi bekler.

## Golden Rules

1. **AI asla kod pushlamaz** — siz soylemedikce
2. **AI asla faz atlamaz** — sizin onayiniz olmadan
3. **AI asla commit etmez** — siz "commit" demedikce
4. **Her completed work oncesinde ozet sunulur**
5. **Her faz gecisinde onay istenir**
6. **Kullanici degisiklik yaptiysa adapte olur**
7. **AI otonom degildir** — karar verici sizsiniz

## Desteklenen Task Kaynaklari

| Kaynak | Pattern | Ornek |
|--------|---------|-------|
| Jira | `[A-Z]+-\d+` | `PDB-12345` |
| Azure DevOps | `AB#\d+` | `AB#456` |
| GitHub Issues | `owner/repo#XXX` | `ekintkara/dqg#42` |
| Dosya | `.md`, `.txt`, `.json` yolu | `docs/task.md` |
| Serbest Metin | Diger her sey | Aciklama metni |

## DQG Engine

Pipeline'in review motoru [Doc Quality Gate (DQG)](/dqg/architecture) engine'dir. DQG, implementasyon dokumaninizi kod tabaniniza karsi dogrular, multi-critic review yapar ve 8 boyutta skorlar.

DQG'nin calisma detaylari icin [DQG Engine dokumantasyonuna](/dqg/overview) bakabilirsiniz.

## Ne Zaman Kullanilir?

- "implement PDB-12345" / "implement AB#456" dediginizde
- "/dev-pipeline PDB-12345" dediginizde
- "bu taski implement et" dediginizde
- "continue pipeline" / "resume pipeline" dediginizde
