---
sidebar_position: 3
title: Pipeline Fazlari
---

# Pipeline Fazlari

Pipeline 11 fazdan olusur. Her faz belirli bir gorevi yerine getirir ve kullanici onayindan sonra bir sonrakine gecer.

## Faz Ozet Tablosu

| Faz | Ad | Goal | User Checkpoint | Detay |
|-----|----|------|-----------------|-------|
| 0 | DQG_ENSURE | DQG hazir mi kontrol et | Hayir | Otomatik |
| 1 | TASK_INTAKE | Task'i oku ve analiz et | **Evet** | [Detay](./task-intake) |
| 1.5 | CONTEXT_CHECK | Context mevcut mu kontrol et | **Evet** (gerekirse) | [Detay](./task-intake) |
| 2 | IMPL_DOC | Implementasyon dokumani olustur | **Evet** | [Detay](./impl-doc) |
| 3 | REVIEW_DOC | DQG ile dokuman review | **Evet** | [Detay](./dqg-review) |
| 4 | PLAN | TODO listesi olustur | **Evet** | [Detay](./planning) |
| 5 | REVIEW_TODO | 3-agent TODO review + judge | **Evet** | [Detay](./planning) |
| 6 | IMPLEMENT | Kodu yaz | Hayir | [Detay](./implementation) |
| 7 | REVIEW_IMPL | 3-agent impl review + judge | **Evet** | [Detay](./implementation) |
| 8 | TEST_PLAN | Test plani olustur | **Evet** | [Detay](./testing) |
| 9 | TEST | Test calistir | **Evet** | [Detay](./testing) |
| 10 | DONE | Ozet sun | Hayir | Pipeline sonu |

## Akis Diyagrami

```
Basla
  │
  ▼
[0] DQG_ENSURE ── basarisiz ──▶ Self-healing ──▶ tekrar dene
  │
  ▼ basarili
[1] TASK_INTAKE
  │
  ▼
  ◀ USER ONAY ── "Durdur" ──▶ BITIR
  │ "Onayliyorum"
  ▼
[1.5] CONTEXT_CHECK
  │ context var ──▶ [2]
  │ context yok ──▶ GENERATE_CONTEXT ──▶ ◀ USER ONAY ──▶ [2]
  │
  ▼
[2] IMPL_DOC
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[3] REVIEW_DOC (DQG)
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[4] PLAN (TODO listesi)
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[5] REVIEW_TODO (3 agent + judge)
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[6] IMPLEMENT (kod yazma)
  │
  ▼
[7] REVIEW_IMPL (3 agent + judge)
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[8] TEST_PLAN
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[9] TEST
  │
  ▼
  ◀ USER ONAY
  │
  ▼
[10] DONE ──▶ BITIR
```

## User Checkpoint'ler

Her checkpoint'te AI size sunlari sunar:

1. **Ozet** — o fazda ne yapildi
2. **Sonuclar** — skorlar, bulgular, degisen dosyalar
3. **Secenekler:**
   - `"Onayliyorum"` → sonraki faza gec
   - `"Sunu degistir: ..."` → degisikligi uygula ve tekrar sun
   - `"Durdur"` → pipeline'i durdur

## Kaldi Yerden Devam

Pipeline herhangi bir noktada durdurulabilir. "continue pipeline" veya "resume pipeline" dediginizde:

1. `.pipeline/{TASK_KEY}-state.json` okunur
2. `current_phase` belirlenir
3. Kaldigi fazdan devam eder

Detaylar icin [Sorun Giderme](./troubleshooting) sayfasina bakin.
