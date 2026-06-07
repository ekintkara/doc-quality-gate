---
sidebar_position: 5
title: 'Faz 2: Implementasyon Dokumani'
---

# Faz 2: IMPL_DOC

Task analizi, kullanici geribildirisi ve kod tabani incelemesinden implementasyon dokumani olusturur.

## Adimlar

1. Onaylanan task ozeti ve kullanici geribildirisi okunur
2. Kod tabani `augmentcode_codebase-retrieval` ile detayli incelenir
3. Implementasyon dokumani olusturulur
4. `.pipeline/{TASK_KEY}-impl-doc.md` olarak kaydedilir

## Dokuman Template

Her implementasyon dokumani su yapidadir:

```markdown
# Implementation Document: {TASK_KEY}

## 1. Task Summary
- **Key:** {key}
- **Title:** {title}
- **Type:** {type}
- **Priority:** {priority}
- **Source:** {jira/azure-devops/github/manual}

## 2. Requirements Analysis
### 2.1 Functional Requirements
### 2.2 Non-Functional Requirements
### 2.3 Acceptance Criteria

## 3. Technical Analysis
### 3.1 Current State
### 3.2 Proposed Changes
### 3.3 Affected Components
### 3.4 Database Changes (if applicable)
### 3.5 API Changes (if applicable)

## 4. Implementation Plan
### 4.1 Phase 1: {name}
### 4.2 Phase 2: {name}

## 5. Risk Assessment
## 6. Dependencies
## 7. Testing Strategy
```

## Kullaniciya Sunulan Format

```
📝 IMPLEMENTASYON DOKUMANI HAZIR

Ozet:
- Kullanici profil sayfasina avatar yukleme ozelligi ekleniyor
- Toplam 3 faz, 8 degisiklik

Kritik noktalar:
- Yeni API endpoint gerekli: POST /api/users/avatar
- S3-compatible storage entegrasyonu lazim
- Mevcut profil formu genisletilecek

Etkilenen dosyalar: src/pages/Profile.tsx, src/api/users.ts, src/models/User.ts

Tam dokuman: .pipeline/PDB-12345-impl-doc.md

Yantla: "Onayliyorum" → DQG review'a gonderirim
         "Sunu degistir: ..." → degisikligi uygularim
         "Dokumani okumak istiyorum" → tamamini gosteririm
```

## Kullanici Secenekleri

| Yanit | Aksiyon |
|-------|---------|
| "Onayliyorum" | Faz 3: DQG Review'a gec |
| "Sunu degistir: ..." | Degisikligi uygula, dokumani guncelle, tekrar sun |
| "Dokumani okumak istiyorum" | Tam dokumani goster, onay bekle |
| "Durdur" | Pipeline'i durdur |

## Onemli Notlar

- Dokuman, gercek kod tabani verilerine dayanir (codebase-retrieval ile)
- Mevcut dosyalar, API'ler, modeller analiz edilir
- Risk degerlendirmesi ve bagimlilik analizi otomatik yapilir
- Kullanici her degisiklik yapabilir, pipeline adapte olur
