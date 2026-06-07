---
sidebar_position: 9
title: 'Faz 8-9: Test ve Tamamlama'
---

# Faz 8: TEST_PLAN

Implementasyon degisikliklerine dayali test dokumantasyonu olusturur.

## Adimlar

1. TODO listesi + implementation degisiklikleri okunur
2. Test Planner agent gorevlendirilir
3. Test plani `.pipeline/{TASK_KEY}-test-plan.md` olarak kaydedilir

## Test Plani Icerigi

Test plani su kategorileri icerir:

| Kategori | Tur | Aciklama |
|----------|-----|----------|
| Unit testleri | Otomatik | Her fonksiyon/metot icin |
| Integration testleri | Otomatik | API endpoint'ler, servis baglantakları |
| E2E testleri | Otomatik (Playwright) | Kullanici senaryolari |
| Happy path | Manuel | Ana akis senaryoları |
| Edge case | Manuel | Sinir durumlar |
| Error scenario | Manuel | Hata durumlari |

## Kullaniciya Sunulan Format

```
🧪 TEST PLANI HAZIR

Otomatik: 8 unit, 3 integration, 2 Playwright
Manuel: 4 happy path, 3 edge, 2 error

Yantla: "Onayliyorum" → testleri calistiririm
         "Sunu degistir: ..." → uygularim
         "Testleri atla" → kaydeder, devam
```

---

# Faz 9: TEST

Test planini calistirir ve sonuclari raporlar.

## Adimlar

1. Unit ve integration testleri bash uzerinden calistirilir
2. Playwright MCP testleri (varsa) calistirilir
3. Sonuclar `.pipeline/{TASK_KEY}-test-results.md` olarak kaydedilir

## Test Sonuclari Format

```
🧪 TEST SONUCLARI

Otomatik:
  Unit: 8/8 gecti
  Integration: 3/3 gecti
  E2E: 2/2 gecti

Manuel test adimlari:
1. Profil sayfasini ac → Avatar yukleme butonu gorunmeli
2. Gecersiz dosya formati yukle → Hata mesaji gorunmeli
3. 10MB ustu dosya yukle → Boyut limiti uyarisi gorunmeli
4. Avatar yukle → Profil resmi guncellenmeli

Yantla: "Manuel testler tamamlandi" → pipeline tamamlanir
         "Su test basarisiz, duzelt" → duzeltirim
         "Devam" → pipeline tamamlanir
```

---

# Faz 10: DONE

Pipeline tamamlandiginda ozet sunulur.

```
✅ PIPELINE TAMAMLANDI: PDB-12345

Ciktilar: .pipeline/ dizininde
- Implementasyon dokumani: PDB-12345-impl-doc-reviewed.md
- TODO listesi: PDB-12345-todo.md
- Test plani: PDB-12345-test-plan.md
- Test sonuclari: PDB-12345-test-results.md

NOT: Kod pushlanmadi. Pushlamak istersen soyle.
```

## Onemli

- **Kod asla otomatik pushlanmaz** — explicit talep gerekir
- Pipeline ciktilari `.pipeline/` dizininde saklanir
- Ileride referans olarak kullanilabilir
- "continue pipeline" ile pipeline tekrar baslatilabilir
