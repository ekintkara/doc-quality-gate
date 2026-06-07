# dev-pipeline Skill: Complete Guide ile Karsilastirma Analizi

Anthropic'in "Complete Guide to Building Skills for Claude" dokumani ile mevcut skill arasindaki farklar ve yapilmasi gereken degisiklikler.

---

## 1. YAML Frontmatter — Eksik Alanlar

**Kaynak:** Reference B — YAML Frontmatter

### 1.1 `license` alani eksik
```yaml
# Mevcut
---
name: dev-pipeline
description: "..."
---

# Olmasi gereken
---
name: dev-pipeline
description: "..."
license: MIT
---
```

### 1.2 `metadata` alani eksik (author, version, category, tags)
```yaml
# Eklenecek
metadata:
  author: ekintkara
  version: 0.3.0
  category: development
  tags: [pipeline, code-review, testing, dqg]
  documentation: https://ekintkara.github.io/doc-quality-gate/
```

### 1.3 `allowed-tools` alani eksik
Skill hangi araçları kullanabileceğini belirtebilir. Bu, skill'in hangi araçlara erişeceğini kisitlar:
```yaml
# Opsiyonel ama onerilen
allowed-tools: "Bash(python:*) Bash(npm:*) Bash(gh:*) Bash(acli:*)"
```

### 1.4 `compatibility` alani eksik
Ortam gereksinimleri belirtilmeli:
```yaml
compatibility: "Requires Python 3.11+, Node.js 18+, and Git. Works with Claude Code, OpenCode, Cursor, and Claude.ai."
```

---

## 2. Dosya Yapisi — Standart Disi Dizin Adlari

**Kaynak:** Chapter 1 — File Structure

### 2.1 `prompts/` → `references/` standart degil
Guide standart yapisi: `scripts/`, `references/`, `assets/`. Biz `prompts/` kullaniyoruz.

**Oneri:** `prompts/` klasörü ismini koruyabilir (çalışıyor), ANCAK guide'ın önerdiği yapı:
```
dev-pipeline/
├── SKILL.md              # Required
├── CHANGELOG.md           # Version history
├── references/            # Dokumanlar (prompts/ yerine)
│   ├── dqg-ensure.md
│   ├── task-intake.md
│   ├── context-generator.md
│   ├── todo-generator.md
│   ├── todo-reviewer.md
│   ├── todo-judge.md
│   ├── doc-reviewer.md
│   ├── doc-judge.md
│   ├── implementer.md
│   └── test-planner.md
├── scripts/               # Calistirilabilir scriptler
│   └── dqg_run.py         # DQG wrapper (repo'daki scripts/ dizininden)
└── assets/                # Sablonlar
    └── impl-doc-template.md
```

**Karar:** `prompts/` → `references/` olarak yeniden adlandir. Guide'in progressive disclosure örneği `references/` kullanıyor. Tüm referans dosyaları SKILL.md'den bir seviye derinlikte olmalı.

### 2.2 `scripts/` dizini eksik
Guide önerisi: Deterministik islemler icin calistirilabilir scriptler ekleyin. Ornegin:
- `scripts/dqg_run.py` — DQG launcher wrapper
- `scripts/validate_pipeline.py` — Pipeline state validation

### 2.3 `assets/` dizini eksik
Template dosyalari icin ornegin `impl-doc-template.md`.

---

## 3. Description — Negative Triggers Eksik

**Kaynak:** Chapter 5 — Troubleshooting, "Skill triggers too often"

Mevcut description trigger frazeleri iceriyor ama **negative triggers** yok:

```yaml
# Mevcut
description: "...Use when: implement TASK-123, /dev-pipeline TASK-123, continue pipeline."

# Olmasi gereken — negative triggers ekle
description: "...Use when: implement TASK-123, /dev-pipeline TASK-123, continue pipeline.
Do NOT use for: general coding questions, single-file edits, git operations,
code explanations, or tasks that don't need a structured implementation pipeline."
```

---

## 4. SKILL.md Icerik Yapisi — Eksik Bolumler

**Kaynak:** Chapter 2 — Recommended Structure

Guide'in onerdiği yapida bizde olmayan bolumler:

### 4.1 Examples bolumu eksik
Kullanicilarin skill'in ne yapdigini anlamasi icin concrete ornekler:

```markdown
## Examples

### Example 1: Jira task
User says: "implement PROJ-123"
Result: Pipeline reads Jira task → generates impl doc → DQG review → TODO → implement → test

### Example 2: Free text
User says: "/dev-pipeline Add dark mode toggle to settings page"
Result: Pipeline creates impl doc from description → full review cycle

### Example 3: Resume
User says: "continue pipeline"
Result: Reads state file → resumes from last checkpoint
```

### 4.2 Troubleshooting bolumu eksik
Yaygin hatalar ve cozumleri:

```markdown
## Troubleshooting

### DQG won't start
Cause: Python or .venv missing
Solution: Run PHASE 0 again, check Python 3.11+ is installed

### Jira authentication failed
Cause: Missing or expired credentials
Solution: Check .env file or run `acli jira auth login`

### Pipeline stuck on REVIEW_DOC
Cause: DQG review takes 5-15 minutes
Solution: Check http://localhost:8080 dashboard, poll again
```

