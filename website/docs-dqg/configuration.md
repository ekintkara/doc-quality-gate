---
sidebar_position: 15
title: Konfigurasyon
---

# Konfigürasyon

## Tüm Yapılandırma Dosyaları

DQG, dört ana konfigürasyon dosyası ve bir ortam değişkenleri dosyası ile yönetilir. Her dosya belirli bir sistemi konfigüre eder ve tüm parametreler ortam değişkenleri ile override edilebilir.

---

## Konfigürasyon Dosyaları Haritası

```
doc-quality-gate/
├── .env                              ← API anahtarları ve ortam değişkenleri
├── config/
│   ├── app.yaml                      ← Ana uygulama konfigürasyonu
│   ├── pipeline_profiles.yaml        ← Pipeline profil tanımları
│   └── litellm/
│       └── config.yaml               ← LiteLLM proxy model ve router ayarları
```

---

## 1. app.yaml — Ana Uygulama Konfigürasyonu

`config/app.yaml` dosyası, DQG'nin temel ayarlarını içerir. `${VARIABLE:default}` sözdizimi ile ortam değişkeni desteği sunar.

### Tam Yapı

```yaml
app:
  name: doc-quality-gate
  version: "0.1.0"

proxy:
  base_url: ${LITELLM_PROXY_URL:http://localhost:4000}
  api_key: ${LITELLM_MASTER_KEY:sk-dqg-local}
  timeout_seconds: 300

pipeline:
  critic_max_workers: ${DQG_CRITIC_WORKERS:3}
  critic_delay_seconds: ${DQG_CRITIC_DELAY:2}
  critic_runs: ${DQG_CRITIC_RUNS:2}
  scorer_runs: ${DQG_SCORER_RUNS:2}
  scorer_max_workers: ${DQG_SCORER_MAX_WORKERS:2}
  context_path: ${DQG_CONTEXT_PATH:}
  default_profile: ${DQG_DEFAULT_PROFILE:auto}

output:
  base_dir: ${DQG_OUTPUT_DIR:outputs/runs}

logging:
  level: ${DQGLOG_LEVEL:INFO}
  format: json
  log_dir: ${DQG_LOG_DIR:logs}
  max_file_size_mb: 10
  backup_count: 3

document_types:
  - feature_spec
  - implementation_plan
  - architecture_change
  - refactor_plan
  - migration_plan
  - incident_action_plan
  - custom

model_aliases:
  critic_a: cheap_large_context
  critic_b: cheap_large_context_alt
  critic_judge: cheap_large_context
  validator: strong_judge
  reviser: cheap_large_context
  scorer: strong_judge
  scorer_promptfoo: fallback_general
  meta_judge: strong_judge
  fallback: fallback_general

scoring:
  dimensions:
    - correctness
    - completeness
    - implementability
    - consistency
    - edge_case_coverage
    - testability
    - risk_awareness
    - clarity
```

### Bölüm Açıklamaları

#### `app` — Uygulama Bilgileri

| Parametre | Varsayılan | Açıklama |
|-----------|-----------|----------|
| `name` | `doc-quality-gate` | Uygulama adı |
| `version` | `0.1.0` | Uygulama versiyonu |

#### `proxy` — LiteLLM Proxy Bağlantısı

| Parametre | Varsayılan | Ortam Değişkeni | Açıklama |
|-----------|-----------|-----------------|----------|
| `base_url` | `http://localhost:4000` | `LITELLM_PROXY_URL` | Proxy URL'si |
| `api_key` | `sk-dqg-local` | `LITELLM_MASTER_KEY` | Proxy kimlik doğrulama anahtarı |
| `timeout_seconds` | `300` | — | Proxy çağrı timeout süresi (saniye) |

#### `pipeline` — Pipeline Ayarları

