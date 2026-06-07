---
sidebar_position: 8
title: Rescore Modu
---

# Rescore Modu

## Rescore Modu Nedir?

Rescore modu, daha önce çalıştırılmış bir DQG review'unun **sadece skorlama aşamalarını** yeniden çalıştıran optimize edilmiş bir moddur. Tam pipeline'ı tekrar çalıştırmadan, düzeltilmiş bir dökümanın kalite skorunu hızlıca ölçmenizi sağlar.

### Neden İhtiyaç Var?

Tipik bir DQG workflow'u şu şekilde ilerler:

1. Tam pipeline çalışır (critic → cross-ref → validate → score → meta_judge)
2. Sonuç: skor 6.5/10 (geçmez)
3. Döküman, tespit edilen sorunlara göre düzeltilir
4. **Sorun:** Düzeltme sonrası tekrar tam pipeline çalıştırmak ~10 dakika sürer

Rescore modu, adım 4'te tam pipeline yerine sadece `score` ve `meta_judge` stage'lerini çalıştırarak bu süreyi **~2 dakikaya** indirir.

### Tam Pipeline vs Rescore

| Özellik | Tam Pipeline | Rescore |
|---------|-------------|---------|
| Çalışan Stage'ler | 14-15 aşama | 2-3 aşama |
| Süre | ~10 dakika | ~2 dakika |
| LLM Çağrısı | ~30+ | ~3-5 |
| Token Kullanımı | Yüksek | Düşük |
| Yeni Sorun Tespiti | Evet | Hayır |
| Skor Güncelleme | Evet | Evet |
| Meta-Judge | Evet | Evet (koşullu) |

---

## Nasıl Çalışır

Rescore modu şu adımları izler:

### 1. Önceki Çalışmanın Verilerini Okur

`run_rescore` metodu, önceki review'un `output_dir` dizininden şu dosyaları okur:

- `original.md` — Orijinal döküman
- `revised.md` — Önceki düzeltilmiş döküman
- `issues.json` — Tespit edilen sorunlar
- `validations.json` — Doğrulama sonuçları
- `metadata.json` — Doküman tipi ve meta bilgiler

### 2. Düzeltilmiş Dökümanı Alır

Eğer `revised_file_path` parametresi verilmişse, bu dosyayı okur. Verilmemişse, önceki çalışmanın `revised.md` dosyasını kullanır.

### 3. Sadece Score + Meta Judge Çalıştırır

Critic, cross-reference, validate, revise gibi stage'leri **tamamen atlar**. Doğrudan:

1. **Score Stage** — Düzeltilmiş dökümanı, mevcut sorunlar ve doğrulamalarla birlikte skorlar
2. **Meta Judge** (koşullu) — Skor güveni %85'in altındaysa veya blocking reason varsa çalışır

### 4. Yeni Rapor Üretir

Yeni bir `run_id` ile yeni bir output dizini oluşturulur:

```
outputs/runs/{new_run_id}/
├── original.md
├── revised.md
├── issues.json
├── validations.json
├── scorecard.json
├── meta_judge.json
├── report.md
├── report.html
├── token_report.json
└── metadata.json
```

`metadata.json`'da `execution_status` alanı `"rescore_completed"` olarak işaretlenir.

---

## Kullanım Akışı

### Tipik Rescore Döngüsü

```
┌─────────────────┐
│  Tam Pipeline    │  ← İlk çalıştırma
│  (Full Run)      │
│  Süre: ~10 dk    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Sonuç: 6.5/10  │  ← Score < 8.0
│  15 sorun bulundu│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Dökümanı       │  ← Manuel düzeltme
│  Düzelt         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Rescore        │  ← Hızlı yeniden skorlama
│  Süre: ~2 dk    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Sonuç: 8.2/10  │  ← Score ≥ 8.0 → GEÇTİ
└─────────────────┘
```

---

## CLI Kullanımı

### Temel Kullanım

```powershell
# Önceki review'un revised.md dosyasını kullanarak rescore
python scripts/dqg_run.py rescore abc123def456
```

### Düzeltilmiş Dosya ile

```powershell
# Kendi düzeltilmiş dosyanızı belirtin
python scripts/dqg_run.py rescore abc123def456 --revised C:\path\to\revised-doc.md
```

### Tam Örnek Akış

