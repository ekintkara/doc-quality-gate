---
sidebar_position: 7
title: Pipeline Simulatoru
---

# Pipeline Simülatörü

## Simülatör Nedir?

Pipeline Simülatörü, DQG review pipeline'ının çalışma süresini ve kalite güvenilirliğini tahmin etmenizi sağlayan interaktif bir araçtır. Farklı pipeline profillerinin ve optimizasyon stratejilerinin toplam latency, stage sayısı ve kalite üzerindeki etkisini görsel olarak karşılaştırmanıza olanak tanır.

Gerçek bir review çalıştırmadan önce, hangi profilin ihtiyacınıza uygun olduğunu görmek için simülatörü kullanabilirsiniz. Bu, özellikle "fast track mi yoksa deep analiz mi seçmeliyim?" kararını verirken zaman ve maliyet tasarrufu sağlar.

Simülatör verileri `config/pipeline_profiles.yaml` dosyasındaki gerçek stage sürelerinden (saniye cinsinden) hesaplanır. Bu süreler, geçmiş çalışmalardan elde edilen gerçek ölçümlere dayanır.

---

## Web UI

Simülatöre `http://localhost:8080/simulator` adresinden erişebilirsiniz. Sayfa üç ana bölümden oluşur:

### Strateji Kontrolleri

Sol panelde iki mod bulunur:

- **Hazır Profil**: Önceden tanımlanmış profiller arasından seçim yapın
- **Özel Konfigürasyon**: Optimizasyon stratejilerini tek tek açıp kapatabilirsiniz

Özel konfigürasyon modunda şu toggle'lar mevcuttur:

| Toggle | Açıklama |
|--------|----------|
| **Early Exit** | Kritik hata tespit edildiğinde pipeline'ı erken durdurur |
| **Fan-out Paralelizasyon** | Domain context, cross-reference ve iki critic stage'ini aynı anda çalıştırır (4 paralel thread) |
| **Budama (Pruning)** | Meta-Judge ve Fact-Check gibi azalan verimlilikteki stage'leri kaldırır |
| **Proje Cross-reference** | Proje yolu verildiğinde domain analizi yapılıp yapılmayacağını belirler |

### Metrik Kartları

Sağ üstte dört metrik kartı yer alır:

| Metrik | Açıklama |
|--------|----------|
| **Tahmini Süre** | Pipeline'ın toplam çalışma süresi tahmini |
| **Tasarruf** | Mevcut tam pipeline'a kıyasla zaman tasarrufu yüzdesi |
| **Kalite Güveni** | Pipeline'ın tespit kalitesi güvenilirlik oranı (0.0 - 1.0) |
| **Aşama Sayısı** | Çalıştırılacak toplam stage sayısı |

Kalite güveni renk kodları:
- **Yeşil** (≥%95): Yüksek güven
- **Sarı** (≥%85): Orta güven
- **Kırmızı** (`<85%`): Düşük güven

### Gantt Chart

Sayfanın ortasında yer alan Gantt chart, her stage'in başlangıç zamanını, süresini ve paralel çalışma durumunu görsel olarak gösterir. Paralel çalışan stage'ler aynı satırda yan yana görünür. Atlanan stage'ler soluk renkte "atlandı" etiketiyle gösterilir.

---

## API Endpoints

Simülatör, web UI dışında doğrudan API olarak da kullanılabilir.

### GET /api/simulator/stages

Tüm mevcut pipeline stage'lerini listeler.

```json
{
  "stages": [
    {"id": "ingest", "name": "Ingest", "category": "setup", "llm": false},
    {"id": "complexity_router", "name": "Complexity Router", "category": "setup", "llm": true},
    {"id": "domain_context", "name": "Domain Context", "category": "analysis", "llm": true},
    {"id": "cross_reference", "name": "Cross Reference", "category": "analysis", "llm": true},
    {"id": "deep_analysis", "name": "Deep Analysis", "category": "analysis", "llm": true},
    {"id": "critic_a_multi", "name": "Critic A (multi)", "category": "critic", "llm": true},
    {"id": "critic_b_multi", "name": "Critic B (multi)", "category": "critic", "llm": true},
    {"id": "critic_a_judge", "name": "Critic A Judge", "category": "critic", "llm": true},
    {"id": "critic_b_judge", "name": "Critic B Judge", "category": "critic", "llm": true},
    {"id": "dedupe", "name": "Deduplication", "category": "merge", "llm": false},
    {"id": "validate", "name": "Validation", "category": "review", "llm": true},
    {"id": "revise", "name": "Revision", "category": "review", "llm": true},
    {"id": "score", "name": "Scoring", "category": "evaluation", "llm": true},
    {"id": "meta_judge", "name": "Meta Judge", "category": "evaluation", "llm": true},
    {"id": "fact_check", "name": "Fact Check", "category": "evaluation", "llm": true},
    {"id": "report", "name": "Report", "category": "output", "llm": false}
  ]
}
```