| Parametre | Varsayılan | Ortam Değişkeni | Açıklama |
|-----------|-----------|-----------------|----------|
| `critic_max_workers` | `3` | `DQG_CRITIC_WORKERS` | Critic aşamasında paralel çalışan sayısı |
| `critic_delay_seconds` | `2` | `DQG_CRITIC_DELAY` | Critic çağrıları arası gecikme (saniye) |
| `critic_runs` | `2` | `DQG_CRITIC_RUNS` | Her critic'in kaç kez çalışacağı |
| `scorer_runs` | `2` | `DQG_SCORER_RUNS` | Skorlama çalıştırma sayısı |
| `scorer_max_workers` | `2` | `DQG_SCORER_MAX_WORKERS` | Skorlamada paralel çalışan sayısı |
| `context_path` | (boş) | `DQG_CONTEXT_PATH` | Varsayılan domain context dizini |
| `default_profile` | `auto` | `DQG_DEFAULT_PROFILE` | Varsayılan pipeline profili |

**Critic Parametreleri Detayı:**

- `critic_max_workers: 3` — Aynı anda en fazla 3 paralel critic çağrısı
- `critic_delay_seconds: 2` — API rate limit'e takılmamak için her çağrı arası 2 saniye bekleme
- `critic_runs: 2` — Her critic (A ve B) 2 kez çalışır, sonuçlar birleştirilir

#### `output` — Çıktı Dizini

| Parametre | Varsayılan | Ortam Değişkeni | Açıklama |
|-----------|-----------|-----------------|----------|
| `base_dir` | `outputs/runs` | `DQG_OUTPUT_DIR` | Review çıktılarının kaydedildiği dizin |

Her review çalıştırmasında `base_dir` altında yeni bir alt dizin oluşturulur.

#### `logging` — Loglama Ayarları

| Parametre | Varsayılan | Ortam Değişkeni | Açıklama |
|-----------|-----------|-----------------|----------|
| `level` | `INFO` | `DQGLOG_LEVEL` | Log seviyesi: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `format` | `json` | — | Log formatı (structured logging) |
| `log_dir` | `logs` | `DQG_LOG_DIR` | Log dosyalarının kaydedildiği dizin |
| `max_file_size_mb` | `10` | — | Tek log dosyasının maksimum boyutu (MB) |
| `backup_count` | `3` | — | Tutulan eski log dosyası sayısı |

#### `document_types` — Desteklenen Doküman Türleri

| Tür | Açıklama |
|-----|----------|
| `feature_spec` | Yeni özellik spesifikasyonu |
| `implementation_plan` | Implementasyon planı |
| `architecture_change` | Mimari değişiklik dokümanı |
| `refactor_plan` | Refaktör planı |
| `migration_plan` | Geçiş (migration) planı |
| `incident_action_plan` | Olay aksiyon planı |
| `custom` | Özel doküman türü |

#### `model_aliases` — Stage → Model Grubu Eşleştirmesi

Her pipeline stage'inin hangi model grubunu kullanacağını belirler. Değerler LiteLLM proxy'sindeki `model_name` ile eşleşmelidir.

| Alias | Model Grubu | Açıklama |
|-------|------------|----------|
| `critic_a` | `cheap_large_context` | Critic A (mantıksal tutarlılık) |
| `critic_b` | `cheap_large_context_alt` | Critic B (uygulanabilirlik) |
| `critic_judge` | `cheap_large_context` | Critic hakem |
| `validator` | `strong_judge` | Sorun doğrulayıcı |
| `reviser` | `cheap_large_context` | Doküman düzeltici |
| `scorer` | `strong_judge` | Skorlayıcı |
| `scorer_promptfoo` | `fallback_general` | Promptfoo tabanlı skorlayıcı |
| `meta_judge` | `strong_judge` | Üst hakem |
| `fallback` | `fallback_general` | Genel yedek |

#### `scoring` — Skorlama Boyutları

DQG, dokümanları 8 boyutta değerlendirir:

| Boyut | Açıklama |
|-------|----------|
| `correctness` | Doğruluk — teknik bilgi ve iddiaların doğruluğu |
| `completeness` | Tamlık — gereksinimlerin ne kadar kapsandığı |
| `implementability` | Uygulanabilirlik — kodlamaya hazır olma durumu |
| `consistency` | Tutarlılık — doküman içi tutarlılık |
| `edge_case_coverage` | Uç Durum Kapsamı — edge case'lerin ele alınması |
| `testability` | Test Edilebilirlik — test stratejisinin netliği |
| `risk_awareness` | Risk Farkındalığı — risk tanımlama ve azaltma |
| `clarity` | Netlik — anlaşılırlık ve yapısal düzen |

