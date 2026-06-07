---
sidebar_position: 6
title: Pipeline Optimizasyonu
---

# Pipeline Optimizasyonu

## 1. Pipeline Optimizasyonuna Genel Bakış

Doc Quality Gate (DQG), doküman kalite inceleme pipeline'ı olarak tasarlanmıştır. Varsayılan (deep) pipeline, tüm 14+ aşamayı sıralı-yarı-paralel çalıştırır ve bu da tek bir doküman incelemesinin **18-34 dakika** sürmesine neden olur. Bu süre, geliştiricilerin geri bildirim döngüsünü yavaşlatır ve iteratif çalışmayı zorlaştırır.

### Temel Hedefler

| Metrik | Önceki | Hedef | Gerçekleşen |
|--------|--------|-------|-------------|
| Deep pipeline | 18-34 dk | 10 dk | ~10 dk |
| Standard pipeline | — | 3-4 dk | ~3 dk |
| Early exit | — | 2-3 dk | ~2.5 dk |
| Fast track | — | 1.5 dk | ~1.5 dk |
| Quality confidence | %98 | %95+ | %92-%98 (profile bağlı) |

### Optimizasyon Stratejileri

Pipeline optimizasyonu dört ana stratejiye dayanır:

1. **Pipeline Profilleri** — Doküman karmaşıklığına göre stage listesi ve atlama kuralları
2. **Complexity Router** — LLM tabanlı otomatik profil seçimi
3. **Aggressive Fan-out** — Bağımsız aşamaların paralel çalıştırılması
4. **Early Exit** — Kritik hatalarda erken sonlandırma
5. **Conditional Stages** — meta_judge ve fact_check gibi aşamaların koşullu çalıştırılması

---

## 2. Pipeline Profilleri

Pipeline profilleri, `config/pipeline_profiles.yaml` dosyasında tanımlanır. Her profil, hangi aşamaların çalışacağını, hangilerinin atlanacağını, early exit kurallarını ve tahmini süreyi belirler.

### 2.1 Fast Track Profili

**Açıklama:** Küçük değişiklikler — ağır analiz aşamaları atlanır.

**Kullanım Senaryoları:**
- Typo düzeltmeleri
- Konfigürasyon değişiklikleri
- Basit UI güncellemeleri
- Küçük metin düzeltmeleri
- Mimari etkisi olmayan değişiklikler

| Özellik | Değer |
|---------|-------|
| Tahmini süre | ~90 saniye (1.5 dk) |
| Quality confidence | %70 |
| Early exit | Hayır |
| Aktif stage sayısı | 5 |

**Çalışan aşamalar:**

```
ingest → validate → revise → score → report
```

**Atlanan aşamalar:**

- `domain_context` — Proje domain analizi
- `cross_reference` — Kod tabanı çapraz referans
- `deep_analysis` — Derin mimari analiz
- `critic_a_multi` — Critic A çoklu çalıştırma
- `critic_b_multi` — Critic B çoklu çalıştırma
- `critic_a_judge` — Critic A değerlendirmesi
- `critic_b_judge` — Critic B değerlendirmesi
- `dedupe` — Tekilleştirme
- `meta_judge` — Meta hakem
- `fact_check` — Gerçek kontrolü

> **Not:** Fast track profili critic stage'lerini atladığı için yalnızca validate ve revise aşamalarında temel kalite kontrolü yapılır. Quality confidence %70 seviyesindedir.

### 2.2 Standard Profili

**Açıklama:** Dengeli standart inceleme — derin analiz ve ağır stage'ler atlanır.

**Kullanım Senaryoları:**
- Yeni özellik eklemeleri
- Orta ölçekli refactor'lar
- Yeni endpoint'ler
- Mimari değerlendirme gerektiren ama tam analiz gerektirmeyen değişiklikler

| Özellik | Değer |
|---------|-------|
| Tahmini süre | ~175 saniye (~3 dk) |
| Quality confidence | %92 |
| Early exit | Evet (cross_reference sonrası) |
| Aktif stage sayısı | 12 |