### GET /api/simulator/profiles

`pipeline_profiles.yaml` dosyasından tanımlı tüm profilleri döndürür.

```json
{
  "profiles": {
    "fast_track": { "description": "Minor changes - skip heavy analysis", ... },
    "standard": { "description": "Standard review - balanced", ... },
    "deep": { "description": "Full 14-stage pipeline", ... }
  }
}
```

### POST /api/simulator/calculate

Verilen konfigürasyona göre pipeline simülasyonu çalıştırır.

**Request body:**

```json
{
  "profile": "standard",
  "early_exit": true,
  "fan_out": true,
  "pruning": true,
  "has_project": true
}
```

| Parametre | Tip | Varsayılan | Açıklama |
|-----------|-----|-----------|----------|
| `profile` | string | `"standard"` | Profil adı: `"current"`, `"fast_track"`, `"standard"`, `"deep"` veya `"custom"` |
| `early_exit` | bool | `true` | Early exit stratejisi (sadece custom modda) |
| `fan_out` | bool | `true` | Fan-out paralelizasyon (sadece custom modda) |
| `pruning` | bool | `true` | Stage budama (sadece custom modda) |
| `has_project` | bool | `true` | Proje cross-reference var mı |

**Response:**

```json
{
  "profile": "standard",
  "total_latency_seconds": 175.5,
  "quality_confidence": 0.92,
  "stages_count": 12,
  "active_stages": ["ingest", "domain_context", ...],
  "timeline": [
    {"stage": "ingest", "start": 0, "duration": 0.5, "status": "active"},
    {"stage": "domain_context", "start": 0.5, "duration": 30, "status": "active"},
    {"stage": "cross_reference", "start": 0.5, "duration": 33, "status": "active"},
    {"stage": "critic_a_multi", "start": 0.5, "duration": 42, "status": "active"},
    {"stage": "critic_b_multi", "start": 0.5, "duration": 39, "status": "active"}
  ],
  "savings_vs_current": 70.8,
  "early_exit": true,
  "early_exit_stages": ["cross_reference"]
}
```

Timeline'daki paralel stage'ler aynı `start` değerine sahiptir. Toplam latency, en uzun süren paralel stage'e göre hesaplanır.

### GET /api/simulator/comparison

Tüm profillerin yan yana karşılaştırmasını döndürür. Mevcut pipeline, fast_track, standard, deep ve custom (tüm optimizasyonlar açık) sonuçlarını içerir.

---

## Stage Duration Verileri

Stage süreleri `config/pipeline_profiles.yaml` dosyasındaki `stage_durations` bölümünden alınır:

| Stage | Süre (sn) | LLM Gerekli | Açıklama |
|-------|-----------|-------------|----------|
| ingest | 0.5 | Hayır | Dosya okuma ve parsing |
| complexity_router | 5 | Evet | Döküman karmaşıklık analizi |
| domain_context | 30 | Evet | Proje domain context çıkarma |
| cross_reference | 33 | Evet | Kod tabanı karşılaştırma |
| deep_analysis | 198 | Evet | Derin domain analiz |
| critic_a_multi | 42 | Evet | Critic A çoklu çalıştırma |
| critic_b_multi | 39 | Evet | Critic B çoklu çalıştırma |
| critic_a_judge | 31 | Evet | Critic A sonuçlarını değerlendirme |
| critic_b_judge | 31 | Evet | Critic B sonuçlarını değerlendirme |
| dedupe | 1 | Hayır | Yinelenen sorunları birleştirme |
| validate | 39 | Evet | Sorunları doğrulama |
| revise | 19 | Evet | Döküman düzeltme |
| score | 31 | Evet | Promptfoo ile skorlama |
| meta_judge | 209 | Evet | Üst değerlendirme |
| fact_check | 87 | Evet | Gerçeklik kontrolü |
| report | 2 | Hayır | Rapor üretme |

