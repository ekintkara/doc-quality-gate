---
sidebar_position: 7
title: 'Faz 4-5: Planlama ve TODO Review'
---

# Faz 4: PLAN

Onaylanan implementasyon dokumanindan yapilandirilmis TODO listesi olusturur.

## Adimlar

1. Onaylanan implementasyon dokumani okunur (orijinal veya DQG-reviewed)
2. TODO Generator agent gorevlendirilir
3. TODO listesi `.pipeline/{TASK_KEY}-todo.md` olarak kaydedilir

## TODO Listesi Format

```markdown
# TODO List: {TASK_KEY}

## Phase 1: {Phase Name}
**Goal:** {phase goal}

### TODO 1.1: {title}
- **Why:** {reason}
- **How:** {step-by-step}
- **Acceptance Criteria:**
  - [ ] {criterion}
- **Files:** {files}
- **Risk:** {low/medium/high}

### TODO 1.2: {title}
...
```

## Kullaniciya Sunulan Format

```
📋 TODO LISTESI HAZIR

Toplam: 3 faz, 12 TODO

Faz ozetleri:
1. Backend API - 5 madde
2. Frontend UI - 4 madde
3. Test - 3 madde

Tam liste: .pipeline/PDB-12345-todo.md

Yantla: "Onayliyorum" → review'a gonderirim
         "Sunu degistir: ..." → degisikligi uygularim
         "Listeyi gormek istiyorum" → tamamini gosteririm
```

---

# Faz 5: REVIEW_TODO

3 paralel agent ile TODO listesini review eder + hakem (judge) ile sentezler.

## 3 Agent Review

Ayni anda 3 farkli perspektiften review yapilir:

| Agent | Perspektif | Inceler |
|-------|------------|---------|
| Agent 1 | **Completeness** | Eksik adim var mi? Tum gereksinimler kapsaniyor mu? |
| Agent 2 | **Order** | Faz siralamasi dogru mu? Bagimliliklar gozetilmis mi? |
| Agent 3 | **Practicality** | Adimlar uygulanabilir mi? Gercekci zaman ve risk tahmini var mi? |

**Her 3 agent ayni anda calisir** — paralel gorevlendirme sayesinde toplam sure tek agent kadar surer.

## Judge (Hakem)

3 agent'in sonuclarini toplar ve:

1. Ortak bulgulari belirler
2. Celiskileri cozer
5. Nihai karari verir: `APPROVED` / `MINOR_REVISION` / `MAJOR_REVISION`
6. Gerekli degisiklikleri listeler

## Cikti Dosyalari

```
.pipeline/
├── {TASK_KEY}-todo-review-1.md    → Agent 1 (Completeness)
├── {TASK_KEY}-todo-review-2.md    → Agent 2 (Order)
├── {TASK_KEY}-todo-review-3.md    → Agent 3 (Practicality)
└── {TASK_KEY}-todo-judge.md       → Judge karari
```

## Kullaniciya Sunulan Format

```
🔍 TODO REVIEW SONUCLARI

Judge Karari: MINOR_REVISION

Degisiklikler:
- TODO 2.3 onceligi medium → high (kritik bagimlilik)
- TODO 3.1 oncesine yeni TODO eklendi: error handling middleware
- Faz 2 ve 3 arasina integration test fazi onerildi

Guncel TODO: .pipeline/PDB-12345-todo.md

Yantla: "Onayliyorum" → implementasyona gecerim
         "Sunu degistir: ..." → degisikligi uygularim
```