**Çalışan aşamalar:**

```
ingest → domain_context → cross_reference → critic_a_multi → critic_b_multi
       → critic_a_judge → critic_b_judge → dedupe → validate → revise
       → score → report
```

**Atlanan aşamalar:**

- `deep_analysis` — Derin mimari analiz
- `meta_judge` — Meta hakem (koşullu çalışabilir)
- `fact_check` — Gerçek kontrolü

**Early exit noktaları:**
- `cross_reference` — Kritik çapraz referans hatalarında erken çıkış

### 2.3 Deep Profili

**Açıklama:** Tam 14-aşamalı pipeline — tüm analiz ve değerlendirme stage'leri çalışır.

**Kullanım Senaryoları:**
- Mimari değişiklikler
- Veritabanı migration'ları
- Breaking changes
- Çoklu servis etkileşimi olan değişiklikler
- Kritik dokümanlar (SLA, güvenlik, uyumluluk)

| Özellik | Değer |
|---------|-------|
| Tahmini süre | ~600 saniye (~10 dk) |
| Quality confidence | %98 |
| Early exit | Evet (cross_reference ve deep_analysis sonrası) |
| Aktif stage sayısı | 15 |

**Çalışan aşamalar:**

```
ingest → domain_context → cross_reference → deep_analysis → critic_a_multi
       → critic_b_multi → critic_a_judge → critic_b_judge → dedupe → validate
       → revise → score → meta_judge → fact_check → report
```

**Atlanan aşamalar:** Yok (boş liste)

**Early exit noktaları:**
- `cross_reference` — Kritik çapraz referans hatalarında erken çıkış
- `deep_analysis` — Kritik mimari ihlallerinde erken çıkış (en az 2 violation gerekli)

### 2.4 Profil Karşılaştırma Tablosu

| Özellik | Fast Track | Standard | Deep |
|---------|-----------|----------|------|
| **Tahmini süre** | ~90 sn (1.5 dk) | ~175 sn (~3 dk) | ~600 sn (~10 dk) |
| **Quality confidence** | %70 | %92 | %98 |
| **Aktif stage** | 5 | 12 | 15 |
| **Atlanan stage** | 10 | 3 | 0 |
| **Early exit** | Hayır | Evet (xref) | Evet (xref + deep) |
| **domain_context** | ❌ | ✅ | ✅ |
| **cross_reference** | ❌ | ✅ | ✅ |
| **deep_analysis** | ❌ | ❌ | ✅ |
| **critic_a/b_multi** | ❌ | ✅ | ✅ |
| **critic_a/b_judge** | ❌ | ✅ | ✅ |
| **dedupe** | ❌ | ✅ | ✅ |
| **meta_judge** | ❌ | ❌ | ✅ |
| **fact_check** | ❌ | ❌ | ✅ |
| **validate** | ✅ | ✅ | ✅ |
| **revise** | ✅ | ✅ | ✅ |
| **score** | ✅ | ✅ | ✅ |
| **report** | ✅ | ✅ | ✅ |

### 2.5 Varsayılan Profil

`pipeline_profiles.yaml` dosyasında `default_profile: standard` olarak tanımlanmıştır. Profil belirtilmediğinde bu profil kullanılır.

CLI üzerinden `--profile` bayrağı ile profil seçilebilir:

```bash
# Standard profil (varsayılan)
python -m app.cli review document.md --project ./myproject

# Deep profil
python -m app.cli review document.md --project ./myproject --profile deep

# Fast track profil
python -m app.cli review document.md --project ./myproject --profile fast_track

# Otomatik profil (complexity router ile)
python -m app.cli review document.md --project ./myproject --profile auto
```

---

## 3. Complexity Router

Complexity Router, dokümanın karmaşıklığını değerlendirerek otomatik olarak uygun pipeline profilini seçen bir aşamadır. `profile=auto` belirtildiğinde aktifleşir.

### 3.1 Nasıl Çalışır