---

## 2. pipeline_profiles.yaml — Pipeline Profil Tanımları

`config/pipeline_profiles.yaml` dosyası, farklı derinlik seviyelerindeki pipeline profillerini, paralel çalışma gruplarını, aşama sürelerini ve early exit kurallarını tanımlar.

### Tam Yapı

```yaml
default_profile: standard

profiles:
  fast_track:
    description: "Minor changes - skip heavy analysis"
    stages: [ingest, validate, revise, score, report]
    skip_stages: [domain_context, cross_reference, deep_analysis,
                  critic_a_multi, critic_b_multi, critic_a_judge,
                  critic_b_judge, dedupe, meta_judge, fact_check]
    early_exit: false
    estimated_latency_seconds: 90
    quality_confidence: 0.70

  standard:
    description: "Standard review - balanced"
    stages: [ingest, domain_context, cross_reference, critic_a_multi,
             critic_b_multi, critic_a_judge, critic_b_judge, dedupe,
             validate, revise, score, report]
    skip_stages: [deep_analysis, meta_judge, fact_check]
    early_exit: true
    early_exit_stages: [cross_reference]
    estimated_latency_seconds: 175
    quality_confidence: 0.92

  deep:
    description: "Full 14-stage pipeline"
    stages: [ingest, domain_context, cross_reference, deep_analysis,
             critic_a_multi, critic_b_multi, critic_a_judge, critic_b_judge,
             dedupe, validate, revise, score, meta_judge, fact_check, report]
    skip_stages: []
    early_exit: true
    early_exit_stages: [cross_reference, deep_analysis]
    estimated_latency_seconds: 600
    quality_confidence: 0.98
```

### Profil Karşılaştırması

| Özellik | Fast Track | Standard | Deep |
|---------|-----------|----------|------|
| Aşama Sayısı | 5 | 12 | 15 |
| Tahmini Süre | ~90 saniye | ~175 saniye | ~600 saniye |
| Kalite Güveni | %70 | %92 | %98 |
| Cross-Reference | Yok | Var | Var |
| Deep Analysis | Yok | Yok | Var |
| Meta-Judge | Yok | Yok | Var |
| Fact-Check | Yok | Yok | Var |
| Early Exit | Yok | Var (cross-ref) | Var (cross-ref + deep) |

### Profil Detayları

#### `fast_track` — Hızlı İnceleme

Küçük değişiklikler için tasarlanmıştır. Critic, cross-reference ve derin analiz aşamalarını atlar.

**Kullanım Senaryoları:**
- Küçük bug fix dokümanları
- Basit konfigürasyon değişiklikleri
- Tek satırlık düzeltmeler

**Aşama Akışı:**
```
ingest → validate → revise → score → report
```

#### `standard` — Standart İnceleme

Denge odaklı profil. Çoğu implementasyon planı için uygundur.

**Kullanım Senaryoları:**
- Yeni özellik spesifikasyonları
- Implementasyon planları
- Orta ölçekli değişiklikler

**Aşama Akışı:**
```
ingest → domain_context → cross_reference →
    [fan-out] critic_a_multi + critic_b_multi →
    [fan-out] critic_a_judge + critic_b_judge →
dedupe → validate → revise → score → report
```

**Early Exit:** Cross-reference aşamasında kritik sorun tespit edilirse pipeline durdurulur.

#### `deep` — Derin İnceleme

Tam 15 aşamalı pipeline. Kritik mimari değişiklikler için tasarlanmıştır.

**Kullanım Senaryoları:**
- Büyük mimari değişiklikler
- Migration planları
- Kritik sistem değişiklikleri

**Aşama Akışı:**
```
ingest → domain_context → cross_reference → deep_analysis →
    [fan-out] critic_a_multi + critic_b_multi →
    [fan-out] critic_a_judge + critic_b_judge →
dedupe → validate → revise → score → meta_judge → fact_check → report
```

### Paralel Çalışma Grupları

```yaml
parallel_groups:
  fan_out_group_1:
    stages: [domain_context, cross_reference, critic_a_multi, critic_b_multi]
    max_workers: 4
    description: "Domain context, cross-reference and both critics run in parallel"

  critic_judges:
    stages: [critic_a_judge, critic_b_judge]
    max_workers: 2
    description: "Both critic judges run in parallel"
```