```powershell
# 1. İlk review'ı başlat
python scripts/dqg_run.py launch doc.md --project C:\my-project

# Çıktı: REVIEW_STARTED review_id=abc123def456

# 2. Sonuçları bekle
python scripts/dqg_run.py poll abc123def456

# Çıktı: SCORE: 6.5/10 | FAIL | Action: rescore

# 3. Dökümanı düzelt (harici editörde)
# ... dosyayı kaydet ...

# 4. Rescore
python scripts/dqg_run.py rescore abc123def456 --revised C:\path\to\fixed-doc.md

# Çıktı: RESCORE_STARTED review_id=xyz789ghi012

# 5. Rescore sonuçlarını bekle
python scripts/dqg_run.py poll xyz789ghi012

# Çıktı: SCORE: 8.2/10 | PASS | Action: approve
```

### Komut Parametreleri

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `review_id` | Evet | Önceki review'un ID'si |
| `--revised` | Hayır | Düzeltilmiş döküman yolu. Belirtilmezse önceki `revised.md` kullanılır |

---

## API Endpoint

### POST /api/review/rescore

**Request body:**

```json
{
  "previous_review_id": "abc123def456",
  "revised_file_path": "C:\\path\\to\\revised-doc.md"
}
```

| Alan | Zorunlu | Açıklama |
|------|---------|----------|
| `previous_review_id` | Evet | Önceki review'un ID'si |
| `revised_file_path` | Hayır | Düzeltilmiş dökümanın dosya yolu |

**Response:**

```json
{
  "review_id": "xyz789ghi012",
  "status": "queued",
  "previous_review_id": "abc123def456"
}
```

Rescore arka planda bir thread'de çalışır. Durumu takip etmek için:

```
GET /api/review/status/xyz789ghi012
```

---

## Performans Karşılaştırması

### Zaman Analizi (Ortalama)

| Stage | Tam Pipeline | Rescore |
|-------|-------------|---------|
| Ingest | 0.5 sn | Atlanır |
| Complexity Router | 5 sn | Atlanır |
| Domain Context | 30 sn | Atlanır |
| Cross Reference | 33 sn | Atlanır |
| Deep Analysis | 198 sn | Atlanır |
| Critic A Multi | 42 sn | Atlanır |
| Critic B Multi | 39 sn | Atlanır |
| Critic A Judge | 31 sn | Atlanır |
| Critic B Judge | 31 sn | Atlanır |
| Dedupe | 1 sn | Atlanır |
| Validate | 39 sn | Atlanır |
| Revise | 19 sn | Atlanır |
| **Score** | **31 sn** | **31 sn** |
| **Meta Judge** | **209 sn** | **209 sn (koşullu)** |
| Fact Check | 87 sn | Atlanır |
| Report | 2 sn | 2 sn |
| **Toplam** | **~600 sn** | **~42-250 sn** |

Meta Judge, skor güveni %85 veya üzeri olduğunda ve blocking reason olmadığında otomatik olarak atlanır. Bu durumda rescore süresi ~33 saniyeye düşer.

### Token Kullanımı

| Metrik | Tam Pipeline | Rescore |
|--------|-------------|---------|
| Toplam Token | ~150K-300K | ~20K-50K |
| LLM Çağrısı | ~30+ | ~3-5 |
| Tahmini Maliyet | Yüksek | %80 daha düşük |

---

## Ne Zaman Rescore, Ne Zaman Full Run

### Karar Ağacı

```
Döküman değişti mi?
├── Hayır → Rescore gerekmez (aynı skor)
└── Evet → Ne değişti?
    ├── Sadece metin düzeltmeleri (typo, wording)
    │   └── → RESCORE
    │
    ├── Sorunlar giderildi (issue fix)
    │   └── → RESCORE
    │
    ├── Yeni bölüm eklendi
    │   ├── Küçük ekleme → RESCORE
    │   └── Büyük ekleme → FULL RUN
    │
    ├── Teknik içerik değişti (API, mimari)
    │   ├── Cross-ref etkisi olmayabilir → RESCORE
    │   └── Kod tabanı uyumluluğu değişti → FULL RUN
    │
    └── Tamamen yeniden yazıldı
        └── → FULL RUN
```

### Rescore Kullanın

- Score 8.0 altında, sorunlar düzeltildi
- Sadece metin/wording değişiklikleri
- Typo ve format düzeltmeleri sonrası
- Hızlı doğrulama gerektiğinde

### Full Run Kullanın

- Döküman köklü değişiklik geçirdi
- Yeni cross-reference gerektiren bölümler eklendi
- İlk çalıştırmada cross-reference bulunamadı (proje yolu eksikti)
- Farklı bir doküman tipiyle test ediyorsunuz
- Tamamen yeni bir döküman

### Pratik Kural

> **İlk run her zaman full pipeline olmalıdır.** Rescore, sadece mevcut sorunları giderdikten sonra skor doğrulaması için kullanılmalıdır. Arka arkaya 3'ten fazla rescore yapıyorsanız, dökümanı kökten düzeltip full run yapmayı düşünün.