1. **Girdi:** Doküman içeriği (ilk 8000 karakter) ve doküman türü
2. **LLM Çağrısı:** Critic A modeline tek bir istek gönderilir
3. **Çıktı:** 1-10 arası karmaşıklık skoru, seviye (minor/standard/major) ve gerekçe
4. **Profil Eşlemesi:** Skor ve seviyeye göre pipeline profili belirlenir

**LLM prompt yapısı** (`complexity_router.py`):

```
Analyze this document and assess its complexity for a document quality review pipeline.

Rate complexity from 1-10:
- 1-3 (Minor): Small changes, typo fixes, config tweaks, simple UI updates. No architectural impact.
- 4-6 (Standard): Feature additions, moderate refactors, new endpoints. Some architectural consideration needed.
- 7-10 (Major): Architecture changes, migrations, breaking changes, multi-service impacts. Full deep analysis required.
```

**Model parametreleri:**

| Parametre | Değer |
|-----------|-------|
| Model | Critic A alias'ı ile çözülen model |
| Temperature | 0.1 (tutarlı sonuçlar için düşük) |
| Max tokens | 256 |
| Stage adı | `complexity_router` |
| Tahmini süre | ~5 saniye |

### 3.2 Eşik Değerleri

Karmaşıklık skorları, `pipeline_profiles.yaml` dosyasındaki `complexity_router.thresholds` değerlerine göre sınıflandırılır:

| Skor Aralığı | Seviye | Profil |
|---------------|--------|--------|
| 1-3 | `minor` | `fast_track` |
| 4-6 | `standard` | `standard` |
| 7-10 | `major` | `deep` |

**Yapılandırma:**

```yaml
complexity_router:
  thresholds:
    minor_change: 3
    standard: 6
    major_change: 10
  profile_mapping:
    minor: fast_track
    standard: standard
    major: deep
```

### 3.3 Karar Mantığı

Router'ın karar verme akışı (`complexity_router.py:81-98`):

```python
if level_str == "minor" or score <= thresholds.get("minor_change", 3):
    level = ComplexityLevel.MINOR        # → fast_track
elif level_str == "major" or score >= thresholds.get("major_change", 7):
    level = ComplexityLevel.MAJOR         # → deep
else:
    level = ComplexityLevel.STANDARD      # → standard
```

LLM'den gelen `level` alanı ile `score` değeri birlikte değerlendirilir. LLM çıktısı `minor` olarak gelirse, skordan bağımsız olarak fast_track profili seçilir. Benzer şekilde `major` gelirse deep profil seçilir. Score eşik değerleri, LLM çıktısının tutarsız olduğu durumlarda yedek kontrol görevi görür.

### 3.4 Hata Durumu

LLM'den gelen yanıt parse edilemezse, sistem güvenli bir şekilde **standard** profiline geri döner:

```python
ComplexityResult(
    level=ComplexityLevel.STANDARD,
    score=5,
    reasoning=f"Fallback due to parse error: {e}",
    profile="standard",
    estimated_latency_seconds=240,
)
```

Bu, markdown kod bloğu içinde gelen JSON yanıtlarını da işleyebilir:

```python
if "```" in text:
    text = text.split("```")[1]
    if text.startswith("json"):
        text = text[4:]