---

## 5. Pattern Uyumu

**Kaynak:** Chapter 5 — Patterns

Skill'imiz birden fazla pattern'e uyuyor:

| Pattern | Uyum | Not |
|---------|------|-----|
| Pattern 1: Sequential workflow | ✅ | 10 fazli sequential pipeline |
| Pattern 3: Iterative refinement | ✅ | DQG score < 8.0 → iterate |
| Pattern 4: Context-aware tool selection | ✅ | Jira: MCP → acli → REST API |
| Pattern 2: Multi-MCP coordination | ❌ | Tek MCP (DQG) kullaniyor |
| Pattern 5: Domain-specific intelligence | ✅ | DQG review expertise |

**Eklenmesi gereken:** SKILL.md body'sinde kullanicinin hangi pattern'i kullanacagini belirtmek gerekmiyor ama icerik yapisi acisindan pattern'leri tanimamiz faydali.

---

## 6. Progressive Disclosure — Duzeltme Gerekli

**Kaynak:** Chapter 1 — Progressive Disclosure

Uc seviye dogru kullanilmis:
1. ✅ YAML frontmatter (her zaman yuklu)
2. ✅ SKILL.md body (skill tetiklendiginde yuklu)
3. ⚠️ Linked files — calisiyor ama yol (path) referanslari standart degil

SKILL.md'de `prompts/` referanslari var:
```markdown
See `prompts/dqg-ensure.md`
```

Guide'in standardi `references/` kullanimi. Ayrica guide diyor ki: **"Keep references one level deep from SKILL.md."** Mevcut yapimiz bu kurala uyuyor — tum prompt dosyalari tek seviye derinlikte.

---

## 7. Testing — Hic Test Yok

**Kaynak:** Chapter 3 — Testing and Iteration

### 7.1 Triggering tests eksik
Skill'in dogru zamanda tetiklenip tetiklenmedigini test eden senaryolar yok.

### 7.2 Functional tests eksik
Pipeline'in her fazinin dogru calistigini test eden senaryolar yok.

### 7.3 Performance comparison eksik
Skill ile skill olmadan karsilastirma yapilan bir olcum yok.

**Oneri:** `tests/skill/` dizini altina test senaryolari olustur:

```markdown
# tests/skill/triggering.md

## Should trigger
- "implement PROJ-123"
- "/dev-pipeline PROJ-123"
- "implement AB#456"
- "implement owner/repo#42"
- "/dev-pipeline Add login page"
- "continue pipeline"
- "resume pipeline"
- "bu taski implement et"

## Should NOT trigger
- "What is 2+2?"
- "Help me write a Python function"
- "Explain this code"
- "git commit"
- "Fix this bug in auth.py"
```

---

## 8. Composability — Diger Skill'lerle Birlikte Calisma

**Kaynak:** Chapter 1 — Composability

> "Claude can load multiple skills simultaneously. Your skill should work well alongside others."

Mevcut skill diger skill'lerle conflict olusturabilir mi? Ornegin:
- Kullanici `sonar-analyze` skill'i ile birlikte kullanirsa?
- Kullanici `frontend-design` skill'i ile birlikte kullanirsa?

**Oneri:** SKILL.md'ye composability notu ekle:

```markdown
## Composability

This skill works alongside other skills. It focuses on the pipeline workflow
(task → doc → review → implement → test). Individual phases may benefit from
other skills (e.g., sonar-analyze for code quality, frontend-design for UI work).
```

---

## 9. "No README.md inside skill folder" Kurali

**Kaynak:** Chapter 2 — Critical Rules

> "Don't include README.md inside your skill folder. All documentation goes in SKILL.md or references/."

**Mevcut durum:** CHANGELOG.md var (bu bir sorun degil), README.md yok ✅.

---

## 10. Kullanici Deneyimi — "Instructions not followed" Riski

**Kaynak:** Chapter 5 — Instructions not followed

Guide'in onerisi: Kritik talimatlar icin `## Critical` veya `## Important` basliklari kullan.

**Mevcut:** `## Rules` bolumunde kritik kurallar var ama `## Critical` basligi kullanilmiyor.

**Oneri:** Rules bolumunu `## Critical Rules` olarak yeniden adlandir.

---

## Oncelik Sirasi

| Oncelik | Degisiklik | Efor |
|---------|-----------|------|
| **P0** | Frontmatter: `license`, `metadata`, `compatibility` ekle | Dusuk |
| **P0** | Description'a negative triggers ekle | Dusuk |
| **P1** | `prompts/` → `references/` klasorunu yeniden adlandir | Orta |
| **P1** | Examples bolumu ekle | Dusuk |
| **P1** | Troubleshooting bolumu ekle | Dusuk |
| **P2** | `scripts/` dizini olustur (dqg_run.py wrapper) | Orta |
| **P2** | `assets/` dizini olustur (impl-doc-template.md) | Dusuk |
| **P2** | Test senaryolari olustur (triggering + functional) | Yuksek |
| **P3** | `allowed-tools` frontmatter alani ekle | Dusuk |
| **P3** | Composability notu ekle | Dusuk |
| **P3** | `## Rules` → `## Critical Rules` | Dusuk |