**Toplam (tekrarlı):** ~718 saniye (~12 dakika)
**Paralel çalıştırma ile (deep):** ~600 saniye (~10 dakika)

---

## Profile Karşılaştırma

### Mevcut Pipeline (14 aşama)

Tüm stage'ler fan-out ile paralel çalışır. Domain context ve cross-reference aynı anda, critic'ler aynı anda çalışır. Toplam ~718 saniye.

| Metrik | Değer |
|--------|-------|
| Tahmini Süre | ~10-12 dk |
| Kalite Güveni | %100 |
| Aşama Sayısı | 15 |
| Tasarruf | - |

### Fast Track

Minor değişiklikler için tasarlanmıştır. Heavy analysis stage'leri atlanır, sadece validate + revise + score çalışır.

| Metrik | Değer |
|--------|-------|
| Tahmini Süre | ~90 sn (~1.5 dk) |
| Kalite Güveni | %70 |
| Aşama Sayısı | 5 |
| Tasarruf | ~%87 |

**Kullanım:** Küçük metin düzeltmeleri, typo fix'leri, küçük format değişiklikleri.

### Standard

Dengeli profil. Deep analysis, meta_judge ve fact_check atlanır. Early exit aktif.

| Metrik | Değer |
|--------|-------|
| Tahmini Süre | ~175 sn (~3 dk) |
| Kalite Güveni | %92 |
| Aşama Sayısı | 12 |
| Tasarruf | ~%70 |

**Kullanım:** Orta ölçekli feature'lar, standart implementasyon planları.

### Deep

Tam 14-aşama pipeline. Tüm analiz stage'leri çalışır. En yüksek kalite güveni.

| Metrik | Değer |
|--------|-------|
| Tahmini Süre | ~600 sn (~10 dk) |
| Kalite Güveni | %98 |
| Aşama Sayısı | 15 |
| Tasarruf | ~%0 (referans) |

**Kullanım:** Kritik mimari değişiklikler, büyük feature'lar, production deployment planları.

---

## Kullanım Senaryoları

### Senaryo 1: "Hangi profile seçmeliyim?"

```
Soru: "Bu döküman orta ölçekli bir feature için. Ne önerirsiniz?"

Cevap: Standard profil.
- %92 kalite güveni yeterli
- ~3 dakikada tamamlanır
- Deep profile göre %70 daha hızlı
```

### Senaryo 2: "Maliyet analizi"

```
Soru: "Deep profil 10 dakika sürüyor. Standard ile aradaki fark ne?"

Simülatör cevabı:
- Deep: 10 dk, %98 kalite, 15 stage
- Standard: 3 dk, %92 kalite, 12 stage
- Tasarruf: 7 dakika, %6 kalite kaybı
- Karar: %92 yeterliyse standard kullanın
```

### Senaryo 3: "Acil review lazım"

```
Soru: "5 dakikada review yapabilir miyim?"

Simülatör cevabı:
- Fast Track: 1.5 dk, %70 kalite
- Standard: 3 dk, %92 kalite
- Her ikisi de 5 dakikanın altında
- Öneri: %92 kalite için Standard
```

### Senaryo 4: "Kritik mimari değişiklik"

```
Soru: "Production'da bir migration yapıyoruz. Hangi profil?"

Cevap: Deep profil.
- %98 kalite güveni ile tüm kontroller
- Cross-reference + deep analysis + fact check
- 10 dakika beklemeye değer
```

### Maliyet-Süre-Kalite Dengesi

| Profil | Süre | Kalite | Maliyet | Risk |
|--------|------|--------|---------|------|
| Fast Track | 1.5 dk | %70 | Düşük | Yüksek |
| Standard | 3 dk | %92 | Orta | Düşük |
| Deep | 10 dk | %98 | Yüksek | Çok Düşük |

**Altın kural:** Ne kadar kritikse, o kadar derin analiz.