```

### 3.5 Kullanım Zamanlaması

Complexity Router yalnızca `--profile auto` belirtildiğinde çalışır. Diğer profil seçeneklerinde (`fast_track`, `standard`, `deep`) router aşaması tamamen atlanır ve 5 saniyelik LLM çağrısı yapılmaz.

**Otomatik seçim akışı** (`orchestrator.py:205-215`):

```
ingest → complexity_router (sadece profile=auto ise) → [seçilen profilin aşamaları]
```

**Router çıktısı:** `complexity_router.json` dosyasına yazılır:

```json
{
  "level": "standard",
  "score": 5,
  "reasoning": "New API endpoint with moderate complexity, some database interaction",
  "profile": "standard",
  "estimated_latency_seconds": 175
}
```

---

## 4. Aggressive Fan-out

Aggressive Fan-out, birbirinden bağımsız pipeline aşamalarının aynı anda çalıştırılmasıdır. Bu, toplam pipeline süresini dramatik olarak azaltır.

### 4.1 Paralel Çalışan Gruplar

**Fan-out Group 1** (`fan_out_group_1`):

Aşağıdaki dört aşama eşzamanlı olarak çalıştırılır:

| Aşama | Tahmini Süre | Açıklama |
|-------|-------------|----------|
| `domain_context` | ~30 sn | Proje domain analizi ve doküman tarama |
| `cross_reference` | ~33 sn | Kod tabanı çapraz referans kontrolü |
| `critic_a_multi` | ~42 sn | Critic A çoklu çalıştırma (2 run) |
| `critic_b_multi` | ~39 sn | Critic B çoklu çalıştırma (2 run) |

**Max workers:** 4 (tüm görevler eşzamanlı çalışır)

**Paralel olmadan:** 30 + 33 + 42 + 39 = **144 saniye** (sıralı)

**Paralel ile:** max(30, 33, 42, 39) = **~42 saniye**

**Tasarruf:** ~102 saniye (%71 azalma)

**Critic Judges** (`critic_judges`):

| Aşama | Tahmini Süre | Açıklama |
|-------|-------------|----------|
| `critic_a_judge` | ~31 sn | Critic A sonuçlarının değerlendirilmesi |
| `critic_b_judge` | ~31 sn | Critic B sonuçlarının değerlendirilmesi |

**Max workers:** 2

### 4.2 ThreadPoolExecutor Yönetimi

Paralel çalıştırma, Python'un `concurrent.futures.ThreadPoolExecutor` sınıfı ile yönetilir.

**Fan-out Group 1 implementasyonu** (`orchestrator.py:326-329`):

```python
with ThreadPoolExecutor(max_workers=min(len(fan_out_tasks), fan_out_max)) as executor:
    futs = [executor.submit(fn) for _, fn in fan_out_tasks]
    for f in futs:
        f.result()
```

**Önemli noktalar:**

- `max_workers`, görev sayısı ile `fan_out_max` (4) değerinin minimumu olarak belirlenir. Proje path'i yoksa yalnızca 2 critic görevi çalışır ve `max_workers=2` olur.
- `f.result()` çağrısı, tüm görevlerin tamamlanmasını bekler. Herhangi bir görev hata fırlatırsa, hata burada yakalanır.
- Her görev, sonuçlarını closure değişkenlerine (liste elemanlarına) yazar. Bu, thread-safe bir sonuç paylaşım mekanizmasıdır.

**Critic judges paralelliği** (`orchestrator.py:548-552`):

```python
with ThreadPoolExecutor(max_workers=2) as executor:
    fut_ja = executor.submit(_run_critic_a_judge)
    fut_jb = executor.submit(_run_critic_b_judge)
    fut_ja.result()
    fut_jb.result()
```

### 4.3 Koşullu Fan-out

Fan-out yalnızca `has_project=True` olduğunda tüm 4 görevi çalıştırır. Proje path'i yoksa:

```python
elif not has_project:
    # Sadece critic_a ve critic_b paralel çalışır
    # domain_context ve cross_reference atlanır
```

Proje path'i olmadığında domain_context ve cross_reference anlamsızdır. Bu durumda yalnızca critic_a ve critic_b, `max_workers=2` ile paralel çalışır.

### 4.4 Performans Karşılaştırması

| Senaryo | Sıralı | Fan-out | Tasarruf |
|---------|--------|---------|----------|
| 4 stage (domain+xref+criticA+criticB) | 144 sn | 42 sn | %71 |
| 2 critic (proje yok) | 81 sn | 42 sn | %48 |
| 2 judge (criticA+criticB) | 62 sn | 31 sn | %50 |

### 4.5 Fan-out ve Early Exit Etkileşimi

Fan-out grupları tamamlandıktan sonra early exit kontrolü yapılır. Bu, paralel çalışan aşamalardan birinde kritik hata bulunması durumunda pipeline'ın erken sonlandırılmasını sağlar:

```
[domain_context + cross_reference + critic_a + critic_b] (paralel)
  ↓ tamamlanınca
  ↓ cross_reference sonuçları early exit kontrolünden geçer
  ↓ kritik hata varsa → EARLY EXIT
  ↓ kritik hata yoksa → devam