| Grup | Aşamalar | Maks. Worker | Açıklama |
|------|----------|-------------|----------|
| `fan_out_group_1` | domain_context, cross_reference, critic_a_multi, critic_b_multi | 4 | Domain context, cross-ref ve her iki critic paralel çalışır |
| `critic_judges` | critic_a_judge, critic_b_judge | 2 | Her iki critic hakem paralel çalışır |

### Stage Süreleri (Tahmini)

```yaml
stage_durations:
  ingest: 0.5
  complexity_router: 5
  domain_context: 30
  cross_reference: 33
  deep_analysis: 198
  critic_a_multi: 42
  critic_b_multi: 39
  critic_a_judge: 31
  critic_b_judge: 31
  dedupe: 1
  validate: 39
  revise: 19
  score: 31
  meta_judge: 209
  fact_check: 87
  report: 2
```

| Aşama | Tahmini Süre (sn) | Not |
|-------|------------------|-----|
| ingest | 0.5 | Dosya okuma,几乎 anında |
| complexity_router | 5 | Karmaşıklık analizi |
| domain_context | 30 | Domain bilgi toplama |
| cross_reference | 33 | Kod tabanı karşılaştırma |
| deep_analysis | 198 | Derin mimari analiz (en uzun) |
| critic_a_multi | 42 | Critic A çoklu çalıştırma |
| critic_b_multi | 39 | Critic B çoklu çalıştırma |
| critic_a_judge | 31 | Critic A hakem değerlendirmesi |
| critic_b_judge | 31 | Critic B hakem değerlendirmesi |
| dedupe | 1 | Yinelenen sorunları ayıklama |
| validate | 39 | Sorun doğrulama |
| revise | 19 | Doküman düzeltme |
| score | 31 | 8 boyutlu skorlama |
| meta_judge | 209 | Üst hakem değerlendirmesi (en uzun) |
| fact_check | 87 | Gerçeklik kontrolü |
| report | 2 | Rapor oluşturma |

### Complexity Router

Doküman karmaşıklığına göre otomatik profil seçimi:

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

| Karmaşıklık Skoru | Sınıflandırma | Profil |
|-------------------|--------------|--------|
| 0-3 | `minor_change` | `fast_track` |
| 4-6 | `standard` | `standard` |
| 7+ | `major_change` | `deep` |

### Early Exit Kuralları

Belirli aşamalarda kritik sorunlar tespit edilirse pipeline erken durdurulur:

```yaml
early_exit_rules:
  cross_reference:
    fatal_severities: [critical]
    min_fatal_count: 1
    abort_message: "Fatal cross-reference errors detected"

  deep_analysis:
    fatal_severities: [critical]
    min_fatal_count: 2
    abort_message: "Critical architectural violations detected"
```

| Kural | Aşama | Tetikleyici | Minimum Sayı | Mesaj |
|-------|-------|------------|-------------|-------|
| cross_reference | Cross-Reference | `critical` seviye sorun | 1 | Fatal cross-reference errors detected |
| deep_analysis | Deep Analysis | `critical` seviye sorun | 2 | Critical architectural violations detected |

**Örnek:** Cross-reference aşamasında en az 1 `critical` seviye sorun bulunursa, kalan aşamalar atlanır ve pipeline rapor üretir.

---

## 3. litellm config.yaml — Model ve Router Ayarları

`config/litellm/config.yaml` dosyası, LiteLLM proxy'sinin model listesini, router ayarlarını ve fallback zincirlerini tanımlar.

### Tam Yapı

