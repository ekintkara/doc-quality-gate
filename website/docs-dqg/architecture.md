---
sidebar_position: 2
title: Sistem Mimarisi
---

# Sistem Mimarisi

Doc Quality Gate (DQG), doküman kalite değerlendirmesi yapmak için tasarlanmış katmanlı, modüler ve eşzamanlı (concurrent) bir pipeline mimarisine sahiptir. Bu sayfa, sistemin tüm bileşenlerini, veri akışını ve tasarım kararlarını detaylı olarak açıklar.

---

## İçindekiler

- [Yüksek Seviye Mimari](#yüksek-seviye-mimari)
- [Katmanlar](#katmanlar)
  - [CLI Katmanı](#1-cli-katmanı-dqg_runpy)
  - [Web API Katmanı](#2-web-api-katmanı-fastapi)
  - [Orchestrator Katmanı](#3-orchestrator-katmanı)
  - [Stage Katmanı](#4-stage-katmanı)
  - [Entegrasyon Katmanı](#5-entegrasyon-katmanı)
  - [Konfigürasyon Katmanı](#6-konfigürasyon-katmanı)
- [Veri Akışı](#veri-akışı)
- [Orchestrator Deseni](#orchestrator-deseni)
- [Threading Modeli](#threading-modeli)
- [Durum Yönetimi](#durum-yönetimi)
- [Hata Yönetimi](#hata-yönetimi)
- [Bağımlılık Grafiği](#bağımlılık-grafiği)
- [Pipeline Profilleri](#pipeline-profilleri)

---

## Yüksek Seviye Mimari

```
┌─────────────────────────────────────────────────────────────────┐
│                        Kullanıcı Girişi                         │
│  ┌──────────┐  ┌───────────────────┐  ┌─────────────────────┐  │
│  │  CLI      │  │  Web UI           │  │  opencode /dqg      │  │
│  │dqg_run.py │  │  localhost:8080    │  │  komutu             │  │
│  └────┬──────┘  └────────┬──────────┘  └──────────┬──────────┘  │
│       │                  │                         │             │
│       ▼                  ▼                         ▼             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Servis Yönetimi (_ensure_services)          │    │
│  │   LiteLLM Proxy (port 4000) + Web Server (port 8080)    │    │
│  └─────────────────────────┬───────────────────────────────┘    │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   FastAPI Web API                        │    │
│  │  /api/review/start  /api/review/status  /api/events     │    │
│  │  /api/review/from-jira  /api/pipeline/cancel             │    │
│  │  /api/runs  /api/models  SSE endpoint                    │    │
│  └─────────────────────────┬───────────────────────────────┘    │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Orchestrator                           │    │
│  │   Pipeline yönetimi, stage sıralaması, iptal mekanizması│    │
│  │   Fan-out paralellik, early exit, durum broadcast        │    │
│  └──────┬──────────┬──────────┬──────────┬─────────────────┘    │
│         │          │          │          │                       │
│         ▼          ▼          ▼          ▼                       │
│  ┌──────────┐┌──────────┐┌──────────┐┌──────────┐              │
│  │ Domain   ││ Cross    ││ Critic A ││ Critic B │  ← Fan-out   │
│  │ Context  ││ Reference││ (Multi)  ││ (Multi)  │   Grup 1     │
│  └────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘              │
│       │           │           │           │                     │
│       ▼           ▼           ▼           ▼                     │
│  ┌──────────┐          ┌──────────┐┌──────────┐                │
│  │ Deep     │          │ Critic A ││ Critic B │  ← Paralel     │
│  │ Analysis │          │ Judge    ││ Judge    │   Judge        │
│  └────┬─────┘          └────┬─────┘└────┬─────┘                │
│       │                     │           │                       │
│       │                     ▼           ▼                       │
│       │                ┌──────────┐                            │
│       │                │  Dedupe  │                             │
│       │                └────┬─────┘                             │
│       │                     │                                   │
│       ▼                     ▼                                   │
│  ┌──────────┐  ┌──────────┐┌──────────┐┌──────────┐           │
│  │ Validate │→ │  Revise  ││  Score   ││Meta Judge│→ Report   │
│  └──────────┘  └──────────┘└──────────┘└──────────┘           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 Entegrasyon Katmanı                      │    │
│  │   LiteLLMClient ──→ LiteLLM Proxy ──→ LLM Sağlayıcılar  │    │
│  │   PromptfooRunner ──→ npx promptfoo eval                │    │
│  │   JiraReader ──→ Jira REST API                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                 Durum & Broadcast Katmanı                │    │
│  │   LogBroadcaster (singleton) → SSE → Web UI              │    │
│  │   TokenTracker → token_report.json                       │    │
│  │   Run dizini → JSON artifact'ları                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Katmanlar

### 1. CLI Katmanı (`dqg_run.py`)

**Dosya:** `scripts/dqg_run.py`

CLI katmanı, kullanıcıların terminal üzerinden DQG ile etkileşim kurmasını sağlar. Saf Python standart kütüphanesi kullanılarak yazılmıştır; dış bağımlılığı yoktur.

#### Alt Komutlar

| Komut | Açıklama |
|-------|----------|
| `launch` | Servisleri başlatır, asenkron review başlatır, hemen döner |
| `poll <review_id>` | Review sonucunu belirli aralıklarla sorgular |
| `auto-review` | Launch + poll işlemi tek komutta (bloklanabilir) |
| `from-jira <task_key>` | Jira task'ından doküman üret + DQG review (bloke eden) |
| `launch-from-jira` | Jira review'ı asenkron başlatır, hemen döner |
| `start` | Eski yöntem: arka plan süreci olarak review başlatır |
| `status` | Aktif review durumunu kontrol eder |
| `report` | En son çalışmanın raporunu yazdırır |
| `rescore <review_id>` | Önceki bir çalışmayı yeniden skorlar (hızlı) |
| `check-proxy` | LiteLLM proxy durumunu kontrol eder |
| `locate` | DQG proje kök dizinini yazdırır |

#### Servis Yönetimi (`_ensure_services`)

CLI, review komutlarından herhangi biri çağrıldığında önce gerekli servislerin çalıştığını kontrol eder:

1. **LiteLLM Proxy** (port 4000) — Çalışmıyorsa arka planda başlatılır
2. **Web Server** (port 8080) — Çalışmıyorsa uvicorn ile arka planda başlatılır

Her iki servis de `DETACHED_PROCESS` (Windows) veya `start_new_session=True` (Unix) ile ayrı süreçlerde çalışır. Proxy'nin hazır olması en fazla 30 deneme (60 saniye) beklenir.

```python
def _ensure_services():
    proxy_up = _check_proxy()
    web_up = _check_web()
    if proxy_up and web_up:
        return
    if not proxy_up:
        _start_proxy()
        _wait_for(_check_proxy, "PROXY", max_attempts=30, interval=2.0)
    if not web_up:
        _start_web_server()
        _wait_for(_check_web, "WEB", max_attempts=15, interval=2.0)
```

#### İş Akışı Desenleri

**Asenkron (Launch + Poll):**
```
Kullanıcı → launch → API POST /api/review/start → REVIEW_STARTED review_id=abc
Kullanıcı → poll abc → API GET /api/review/status/abc → STATUS: running/complete
```

**Senkron (Auto-review):**
```
Kullanıcı → auto-review → launch → poll (otomatik, max 120 deneme) → sonuç
```

**Jira Akışı:**
```
Kullanıcı → from-jira PDB-11139 → API POST /api/review/from-jira → poll → sonuç
```

---

### 2. Web API Katmanı (FastAPI)

**Dosya:** `src/app/web/app.py`

FastAPI tabanlı Web API katmanı, hem RESTful API uç noktaları hem de gömülü HTML sayfaları sunar. Uvicorn ASGI sunucusu üzerinde çalışır.

#### API Uç Noktaları

**Review İşlemleri:**

| Uç Nokta | Metot | Açıklama |
|----------|-------|----------|
| `/api/review` | POST | Senkron review (bloke eden) |
| `/api/review/start` | POST | Asenkron review başlatır, thread'de çalışır |
| `/api/review/from-jira` | POST | Jira task'tan asenkron review |
| `/api/review/status/{review_id}` | GET | Review durumunu sorgular |
| `/api/review/rescore` | POST | Önceki review'ı yeniden skorlar |
| `/api/pipeline/cancel` | POST | Aktif pipeline'ı iptal eder |

**Run Yönetimi:**

| Uç Nokta | Metot | Açıklama |
|----------|-------|----------|
| `/api/runs` | GET | Tüm geçmiş çalışmaları listeler |
| `/api/runs/{run_id}` | GET | Tek bir çalışmanın detaylarını döner |
| `/api/runs/{run_id}/report` | GET | HTML/Markdown raporu döner |
| `/api/runs/{run_id}/files` | GET | Çalışma dizinindeki dosyaları listeler |
| `/api/runs/{run_id}/file/{filename}` | GET | Tek bir dosya indirir |

**Gerçek Zamanlı Olaylar:**

| Uç Nokta | Metot | Açıklama |
|----------|-------|----------|
| `/api/events` | GET (SSE) | Server-Sent Events akışı |
| `/api/events/ingest` | POST | Harici olayları sisteme enjekte eder |

**Model & Konfigürasyon:**

| Uç Nokta | Metot | Açıklama |
|----------|-------|----------|
| `/api/models` | GET | Model grupları ve routing bilgisi |
| `/api/models/routing` | POST | Stage routing günceller |
| `/api/models/group/{name}` | POST | Model grup tanımını günceller |
| `/api/status` | GET | Proxy sağlığı ve sistem durumu |
| `/api/copilot/status` | GET | GitHub Copilot durum kontrolü |

**Simülatör:**

| Uç Nokta | Metot | Açıklama |
|----------|-------|----------|
| `/api/simulator/stages` | GET | Tüm stage'leri listeler |
| `/api/simulator/profiles` | GET | Pipeline profillerini listeler |
| `/api/simulator/calculate` | POST | Süre tahmini hesaplar |
| `/api/simulator/comparison` | GET | Profil karşılaştırması |

#### Sayfa Uç Noktaları (HTML)

| Yol | Açıklama |
|-----|----------|
| `/` veya `/dashboard` | Canlı dashboard — stage ilerlemesi, log akışı, LLM çağrıları |
| `/runs` | Geçmiş çalışmalar tablosu |
| `/run/{run_id}` | Tek çalışma detayı — skor kartı, boyut puanları, orijinal/düzeltilmiş doküman |
| `/settings` | Model grupları, stage routing, Copilot durumu |
| `/smoke` | Smoke test arayüzü |
| `/simulator` | Pipeline süre simülatörü |

#### Arka Plan İşleme Modeli

Review'lar arka plan thread'lerinde çalışır. Her review için:

1. Benzersiz `review_id` üretilir (UUID'nin ilk 12 karakteri)
2. `threading.Event` tabanlı bir iptal mekanizması oluşturulur
3. Daemon thread başlatılır
4. `_async_reviews` sözlüğünde durum takip edilir: `queued → running → complete/failed/cancelled`

```python
def _run_review_background(review_id, doc_path, doc_type, project_path, ...):
    try:
        _async_reviews[review_id]["status"] = "running"
        artifacts = orch.run(doc_path, doc_type, ...)
        _async_reviews[review_id]["status"] = "complete"
    except PipelineCancelledError:
        _async_reviews[review_id]["status"] = "cancelled"
    except Exception as e:
        _async_reviews[review_id]["status"] = "failed"
```

---

### 3. Orchestrator Katmanı

**Dosya:** `src/app/orchestrator.py`

Orchestrator, DQG sisteminin kalbidir. Pipeline'ın tamamını yönetir: stage sıralaması, paralel çalıştırma, iptal, durum broadcast ve artifact üretimi.

#### Orchestrator Sınıfı

```python
class Orchestrator:
    def __init__(self, config: AppConfig):
        self.config = config
        self.token_tracker = TokenTracker()
        self.client = LiteLLMClient(self.config, token_tracker=self.token_tracker)
        self.promptfoo_runner = PromptfooRunner(self.config.config_dir, ...)
```

#### Temel Metodlar

| Metod | Açıklama |
|-------|----------|
| `run()` | Tam pipeline çalıştırması |
| `run_from_jira()` | Jira task → doküman üretimi → pipeline |
| `run_rescore()` | Sadece score + meta_judge (hızlı yeniden skorlama) |
| `run_eval_only()` | Sadece değerlendirme (mevcut artifact'lerden) |
| `run_fact_check_only()` | Sadece fact-check aşaması |
| `run_apply_fixes()` | Fact-check düzeltmelerini uygular |
| `smoke_test()` | Proxy ve model bağlantı testi |

#### Pipeline Çalıştırma Akışı (`run` metodu)

`run()` metodu ~700 satırlık ana pipeline akışıdır. Aşamalar şunlardır:

1. **Run dizini oluşturma** — `outputs/runs/<run_id>/` dizini yaratılır
2. **İncest** — Doküman okunur ve türü tespit edilir
3. **Profil seçimi** — `pipeline_profiles.yaml`'dan profil yüklenir; `auto` ise complexity router çalışır
4. **Fan-out Grup 1** — `domain_context`, `cross_reference`, `critic_a_multi`, `critic_b_multi` paralel çalışır
5. **Deep analysis** — Domain analizi (opsiyonel)
6. **Early exit kontrolü** — Kritik hatalarda erken çıkış
7. **Critic judge** — Her iki critic'in sonuçları paralel değerlendirilir
8. **Dedup** — Tekrar eden sorunlar birleştirilir
9. **Validate** — Sorunlar geçerlilik kontrolünden geçirilir
10. **Revise** — Geçerli sorunlara göre doküman düzeltilir
11. **Score** — Çoklu scorer çalışması + Promptfoo rubrik değerlendirmesi
12. **Meta judge** — Skorun adilliğini değerlendirir, ayarlama yapar
13. **Fact check** — Gerçeklik kontrolü (opsiyonel)
14. **Report** — Markdown ve HTML raporları üretilir
15. **Türkçe özet** — LLM ile Türkçe durum özeti oluşturulur

---

### 4. Stage Katmanı

**Dizin:** `src/app/stages/`

Her stage, bağımsız bir Python modülüdür. Orchestrator tarafından sıralı veya paralel olarak çağrılır.

#### Stage Listesi

| Modül | Stage Adı | Açıklama | LLM Kullanır mı? |
|-------|-----------|----------|-------------------|
| `ingest.py` | `ingest` | Dokümanı okur, türünü tespit eder | Hayır |
| `complexity_router.py` | `complexity_router` | Doküman karmaşıklığını analiz eder, profil önerir | Evet |
| `domain_context.py` | `domain_context` | Proje dizininden domain bağlamını çıkarır | Evet |
| `cross_reference.py` | `cross_reference` | Dokümanı kod tabanıyla çapraz kontrol eder | Evet |
| `deep_analysis.py` | `deep_analysis` | Domain bazlı derin analiz yapar | Evet |
| `critic.py` | `critic_a_multi` / `critic_b_multi` | İki farklı perspektiften çoklu critic çalışması | Evet |
| `critic_judge.py` | `critic_a_judge` / `critic_b_judge` | Critic sonuçlarını değerlendirir, sorun listesi üretir | Evet |
| `dedupe.py` | `dedupe` | Tekrar eden sorunları birleştirir | Hayır |
| `validate.py` | `validate` | Sorunların geçerliliğini kontrol eder | Evet |
| `revise.py` | `revise` | Geçerli sorunlara göre dokümanı düzeltir | Evet |
| `score.py` | `score` | 8 boyutta skorlama + Promptfoo rubrik | Evet |
| `meta_judge.py` | `meta_judge` | Skorun adilliğini değerlendirir | Evet |
| `fact_check.py` | `fact_check` | Sorunların gerçeklik kontrolü | Evet |
| `report.py` | `report` | Markdown ve HTML rapor üretimi | Hayır |
| `task_analyzer.py` | `task_analysis` | Jira task'ını analiz eder | Evet |
| `document_generator.py` | `document_generation` | Jira task'tan implementasyon dokümanı üretir | Evet |

#### Critic Çalışma Deseni

Critic stage'leri benzersiz bir "çoklu çalıştırma" desenine sahiptir:

```
Critic A (N run) → Judge A → ┐
                               ├→ Dedup → Birleştirilmiş Sorun Listesi
Critic B (N run) → Judge B → ┘
```

- Her critic N kez çalışır (`critic_runs` konfigürasyonu, varsayılan: 2)
- Her çalıştırma arasında gecikme vardır (`critic_delay_seconds`, varsayılan: 2.0)
- Her çalıştırma ayrı bir thread'de (`critic_max_workers`, varsayılan: 3)
- Her critic'in kendi judge'ı vardır
- Sonuçlar dedup stage'inde birleştirilir

#### Score Stage

Score stage'i iki bağımsız değerlendirme sistemini birleştirir:

1. **LLM Scorer** — `scorer` model grubu ile 8 boyutta puanlama
2. **Promptfoo Rubrik** — `scorer_promptfoo` model grubu ile rubrik bazlı değerlendirme

Her iki sistem de birden fazla kez çalışır (`scorer_runs` kez, paralel: `scorer_max_workers`). Sonuçlar ortalaması alınarak `Scorecard` üretilir.

#### 8 Skor Boyutu

| Boyut | Açıklama |
|-------|----------|
| `correctness` | Doğruluk — bilgilerin teknik doğruluğu |
| `completeness` | Tamlık — tüm gerekli bilgilerin mevcudiyeti |
| `implementability` | Uygulanabilirlik — geliştirici tarafından uygulanabilir olma |
| `consistency` | Tutarlılık — doküman içi çelişkisizlik |
| `edge_case_coverage` | Sınır Durum Kapsamı — uç durumların ele alınması |
| `testability` | Test Edilebilirlik — test stratejisinin varlığı |
| `risk_awareness` | Risk Farkındalığı — risklerin tanımlanması |
| `clarity` | Netlik — anlaşılır ve okunabilir olma |

---

### 5. Entegrasyon Katmanı

**Dizin:** `src/app/integrations/`

#### LiteLLMClient (`litellm_client.py`)

Tüm LLM çağrıları tek bir istemci üzerinden geçer. LiteLLM Proxy'ye HTTP istekleri gönderir.

**Temel özellikler:**

- **Model çözümleme:** Stage adını model grubuna çevirir (`resolve_model("critic_a")` → `"cheap_large_context"`)
- **Proxy üzerinden yönlendirme:** Tüm istekler `http://localhost:4000/chat/completions` uç noktasına gider
- **Token takibi:** Her çağrıda token kullanımı `TokenTracker`'a kaydedilir (stage ve model bazlı)
- **Broadcast:** Her LLM çağrısı `LogBroadcaster` üzerinden SSE ile Web UI'ya iletilir
- **Hata yönetimi:** Timeout ve HTTP hataları için yapılandırılmış hata mesajları

```python
client.chat_completion(
    model="cheap_large_context",
    messages=[{"role": "user", "content": "..."}],
    temperature=0.3,
    max_tokens=4096,
    stage="critic_a",
)
```

#### PromptfooRunner (`promptfoo_runner.py`)

Rubrik bazlı doküman değerlendirmesi için `npx promptfoo eval` komutunu sarar.

**Çalışma akışı:**

1. Doküman türüne uygun rubrik dosyasını yükler (`config/promptfoo/rubrics/<doc_type>.yaml`)
2. Geçici dizinde Promptfoo konfigürasyonu oluşturur
3. `npx promptfoo eval` komutunu çalıştırır
4. JSON çıktısını parse eder
5. 8 boyut için `llm-rubric` assertion sonuçlarını toplar

Rubrik yoksa `generic.yaml` fallback olarak kullanılır.

#### JiraReader (`jira_reader.py`)

Jira REST API üzerinden task bilgilerini ve yorumlarını okur.

- ADF (Atlassian Document Format) açıklamalarını parse eder
- Task yorumlarını toplar
- `JiraConfig` üzerinden kimlik doğrulama yapar (e-posta + API token)

---

### 6. Konfigürasyon Katmanı

**Dizin:** `config/`

#### Konfigürasyon Dosyaları

| Dosya | Açıklama |
|-------|----------|
| `app.yaml` | Ana uygulama konfigürasyonu — proxy, pipeline, model alias'ları |
| `pipeline_profiles.yaml` | Pipeline profilleri — stage listesi, paralel gruplar, early exit kuralları |
| `thresholds.yaml` | Skor eşikleri — doküman türü bazlı |
| `model_routing.yaml` | Model grup tanımları ve sağlayıcı bilgileri |
| `litellm/config.yaml` | LiteLLM Proxy konfigürasyonu — model listesi, yönlendirme |
| `promptfoo/rubrics/*.yaml` | Her doküman türü için değerlendirme rubrikleri |
| `prompts/*.md` | Stage'ler için LLM prompt şablonları |

#### Ortam Değişkeni Desteği (`_resolve_env`)

Konfigürasyon değerleri `${ENV_VAR:default}` sözdizimini destekler:

```yaml
proxy:
  base_url: ${LITELLM_PROXY_URL:http://localhost:4000}
  api_key: ${LITELLM_MASTER_KEY:sk-dqg-local}
```

Eğer ortam değişkeni tanımlıysa onu kullanır, değilse varsayılan değeri kullanır.

#### Model Alias Sistemi

Stage'ler doğrudan model adı bilmez; model gruplarına başvurur:

```yaml
model_aliases:
  critic_a: cheap_large_context        # → zai/glm-4.5
  critic_b: cheap_large_context_alt    # → zai/glm-4.5-air
  critic_judge: cheap_large_context    # → zai/glm-4.5
  validator: strong_judge              # → github_copilot/gpt-4o
  reviser: cheap_large_context         # → zai/glm-4.5
  scorer: strong_judge                 # → github_copilot/gpt-4o
  scorer_promptfoo: fallback_general   # → zai/glm-4.5-flash
  meta_judge: strong_judge             # → github_copilot/gpt-4o
```

**Avantajları:**

- Stage kodu değiştirilmeden model değiştirilebilir
- Farklı sağlayıcılar arasında geçiş yapılabilir
- Maliyet optimizasyonu: ucuz modeller yüksek token gerektiren stage'lerde, güçlü modeller karar stage'lerinde

---

## Veri Akışı

Pipeline boyunca veri şu şekilde akar:

```
┌─────────────┐
│ Markdown     │  ← Kullanıcı tarafından sağlanan veya Jira'dan üretilen doküman
│ doküman      │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ İncest       │  → original.md (ham içerik), resolved_type (tespit edilen tür)
└──────┬──────┘
       │
       ├──── content ────────────────────────────────────┐
       │                                                  │
       ▼                                                  ▼
┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────┐
│ Domain Ctx   │  │ Cross Ref    │  │  Critic A   │  │  Critic B  │
│ (project/)   │  │ (content +   │  │  (content)  │  │  (content) │
│              │  │  project/)   │  │  N runs     │  │  N runs    │
└──────┬───────┘  └──────┬───────┘  └─────┬──────┘  └─────┬──────┘
       │                 │                 │                │
       │  domain_context │  cross_ref_     │  runs_a        │  runs_b
       │  _str           │  issues         │                │
       │                 │  codebase_ctx   ▼                ▼
       │                 │          ┌────────────┐  ┌────────────┐
       │                 │          │ Judge A    │  │ Judge B    │
       │                 │          │ (runs_a)   │  │ (runs_b)   │
       │                 │          └─────┬──────┘  └─────┬──────┘
       │                 │                │                │
       ▼                 │                ▼                ▼
┌──────────────┐         │          ┌──────────────────────────┐
│ Deep         │         │          │       Dedupe             │
│ Analysis     │         │          │  issues_a + issues_b     │
│ (content +   │         │          │  → merged_issues         │
│  domain_ctx) │         │          └────────────┬─────────────┘
└──────┬───────┘         │                       │
       │                 │                       ▼
       │  domain_        │  cross_ref_    ┌──────────────┐
       │  analysis_str   │  issues        │   Validate   │
       │                 │  + merged      │              │
       └─────────────────┴───────┬─────── │  domain_ctx  │
                                 │        │  codebase_ctx│
                                 │        │  domain_     │
                                 │        │  analysis    │
                                 │        └──────┬───────┘
                                 │               │
                                 │               ▼ valid_issues
                                 │        ┌──────────────┐
                                 ├───────→│    Revise    │
                                 │        │              │
                                 │        └──────┬───────┘
                                 │               │
                                 │               ▼ revised.md
                                 │        ┌──────────────┐
                                 ├───────→│    Score     │
                                 │        │  LLM +       │
                                 │        │  Promptfoo   │
                                 │        └──────┬───────┘
                                 │               │
                                 │               ▼ scorecard.json
                                 │        ┌──────────────┐
                                 ├───────→│  Meta Judge  │
                                 │        │  (opsiyonel) │
                                 │        └──────┬───────┘
                                 │               │
                                 │               ▼ adjusted scorecard
                                 │        ┌──────────────┐
                                 ├───────→│  Fact Check  │
                                 │        │  (opsiyonel) │
                                 │        └──────┬───────┘
                                 │               │
                                 │               ▼
                                 │        ┌──────────────┐
                                 └───────→│   Report     │
                                          │  MD + HTML   │
                                          └──────┬───────┘
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │ Türkçe Özet  │
                                          │ (LLM ile)    │
                                          └──────────────┘
```

---

## Orchestrator Deseni

Orchestrator, "imperative pipeline" desenini kullanır. LangGraph, Prefect veya Airflow gibi bir framework yerine, saf Python ile sıralı ve paralel stage yönetimi yapar.

### Temel Özellikler

#### Stage Yönetimi

Her stage öncesi ve sonrası broadcast yapılır:

```python
_broadcast_stage(run_id, "critic_a_multi", "running")  # Stage başladı
# ... stage çalışır ...
_broadcast_stage(run_id, "critic_a_multi", "done", "5 issues")  # Stage bitti
```

Bu broadcast'ler `LogBroadcaster` üzerinden tüm SSE abonelerine iletilir.

#### İptal Mekanizması

Her stage öncesi iptal kontrolü yapılır:

```python
_check_cancel(cancel_event, run_id, "validate")
```

Eğer `cancel_event` set edilmişse, `PipelineCancelledError` fırlatılır ve pipeline temiz bir şekilde sonlanır.

#### Early Exit

Belirli stage'lerde kritik hatalar tespit edilirse pipeline erken sonlandırılabilir:

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

Early exit tetiklendiğinde:
- `early_exit.json` dosyası yazılır
- Kısmi `metadata.json` oluşturulur
- Token raporu kaydedilir
- `RunArtifacts` döndürülür (`execution_status: "early_exit"`)

#### Meta Judge Atlama Koşulu

Meta judge, yüksek güvenilirlik durumunda otomatik olarak atlanır:

```python
skip_meta = (
    scorecard.confidence_in_scoring >= 0.85
    and scorecard.promptfoo_agreement in ("agree", None)
    and not scorecard.blocking_reasons
)
```

---

## Threading Modeli

DQG, `concurrent.futures.ThreadPoolExecutor` kullanarak I/O-bound LLM çağrılarını paralelleştirir.

### Paralel Çalıştırma Grupları

#### Fan-out Grup 1 (Maks 4 Worker)

Proje yolu verildiğinde, şu stage'ler paralel çalışır:

```
ThreadPoolExecutor(max_workers=4)
├── domain_context    ← Proje dizininden domain bilgisi çıkarır
├── cross_reference   ← Dokümanı kod tabanıyla karşılaştırır
├── critic_a_multi    ← Çoklu critic A çalışması
└── critic_b_multi    ← Çoklu critic B çalışması
```

Her critic kendi içinde de `ThreadPoolExecutor` kullanır (`critic_max_workers` worker ile N çalıştırma yapar).

#### Critic Judge Paralelliği (Maks 2 Worker)

```
ThreadPoolExecutor(max_workers=2)
├── critic_a_judge   ← Critic A sonuçlarını değerlendirir
└── critic_b_judge   ← Critic B sonuçlarını değerlendirir
```

#### Critic İç Paralelliği

Her critic stage'i, N çalıştırma arasında paralellik sağlar:

```python
def run_critic_a_multi(client, content, doc_type, n_runs=2, max_workers=3, delay_seconds=2.0):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i in range(n_runs):
            futures.append(executor.submit(run_critic_a_single, client, content, doc_type, i))
            time.sleep(delay_seconds)  # Rate limiting
        results = [f.result() for f in futures]
    return results
```

#### Scorer Paralelliği

Score stage'i, `scorer_runs` kez LLM skorlamasını paralel çalıştırır (`scorer_max_workers` worker ile).

### Thread Güvenliği

- `LogBroadcaster` singleton'dur; thread-safe `publish()` metodu kullanır
- `TokenTracker`, thread-safe sayaçlar kullanır
- Her review kendi `threading.Event` iptal mekanizmasına sahiptir
- `_async_reviews` sözlüğü ana thread'den erişilir (FastAPI async context)

### Arka Plan Thread Modeli

Web API'de her review bir daemon thread'de çalışır:

```python
t = threading.Thread(
    target=_run_review_background,
    args=(review_id, doc_path, doc_type, project_path),
    kwargs={"context_path": context_path, "cancel_event": cancel_event},
    daemon=True,
)
t.start()
```

---

## Durum Yönetimi

### Run Dizinleri

Her pipeline çalıştırması için benzersiz bir dizin oluşturulur:

```
outputs/runs/
└── 20250607_143022_a1b2c3d4/
    ├── original.md          ← Orijinal doküman
    ├── revised.md           ← Düzeltilmiş doküman
    ├── issues.json          ← Tespit edilen tüm sorunlar
    ├── validations.json     ← Sorun geçerlilik kararları
    ├── scorecard.json       ← Skor kartı (8 boyut + genel)
    ├── metadata.json        ← Çalışma metadatası (modeller, süre, token)
    ├── token_report.json    ← Detaylı token kullanım raporu
    ├── report.md            ← Markdown rapor
    ├── report.html          ← HTML rapor
    ├── pipeline_profile.json← Kullanılan profil bilgisi
    ├── domain_context.md    ← Domain bağlam metni (opsiyonel)
    ├── domain_docs.json     ← Domain doküman listesi (opsiyonel)
    ├── domain_analysis.json ← Derin analiz sonuçları (opsiyonel)
    ├── domain_analysis.md   ← Derin analiz metni (opsiyonel)
    ├── codebase_context.md  ← Kod tabanı bağlamı (opsiyonel)
    ├── cross_ref_issues.json← Çapraz referans sorunları (opsiyonel)
    ├── meta_judge.json      ← Meta judge sonuçları (opsiyonel)
    ├── promptfoo_raw.json   ← Promptfoo ham çıktı (opsiyonel)
    ├── fact_check.json      ← Fact-check sonuçları (opsiyonel)
    ├── fact_check.md        ← Fact-check raporu (opsiyonel)
    ├── task_analysis.json   ← Jira task analizi (opsiyonel)
    ├── early_exit.json      ← Early exit bilgisi (opsiyonel)
    └── complexity_router.json← Karmaşıklık analizi (opsiyonel)
```

### JSON Artifact'ları

Her stage çıktısını JSON olarak yazar (`write_json`). Bu sayede:

- Herhangi bir stage sonucu bağımsız olarak incelenebilir
- `run_rescore` ve `run_eval_only` metodları önceki artifact'leri okuyarak çalışır
- Hata durumunda kısmi sonuçlar korunur

### SSE (Server-Sent Events) Broadcast

`LogBroadcaster`, gerçek zamanlı olay yayınlayan bir singleton bileşendir.

**Olay tipleri:**

| Tip | Açıklama |
|-----|----------|
| `pipeline_stage` | Bir stage başladı/bitti/hata verdi |
| `pipeline_done` | Pipeline tamamlandı (skor, geçti/kaldı, Türkçe özet) |
| `llm_call` | Bir LLM çağrısı yapıldı (model, token, süre) |
| `log` | Genel log mesajı |
| `setup_step` | Kurulum adımı |

**Abone modeli:**

```
LogBroadcaster (singleton)
├── SSE Client 1 → asyncio.Queue → /api/events stream
├── SSE Client 2 → asyncio.Queue → /api/events stream
└── HTTP Forward → buffer → POST /api/events/ingest
```

Her SSE client bağlandığında bir `asyncio.Queue` oluşturulur. Son 500 mesajlık geçmiş (history) yeni abonelere gönderilir.

### Token Takibi

`TokenTracker`, tüm LLM çağrılarında token kullanımını kaydeder:

- **Stage bazlı:** Her stage'in ne kadar token kullandığı
- **Model bazlı:** Her modelin ne kadar token kullandığı
- **Çağrı sayısı:** Toplam LLM çağrısı sayısı
- Pipeline sonunda `token_report.json` olarak yazılır

---

## Hata Yönetimi

### Hata Tipleri

#### PipelineCancelledError

Kullanıcı tarafından pipeline iptal edildiğinde fırlatılır.

```python
class PipelineCancelledError(Exception):
    pass
```

**Davranış:**
1. `_check_cancel` her stage öncesi kontrol eder
2. `cancel_event.is_set()` → `PipelineCancelledError` fırlatılır
3. `metadata.json`'a `execution_status: "cancelled"` yazılır
4. Exception yeniden fırlatılır, arka plan thread'de yakalanır
5. `_async_reviews[review_id]["status"] = "cancelled"` olarak güncellenir

#### Early Exit

Kritik hatalar tespit edildiğinde pipeline normal akışta erken sonlanır.

**Davranış:**
1. Early exit koşulu kontrol edilir (fatal severity + min count)
2. `early_exit.json` yazılır
3. Kısmi `RunArtifacts` oluşturulur (`execution_status: "early_exit"`)
4. Normal dönüş yapılır (exception yok)

#### Stage Hataları

Herhangi bir stage'de exception oluşursa:

1. Pipeline geneli `try/except Exception` bloğundadır
2. `metadata.json`'a `execution_status: "failed"` yazılır
3. Hata detayı structlog ile loglanır
4. `_broadcast_done` çağrılarak SSE client'lar bilgilendirilir
5. Exception yeniden fırlatılır

#### Fact-check Hatası

Fact-check stage'i özel try/except ile sarılır; başarısız olursa pipeline devam eder:

```python
try:
    fact_check_result = run_fact_check(self.client, run_dir)
except Exception as e:
    logger.warning("fact_check_failed", error=str(e))
    _broadcast_stage(run_id, "fact_check", "failed", str(e))
```

### Fallback Davranışları

| Durum | Fallback |
|-------|----------|
| LiteLLM Proxy çalışmıyor | Smoke test ile uyarı, pipeline başlatılmaz |
| Promptfoo yüklü değil | Sadece LLM scorer kullanılır |
| Rubrik bulunamıyor | `generic.yaml` fallback |
| Model alias tanımsız | Stage adı doğrudan model adı olarak kullanılır |
| Domain context yok | `domain_context_str = ""`, deep analysis atlanır |
| Project path yok | Cross-reference atlanır, sadece critic çalışır |
| Türkçe özet başarısız | Basit format string ile fallback |
| LogBroadcaster kullanılamıyor | `try/except` ile sessizce atlanır |

---

## Bağımlılık Grafiği

Stage'ler arasındaki veri bağımlılıkları aşağıda gösterilmiştir. Bir ok, hedef stage'in kaynak stage'in çıktısına bağımlı olduğunu belirtir.

```
                    ┌──────────┐
                    │  İncest   │
                    └────┬─────┘
                         │ content, resolved_type
                         │
              ┌──────────┼──────────────────────────────┐
              │          │                              │
              ▼          ▼                              ▼
     ┌────────────┐ ┌──────────┐              ┌───────────────┐
     │Domain Ctx  │ │Cross Ref │              │ Complexity    │
     │            │ │          │              │ Router        │
     └────┬───────┘ └────┬─────┘              └───────┬───────┘
          │              │                            │
          │              │                            ▼
          │              │                     ┌──────────────┐
          │              │                     │ Profile Seçimi│
          │              │                     └──────────────┘
          │              │
          │    ┌─────────┴──────────┐
          │    │                    │
          │    ▼                    ▼
          │  ┌────────────┐  ┌────────────┐
          │  │ Critic A   │  │ Critic B   │    ← İkisi de content'e bağımlı
          │  │ (Multi)    │  │ (Multi)    │
          │  └────┬───────┘  └────┬───────┘
          │       │               │
          │       ▼               ▼
          │  ┌────────────┐  ┌────────────┐
          │  │ Judge A    │  │ Judge B    │    ← runs_a / runs_b'ye bağımlı
          │  └────┬───────┘  └────┬───────┘
          │       │               │
          │       └───────┬───────┘
          │               ▼
          │        ┌────────────┐
          │        │   Dedupe   │              ← issues_a + issues_b'ye bağımlı
          │        └────┬───────┘
          │             │
          │             ▼ merged_issues + cross_ref_issues
          │        ┌────────────┐
          ├───────→│  Validate  │              ← domain_ctx, codebase_ctx, domain_analysis
          │        └────┬───────┘
          │             │
          │             ▼ valid_issues
          │        ┌────────────┐
          ├───────→│   Revise   │              ← content + valid_issues
          │        └────┬───────┘
          │             │
          │             ▼ revised.md
          │        ┌────────────┐
          ├───────→│   Score    │              ← revised + original + issues + validations
          │        └────┬───────┘
          │             │
          │             ▼ scorecard
          │        ┌────────────┐
          ├───────→│ Meta Judge │              ← scorecard + revised (opsiyonel)
          │        └────┬───────┘
          │             │
          │             ▼ adjusted scorecard
          │        ┌────────────┐
          ├───────→│ Fact Check │              ← issues + revised (opsiyonel)
          │        └────┬───────┘
          │             │
          ▼             ▼
     ┌─────────────────────────┐
     │        Report           │              ← tüm artifact'ler
     └────────────┬────────────┘
                  │
                  ▼
           ┌────────────┐
           │ Türkçe Özet│              ← scorecard + issues + validations
           └────────────┘
```

### Bağımlılık Tablosu

| Stage | Girdi Bağımlılıkları |
|-------|---------------------|
| `ingest` | Dosya yolu, doc_type (opsiyonel) |
| `complexity_router` | content (ingest çıktısı) |
| `domain_context` | project_path, doc_type |
| `cross_reference` | content, doc_type, project_path |
| `deep_analysis` | content, doc_type, domain_context_str, codebase_context |
| `critic_a_multi` | content, doc_type |
| `critic_b_multi` | content, doc_type |
| `critic_a_judge` | runs_a (critic_a_multi çıktısı), content, doc_type |
| `critic_b_judge` | runs_b (critic_b_multi çıktısı), content, doc_type |
| `dedupe` | issues_a, issues_b |
| `validate` | all_issues, content, domain_context, codebase_context, domain_analysis |
| `revise` | content, doc_type, valid_issues |
| `score` | revised_content, doc_type, original_content, issues, validations, threshold_config |
| `meta_judge` | scorecard, revised_content, doc_type |
| `fact_check` | run_dir (issues.json, revised.md) |
| `report` | RunArtifacts (tüm önceki çıktılar) |

---

## Pipeline Profilleri

Üç yerleşik profil mevcuttur:

### Fast Track

- **Süre:** ~90 saniye
- **Güven:** %70
- **Stage'ler:** ingest → validate → revise → score → report
- **Kullanım:** Küçük değişiklikler, hızlı geri bildirim

### Standard

- **Süre:** ~175 saniye
- **Güven:** %92
- **Stage'ler:** ingest → domain_context → cross_reference → critic_a/b → judge_a/b → dedupe → validate → revise → score → report
- **Early exit:** cross_reference'da kritik hata varsa
- **Kullanım:** Genel doküman değerlendirmesi (varsayılan profil)

### Deep

- **Süre:** ~600 saniye (~10 dakika)
- **Güven:** %98
- **Stage'ler:** Tam 14 stage pipeline
- **Early exit:** cross_reference ve deep_analysis'da
- **Kullanım:** Kritik dokümanlar, mimari değişiklikler

### Auto (Complexity Router)

`auto` profili seçildiğinde, `complexity_router` stage'i dokümanı analiz eder ve uygun profili otomatik belirler:

```
Karmaşıklık Skoru 1-3  → fast_track
Karmaşıklık Skoru 4-6  → standard
Karmaşıklık Skoru 7+   → deep
```

---

## Özet

DQG mimarisi şu tasarım ilkelerine dayanır:

1. **Modülerlik:** Her stage bağımsız bir modüldür, değiştirilebilir veya atlanabilir
2. **Konfigürasyon odaklı:** Kod değişikliği olmadan profil, model ve eşik değiştirilebilir
3. **Paralelliğin kapsamlı kullanımı:** I/O-bound LLM çağrıları ThreadPoolExecutor ile paralelleştirilir
4. **Gözlemlenebilirlik:** SSE broadcast, structlog, JSON artifact'lar ile tam izlenebilirlik
5. **Zarif bozulma:** Hatalar sessizce yutulmaz, fallback'ler belirgindir, kısmi sonuçlar korunur
6. **İptal edilebilirlik:** Herhangibir anda kullanıcı pipeline'ı iptal edebilir
7. **Şeffaflık:** LangGraph gibi sihirli framework'ler yerine, okunabilir ve denetlenebilir Python kodu