```

Bu tasarım, paralel çalışmanın avantajını korurken erken sonlandırma güvenliğini sağlar.

---

## 5. Early Exit

Early exit, pipeline'ın kritik hatalar tespit edildiğinde erken sonlandırılmasıdır. Kalan aşamalar çalıştırılmaz ve doküman "KALDI" olarak işaretlenir.

### 5.1 Ne Zaman Tetiklenir

Early exit iki noktada kontrol edilir:

**1. Cross-Reference sonrası** (`orchestrator.py:350-402`)

Cross-reference aşaması tamamlandığında, bulunan sorunlar `early_exit_rules` kurallarına göre değerlendirilir.

**2. Deep Analysis sonrası** (`orchestrator.py:432-485`)

Deep analysis aşaması tamamlandığında, domain ihlalleri kontrol edilir.

### 5.2 Kurallar Yapılandırması

Early exit kuralları `pipeline_profiles.yaml` dosyasında tanımlanır:

```yaml
early_exit_rules:
  cross_reference:
    fatal_severities:
      - critical
    min_fatal_count: 1
    abort_message: "Fatal cross-reference errors detected"
  deep_analysis:
    fatal_severities:
      - critical
    min_fatal_count: 2
    abort_message: "Critical architectural violations detected"
```

| Parametre | Açıklama |
|-----------|----------|
| `fatal_severities` | Hangi severity seviyelerinin fatal sayılacağı |
| `min_fatal_count` | Early exit için gereken minimum fatal hata sayısı |
| `abort_message` | Sonlandırma mesajı |

**Cross-reference kuralı:** En az 1 `critical` seviye sorun bulunduğunda early exit tetiklenir.

**Deep analysis kuralı:** En az 2 `critical` seviye ihlal bulunduğunda early exit tetiklenir. Deep analysis için daha yüksek eşik (2) kullanılması, tek bir mimari ihlalin false positive olabileceği durumlarda pipeline'ın gereksiz yere sonlandırılmasını önler.

### 5.3 Profil Bazlı Early Exit Davranışı

| Profil | Early Exit | Noktalar |
|--------|-----------|----------|
| `fast_track` | ❌ Kapalı | — |
| `standard` | ✅ Açık | cross_reference |
| `deep` | ✅ Açık | cross_reference, deep_analysis |

### 5.4 Early Exit Sonrası Ne Olur

Early exit tetiklendiğinde:

1. **Loglama:** `early_exit_triggered` log kaydı oluşturulur
2. **Broadcast:** `early_exit` stage'i "done" olarak yayınlanır
3. **Uyarı:** Warnings listesine `EARLY EXIT: mesaj (N fatal issues)` eklenir
4. **Dosya yazımı:** `early_exit.json` dosyasına sonlandırma detayları yazılır
5. **Token raporu:** `token_report.json` güncellenir
6. **Partial artifacts:** `RunArtifacts` oluşturulur:
   - `execution_status`: `"early_exit"`
   - `revised_content`: Orijinal doküman (revize yapılmadı)
   - `issues`: Bulunan cross-reference sorunları
   - `validations`: Boş liste
   - `scorecard`: `None` (skorlama yapılmadı)
   - `fact_check`: `None`
7. **Metadata:** `metadata.json` yazılır
8. **Pipeline sonlanır:** Fonksiyon early_artifacts döndürür

**`early_exit.json` örneği:**

```json
{
  "stage": "cross_reference",
  "fatal_count": 3,
  "message": "Fatal cross-reference errors detected"
}
```

**Metadata örneği (early exit):**

```json
{
  "execution_status": "early_exit",
  "duration_ms": 45000,
  "warnings": [
    "EARLY EXIT: Fatal cross-reference errors detected (3 fatal issues)"
  ]
}
```

### 5.5 Early Exit ve Token Kullanımı

Early exit, token kullanımını önemli ölçüde azaltır. Tam deep pipeline ~10 dakika ve binlerce token harcarken, early exit ile sonlandırılan bir çalışma ~2.5 dakika ve çok daha az token harcar:

```
Tam pipeline: ingest → [fan-out 4] → deep → [judge 2] → dedupe → validate → revise → score → meta_judge → fact_check → report
                                                                        ↑ ~10 dk, ~500K token