```yaml
model_list:
- model_name: cheap_large_context
  litellm_params:
    model: openai/glm-5-turbo
    api_base: https://api.z.ai/api/coding/paas/v4
    api_key: os.environ/ZAI_API_KEY
    headers:
      User-Agent: opencode/1.0.0
      HTTP-Referer: https://opencode.ai/
      X-Title: opencode
  model_info:
    mode: chat

- model_name: cheap_large_context_alt
  litellm_params:
    model: openai/glm-5-turbo
    api_base: https://api.z.ai/api/coding/paas/v4
    api_key: os.environ/ZAI_API_KEY
    headers: ...
  model_info:
    mode: chat

- model_name: strong_judge
  litellm_params:
    model: openai/glm-5.1
    api_base: https://api.z.ai/api/coding/paas/v4
    api_key: os.environ/ZAI_API_KEY
    headers: ...
  model_info:
    mode: chat

- model_name: fallback_general
  litellm_params:
    model: openai/glm-5
    api_base: https://api.z.ai/api/coding/paas/v4
    api_key: os.environ/ZAI_API_KEY
    headers: ...
  model_info:
    mode: chat

router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 300
  allowed_fails: 3
  fallbacks:
  - cheap_large_context: [fallback_general]
  - cheap_large_context_alt: [fallback_general]
  - strong_judge: [cheap_large_context, fallback_general]

litellm_settings:
  drop_params: true
  num_retries: 2
  request_timeout: 300
  fallbacks:
  - strong_judge: [fallback_general]

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

### Bölüm Açıklamaları

#### `model_list` — Model Tanımları

Her model girişi şu yapıya sahiptir:

```yaml
- model_name: <grup_adı>
  litellm_params:
    model: <sağlayıcı/model>
    api_base: <api_url>
    api_key: os.environ/<değişken_adı>
    headers:
      User-Agent: opencode/1.0.0
      HTTP-Referer: https://opencode.ai/
      X-Title: opencode
  model_info:
    mode: chat
```

| Alan | Açıklama |
|------|----------|
| `model_name` | Pipeline stage'lerinin kullandığı grup adı |
| `litellm_params.model` | Sağlayıcı ve model tanımlayıcısı |
| `litellm_params.api_base` | API endpoint URL'si |
| `litellm_params.api_key` | `os.environ/` prefix ile ortam değişkeni referansı |
| `litellm_params.headers` | Z.ai API'si için gerekli header'lar |
| `model_info.mode` | `chat` — sohbet modunda kullanım |

#### `router_settings` — Router Yapılandırması

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| `routing_strategy` | `simple-shuffle` | Rastgele model seçimi |
| `num_retries` | `2` | Başarısız çağrıyı 2 kez tekrar dene |
| `timeout` | `300` | Çağrı başına 300 saniye timeout |
| `allowed_fails` | `3` | 3 başarısızlıktan sonra model cooldown'a alınır |

**Fallback Zinciri:**

```
cheap_large_context ──► fallback_general
cheap_large_context_alt ──► fallback_general
strong_judge ──► cheap_large_context ──► fallback_general
```

#### `litellm_settings` — Genel LiteLLM Ayarları

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| `drop_params` | `true` | Desteklenmeyen parametreleri sessizce kaldır |
| `num_retries` | `2` | Genel retry sayısı |
| `request_timeout` | `300` | İstek timeout süresi |

#### `general_settings` — Genel Ayarlar

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| `master_key` | `os.environ/LITELLM_MASTER_KEY` | Proxy API'sine erişim için yönetici anahtarı |

---

## 4. .env — Ortam Değişkenleri

`.env` dosyası, API anahtarları ve hassas konfigürasyon değerleri için kullanılır.

### Tam Yapı

```env
ZAI_API_KEY=your-zai-api-key
LITELLM_MASTER_KEY=your-litellm-master-key

