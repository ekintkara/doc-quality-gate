---
sidebar_position: 8
title: 'Faz 6-7: Implementasyon ve Review'
---

# Faz 6: IMPLEMENT

TODO listesindeki maddeleri faz faz uygular.

## Adimlar

1. Onaylanan TODO listesi okunur
2. Her TODO icin `todowrite` ile takip kaydi olusturulur
3. Fazlar sirayla islenir:
   - Kullaniciya hangi fazin baslatildigi bildirilir
   - Her TODO uygulanir → acceptance criteria dogrulanir → tamamlandi isaretlenir
   - Her faz sonrasi lint/typecheck calistirilir
4. **Kod asla commit edilmez**

## Faz Isleyisi

```
Faz 1 baslatiliyor...
  [1.1] ✓ Backend API endpoint olusturuldu
  [1.2] ✓ S3 upload servisi eklendi
  [1.3] ✓ Model guncellendi
  Lint ✓ | Typecheck ✓

Faz 2 baslatiliyor...
  [2.1] ✓ Profil sayfasi guncellendi
  [2.2] ✓ Avatar yukleme komponenti eklendi
  Lint ✓ | Typecheck ✓
```

## Kullaniciya Sunulan Format

```
✅ IMPLEMENTASYON TAMAMLANDI

Yapilanlar:
- Faz 1: Backend API endpoint + S3 entegrasyonu
- Faz 2: Frontend UI komponentleri

Degisen dosyalar: src/api/users.ts, src/services/upload.ts,
                  src/pages/Profile.tsx, src/components/AvatarUpload.tsx

Lint/Typecheck: GECTI

Yantla: "Devam" → implementation review'a gecerim
         "Sunu duzelt: ..." → duzeltme yaparim
```

---

# Faz 7: REVIEW_IMPL

3 paralel agent ile yazilan kodu review eder + hakem (judge) ile sentezler.

## 3 Agent Review

| Agent | Perspektif | Inceler |
|-------|------------|---------|
| Agent 1 | **Compliance** | Kod dokumandaki her seyi uyguluyor mu? |
| Agent 2 | **Quality** | Bug, guvenlik acigi, performans sorunu var mi? |
| Agent 3 | **Pattern** | Yeni kod mevcut proje pattern'lerine uygun mu? |

Her 3 agent ayni anda calisir. Sonuclar judge'a sunulur.

## Judge (Hakem)

1. 3 agent'in bulgularini sentezler
2. Oncelik sirasina gore duzeltme onerileri sunar
3. Compliance skoru verir (kac gereksinim karsilandi)

## Kullaniciya Sunulan Format

```
🔍 IMPLEMENTASYON REVIEW

Compliance: 8/10 gereksinim karsilandi
Quality: 2 dusuk, 0 kritik sorun
Pattern: 1 uyumsuzluk

Judge ozeti:
- Avatar yukleme icin dosya boyut limiti eksik (guvenlik)
- Error handling mevcut pattern ile uyumsuz
- API response formati tutarsiz

Yantla: "Duzeltmeleri uygula" → judge'in onerdiklerini yaparim
         "Onayliyorum, devam" → test planina gecerim
         "Sunu duzelt: ..." → sadece onu yaparim
```

## Onemli Notlar

- Kullanici "Duzeltmeleri uygula" derse, judge'in onerdigi tum duzeltmeler uygulanir
- Duzeltmeler sonrasi tekrar lint/typecheck calistirilir
- Kullanici sadece belirli bir duzeltme de isteyebilir
- Review sonrasinda kod hala commit edilmemistir — push icin explicit talep gerekir