Early exit:   ingest → [fan-out 4] → EARLY EXIT
                                 ↑ ~2.5 dk, ~50K token
```

---

## 6. Conditional Stages

Bazı pipeline aşamaları, koşullar karşılandığında otomatik olarak atlanır. Bu, gereksiz LLM çağrılarını önler ve süreyi azaltır.

### 6.1 Meta Judge

Meta judge, skorlama aşamasının güvenilirliğini değerlendiren son kontrol mekanizmasıdır. Ancak yüksek güvenilirlik durumlarında çalıştırılması gereksizdir.

**Koşullu atlama kuralı** (`orchestrator.py:658-665`):

Meta judge şu koşulların **tümü** sağlandığında atlanır:

| Koşul | Açıklama |
|-------|----------|
| `scorecard.confidence_in_scoring >= 0.85` | Skorlama güveni yüksek |
| `scorecard.promptfoo_agreement in ("agree", None)` | Promptfoo ile anlaşma var |
| `not scorecard.blocking_reasons` | Engelleyici neden yok |

**Mantık:**

```python
skip_meta = (
    scorecard.confidence_in_scoring >= 0.85
    and scorecard.promptfoo_agreement in ("agree", None)
    and not scorecard.blocking_reasons
)
```

Üç koşul birlikte değerlendirilir. Skor yüksek güvenle verilmiş, promptfoo ile uyumlu ve engelleyici neden yoksa, meta judge'ın ek kontrolü gereksizdir.

**Profil bazlı davranış:**

- `deep` profili: Meta judge aktif stage listesindedir, ancak koşullar sağlanırsa atlanır
- `standard` profili: Meta judge `skip_stages` listesindedir, hiç çalışmaz
- `fast_track` profili: Meta judge `skip_stages` listesindedir, hiç çalışmaz

Meta judge atlandığında log kaydı ve broadcast mesajı:

```
meta_judge_skipped | confidence=0.92
meta_judge: done | "skipped (high confidence)"
```

### 6.2 Fact Check

Fact check, revise edilmiş dokümandaki iddiaların doğruluğunu kontrol eden bir aşamadır.

**Profil bazlı davranış:**

| Profil | Fact Check |
|--------|-----------|
| `fast_track` | ❌ `skip_stages` listesinde |
| `standard` | ❌ `skip_stages` listesinde |
| `deep` | ✅ Aktif, her zaman çalışır |

Fact check yalnızca deep profilinde çalışır. Standard ve fast_track profillerinde `skip_stages` listesinde yer aldığı için hiç çalıştırılmaz.

Fact check atlandığında:

```
fact_check_skipped_by_profile | run_id=xxx
fact_check: skipped | "not in profile"
```

### 6.3 Deep Analysis

Deep analysis, domain context ve codebase context'e dayalı kapsamlı mimari analizdir.

**Profil bazlı davranış:**

| Profil | Deep Analysis |
|--------|-------------|
| `fast_track` | ❌ `skip_stages` listesinde |
| `standard` | ❌ `skip_stages` listesinde |
| `deep` | ✅ Aktif, domain_context sonrası çalışır |

Deep analysis yalnızca `has_project=True` ve domain context bulunduğunda çalışır. Domain context boşsa deep analysis anlamsızdır ve atlanır:

```python
if has_deep and domain_context_str:
    # deep analysis çalışır