# Jira Integration (for from-jira command)
DQG_JIRA_BASE_URL=https://your-domain.atlassian.net
DQG_JIRA_EMAIL=your.email@domain.com
DQG_JIRA_API_TOKEN=your-jira-api-token
DQG_JIRA_PROJECT=YOUR_PROJECT_KEY
DQG_JIRA_DEFAULT_CONTEXT_PATH=C:\path\to\context
```

### Değişken Açıklamaları

#### LLM Erişimi

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `ZAI_API_KEY` | Evet | Z.ai platform API anahtarı — tüm LLM çağrıları için gerekli |
| `LITELLM_MASTER_KEY` | Evet | LiteLLM proxy yönetici anahtarı — proxy API'sine erişim |

#### Jira Entegrasyonu

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `DQG_JIRA_BASE_URL` | from-jira için | Jira sunucu URL'si |
| `DQG_JIRA_EMAIL` | from-jira için | Jira hesap e-postası |
| `DQG_JIRA_API_TOKEN` | from-jira için | Jira API token |
| `DQG_JIRA_PROJECT` | from-jira için | Jira proje anahtarı (örn. PDB) |
| `DQG_JIRA_DEFAULT_CONTEXT_PATH` | Hayır | `--cp` belirtilmediğinde kullanılacak varsayılan context yolu |

### Ortam Değişkeni Override'ları

`app.yaml` dosyasındaki değerler şu ortam değişkenleri ile override edilebilir:

| Ortam Değişkeni | app.yaml Parametresi | Varsayılan |
|-----------------|---------------------|-----------|
| `LITELLM_PROXY_URL` | `proxy.base_url` | `http://localhost:4000` |
| `LITELLM_MASTER_KEY` | `proxy.api_key` | `sk-dqg-local` |
| `DQG_CRITIC_WORKERS` | `pipeline.critic_max_workers` | `3` |
| `DQG_CRITIC_DELAY` | `pipeline.critic_delay_seconds` | `2` |
| `DQG_CRITIC_RUNS` | `pipeline.critic_runs` | `2` |
| `DQG_SCORER_RUNS` | `pipeline.scorer_runs` | `2` |
| `DQG_SCORER_MAX_WORKERS` | `pipeline.scorer_max_workers` | `2` |
| `DQG_CONTEXT_PATH` | `pipeline.context_path` | (boş) |
| `DQG_DEFAULT_PROFILE` | `pipeline.default_profile` | `auto` |
| `DQG_OUTPUT_DIR` | `output.base_dir` | `outputs/runs` |
| `DQGLOG_LEVEL` | `logging.level` | `INFO` |
| `DQG_LOG_DIR` | `logging.log_dir` | `logs` |

---

## 5. Eşik Değerler — Pass/Fail Thresholds

### Quality Gate Karar Mantığı

DQG, bir dokümanın pass veya fail olmasına şu kriterlere göre karar verir:

| Kriter | Eşik | Açıklama |
|--------|------|----------|
| **Overall Score** | >= 8.0 | Genel puan 10 üzerinden 8.0 veya üstü olmalıdır |
| **Kritik Sorunlar** | 0 | Çözülmemiş kritik (critical) seviye sorun olmamalıdır |
| **Blocking Reasons** | Yok | Engelleyici neden (blocking reason) olmamalıdır |

### Skor Sonuçları

```
Score >= 8.0 ve 0 çözülmemiş kritik sorun
    → PASS (proceed)
    → "Doküman kalite kapısından geçti."

Score < 8.0 veya çözülmemiş kritik sorunlar var
    → FAIL (revise_and_resubmit)
    → "Doküman revize edilmeli ve tekrar gönderilmeli."
```

### Dimension Score Eşikleri

Her boyut skoru 0-10 arasındadır. Renk kodlaması:

| Aralık | Renk | Anlam |
|--------|------|-------|
| 8.0 - 10.0 | Yeşil | İyi |
| 6.0 - 7.9 | Sarı | Kabul edilebilir ama iyileştirilebilir |
| 0.0 - 5.9 | Kırmızı | Zayıf, düzeltilmeli |

### Önerilen Aksiyonlar

| `recommended_next_action` | Açıklama |
|--------------------------|----------|
| `proceed` | Doküman geçti, implementasyona başlanabilir |
| `revise_and_resubmit` | Doküman kaldı, revize edilip tekrar gönderilmeli |
| `escalate` | Ciddi sorunlar var, manuel inceleme gerekli |

---

## Konfigürasyon Değişiklik Rehberi

### Model Değiştirme

1. **Web Dashboard → Settings** sayfasını açın
2. Model Groups bölümünde yeni model adını girin
3. "Update" butonuna tıklayın
4. LiteLLM proxy'sini yeniden başlatın

### Profil Değiştirme

1. `config/app.yaml` dosyasında `default_profile` değerini değiştirin
2. Veya `DQG_DEFAULT_PROFILE` ortam değişkenini set edin

### Pipeline Derinliğini Ayarlama

1. `config/pipeline_profiles.yaml` dosyasında ilgili profile `skip_stages` ekleyin veya çıkarın
2. `stage_durations` değerlerini güncelleyin
3. `early_exit_rules` kurallarını ayarlayın