```

### 6.4 Stage Süreleri ve Koşullu Atlama Etkisi

| Stage | Süre (sn) | Fast Track | Standard | Deep |
|-------|-----------|-----------|----------|------|
| ingest | 0.5 | ✅ | ✅ | ✅ |
| complexity_router | 5 | - (auto değilse) | - | - |
| domain_context | 30 | ❌ | ✅ | ✅ |
| cross_reference | 33 | ❌ | ✅ | ✅ |
| deep_analysis | 198 | ❌ | ❌ | ✅ |
| critic_a_multi | 42 | ❌ | ✅ | ✅ |
| critic_b_multi | 39 | ❌ | ✅ | ✅ |
| critic_a_judge | 31 | ❌ | ✅ | ✅ |
| critic_b_judge | 31 | ❌ | ✅ | ✅ |
| dedupe | 1 | ❌ | ✅ | ✅ |
| validate | 39 | ✅ | ✅ | ✅ |
| revise | 19 | ✅ | ✅ | ✅ |
| score | 31 | ✅ | ✅ | ✅ |
| meta_judge | 209 | ❌ | ❌ | ✅ (koşullu) |
| fact_check | 87 | ❌ | ❌ | ✅ |
| report | 2 | ✅ | ✅ | ✅ |

---

## 7. Gerçek Dünyada Performans

Aşağıdaki veriler, gerçek DQG çalıştırmalarından elde edilmiş performans metrikleridir.

### 7.1 Benchmark Sonuçları

| Senaryo | Süre | Stage Sayısı | Token Kullanımı | Quality Confidence |
|---------|------|-------------|----------------|-------------------|
| **Deep (tam)** | 18-34 dk | 15 | ~500K+ | %98 |
| **Deep (optimize)** | ~10 dk | 15 | ~300K | %98 |
| **Standard** | ~3 dk | 12 | ~180K | %92 |
| **Early exit (xref)** | ~2.5 dk | 4-6 | ~50K | N/A (KALDI) |
| **Early exit (deep)** | ~4 dk | 6-8 | ~80K | N/A (KALDI) |
| **Fast track** | ~1.5 dk | 5 | ~30K | %70 |
| **Rescore** | ~2 dk | 3 | ~60K | Mevcut skor |

### 7.2 Stage Bazlı Gerçekçi Süreler

Aşağıdaki süreler, `config/pipeline_profiles.yaml` dosyasındaki `stage_durations` değerlerine dayanır ve gerçek LLM yanıt sürelerinden elde edilmiştir:

```yaml
stage_durations:
  ingest: 0.5        # Yerel dosya okuma
  complexity_router: 5   # Tek LLM çağrısı
  domain_context: 30     # Dosya tarama + LLM
  cross_reference: 33    # Kod tabanı tarama + LLM
  deep_analysis: 198     # Kapsamlı LLM analizi (en uzun)
  critic_a_multi: 42     # 2x LLM çağrısı, 3 workers
  critic_b_multi: 39     # 2x LLM çağrısı, 3 workers
  critic_a_judge: 31     # Tek LLM çağrısı
  critic_b_judge: 31     # Tek LLM çağrısı
  dedupe: 1              # Heuristik, LLM yok
  validate: 39           # LLM (sorun grubu başına)
  revise: 19             # LLM üretim
  score: 31              # Promptfoo + LLM
  meta_judge: 209        # Kapsamlı LLM analizi (ikinci en uzun)
  fact_check: 87         # Çoklu LLM çağrısı
  report: 2              # Şablon oluşturma
```

**En uzun 3 aşama:**
1. `meta_judge`: 209 sn (~3.5 dk) — Deep profilinde koşullu
2. `deep_analysis`: 198 sn (~3.3 dk) — Yalnızca deep profilinde
3. `fact_check`: 87 sn (~1.5 dk) — Yalnızca deep profilinde

Bu üç aşama toplamda ~494 sn (~8.2 dk) oluşturur. Standard profil bunları atlayarak ~3 dk'ya düşer.

### 7.3 Zaman Çizelgesi (Timeline) Gösterimi

**Deep Pipeline (Sıralı):**

```
ingest ░ (0.5s)
domain_context ████████████████ (30s)
cross_reference █████████████████ (33s)
deep_analysis ████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████ (198s)
critic_a_multi █████████████████████████ (42s)
critic_b_multi ███████████████████████ (39s)
critic_a_judge ███████████████ (31s)
critic_b_judge ███████████████ (31s)
dedupe ░ (1s)
validate █████████████████████ (39s)
revise █████████████ (19s)
score ███████████████ (31s)
meta_judge ████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████ (209s)
fact_check ████████████████████████████████████████████████ (87s)
report █ (2s)
TOPLAM: ~688s sıralı → ~600s fan-out ile
```

**Standard Pipeline (Fan-out ile):**

```
ingest ░ (0.5s)
[domain_context + cross_reference + critic_a + critic_b] paralel █████████████████████████ (max: 42s)
[critic_a_judge + critic_b_judge] paralel ███████████████ (31s)
dedupe ░ (1s)
validate █████████████████████ (39s)
revise █████████████ (19s)
score ███████████████ (31s)
report █ (2s)
TOPLAM: ~175s
```

**Fast Track Pipeline:**

```
ingest ░ (0.5s)
validate █████████████████████ (39s)
revise █████████████ (19s)
score ███████████████ (31s)
report █ (2s)
TOPLAM: ~90s
```

**Early Exit (Cross-Reference):**

```
ingest ░ (0.5s)
[domain_context + cross_reference + critic_a + critic_b] paralel █████████████████████████ (42s)
→ cross_reference: 3 critical → EARLY EXIT
TOPLAM: ~45s
```

### 7.4 Optimizasyon Bazlı İyileştirme Özeti

| Optimizasyon | Tahmini Tasarruf | Risk |
|-------------|-----------------|------|
| Pipeline profilleri (fast_track/standard) | %70-85 süre azaltma | Quality confidence düşer |
| Complexity router (auto) | Ortalama %50 süre azaltma | Yanlış profil seçimi riski |
| Aggressive fan-out (4 stage paralel) | ~100 sn tasarruf | Thread safety riski (yönetildi) |
| Early exit (xref) | Kritik durumlarda %75 süre azaltma | False positive ile erken çıkış |
| Conditional meta_judge | 209 sn tasarruf (koşullar sağlanırsa) | Düşük güven skorları gözden kaçabilir |
| fact_check skip (standard) | 87 sn tasarruf | Gerçek kontrol yapılmaz |

### 7.5 Rescore Performansı

Rescore, mevcut bir çalışmanın yalnızca skorlama aşamasını tekrar çalıştırır. Kullanıcı dokümanı manuel olarak düzelttikten sonra rescore yapabilir.

**Çalışan aşamalar:**
```
score → meta_judge (koşullu) → report
```

**Süre:** ~2 dakika

**Token kullanımı:** ~60K

**Meta judge koşullu atlama:** Rescore işleminde de aynı koşullar geçerlidir — `confidence >= 0.85` ve promptfoo anlaşması varsa meta judge atlanır.

---

## Ek: Yapılandırma Referansı

Tam pipeline profilleri yapılandırması `config/pipeline_profiles.yaml` dosyasında bulunur. Temel bölümler:

| Bölüm | Açıklama |
|-------|----------|
| `default_profile` | Varsayılan profil adı (`standard`) |
| `profiles` | Profil tanımları (stages, skip_stages, early_exit) |
| `parallel_groups` | Paralel çalışacak stage grupları |
| `stage_durations` | Her stage'in tahmini süresi (saniye) |
| `complexity_router` | Router eşik değerleri ve profil eşlemesi |
| `early_exit_rules` | Early exit kuralları (fatal_severities, min_fatal_count) |

**Simulator API:** Pipeline optimizasyonlarını görsel olarak test etmek için `/simulator` endpoint'i kullanılabilir:

- `GET /api/simulator/stages` — Tüm stage'ler ve tahmini süreler
- `POST /api/simulator/calculate` — Profile bazlı latency hesaplama
- `GET /api/simulator/profiles` — Mevcut profiller
- `GET /api/simulator/comparison` — Tüm profillerin karşılaştırması
