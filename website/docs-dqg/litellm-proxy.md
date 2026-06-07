---
sidebar_position: 13
title: LiteLLM Proxy
---

# LiteLLM Proxy

## Model Yönlendirme Katmanı

DQG, LLM çağrılarını yönetmek için **LiteLLM Proxy** kullanır. Proxy, farklı LLM modellerine tek bir API üzerinden erişim sağlar, fallback mekanizmaları sunar ve API anahtarı yönetimini merkezileştirir.

---

## LiteLLM Proxy Nedir?

LiteLLM Proxy, DQG ile LLM sağlayıcıları arasındaki bir **ara katmandır (middleware)**. Pipeline'ın her aşaması doğrudan bir LLM sağlayıcısına çağrı yapmak yerine, LiteLLM proxy'sine çağrı yapar. Proxy, hangi modelin kullanılacağını, hata durumunda hangi fallback modelin devreye gireceğini ve zaman aşımı sürelerini yönetir.

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  DQG Pipeline   │────►│  LiteLLM     │────►│  LLM Sağlayıcı   │
│  Stages         │     │  Proxy       │     │  (Z.ai API)      │
│                 │     │  :4000       │     │                  │
│  critic_a ──────┤     │              │     │  glm-5-turbo     │
│  critic_b ──────┤     │  Model List  │     │  glm-5           │
│  validator ─────┤     │  Router      │     │  glm-5.1         │
│  scorer ────────┤     │  Fallbacks   │     │                  │
│  meta_judge ────┤     │              │     │                  │
└─────────────────┘     └──────────────┘     └──────────────────┘
```

### Temel Faydalar

| Fayda | Açıklama |
|-------|----------|
| **Tek API endpoint** | Tüm modellere `http://localhost:4000` üzerinden erişim |
| **Otomatik fallback** | Bir model hata verirse yedek modele geçiş |
| **Timeout yönetimi** | Uzun süren çağrılar için 300 saniyelik timeout |
| **Retry mekanizması** | Başarısız çağrılar otomatik tekrar denenir (2 kez) |
| **API key merkeziyeti** | API anahtarları tek yerden yönetilir |
| **Model soyutlama** | Pipeline stage'leri model adı yerine grup adı kullanır |

---

## Model Konfigürasyonu

LiteLLM proxy'sinde dört model grubu tanımlıdır:

### Model Grupları

| Grup Adı | Model | Kullanım Amacı |
|----------|-------|---------------|
| `cheap_large_context` | `openai/glm-5-turbo` | Hızlı, düşük maliyetli, büyük context pencereli — Critic A, Critic Judge, Reviser |
| `cheap_large_context_alt` | `openai/glm-5-turbo` | Aynı model, alternatif critic — Critic B |
| `strong_judge` | `openai/glm-5.1` | Güçlü, yüksek kaliteli — Validator, Scorer, Meta-Judge |
| `fallback_general` | `openai/glm-5` | Genel amaçlı yedek — Tüm gruplar için fallback |

### Konfigürasyon Dosyası

Model tanımları `config/litellm/config.yaml` dosyasında yapılır:

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

- model_name: strong_judge
  litellm_params:
    model: openai/glm-5.1
    api_base: https://api.z.ai/api/coding/paas/v4
    api_key: os.environ/ZAI_API_KEY
    headers:
      User-Agent: opencode/1.0.0
      HTTP-Referer: https://opencode.ai/
      X-Title: opencode
  model_info:
    mode: chat
```

### Model Grubu Yapısı

Her model grubu şu alanları içerir:

| Alan | Açıklama |
|------|----------|
| `model_name` | Pipeline stage'lerinin referans verdiği grup adı |
| `litellm_params.model` | Gerçek model tanımlayıcısı (sağlayıcı/model formatında) |
| `litellm_params.api_base` | API endpoint URL'si |
| `litellm_params.api_key` | `os.environ/ZAI_API_KEY` — Ortam değişkeninden okunur |
| `litellm_params.headers` | HTTP header'ları (User-Agent, Referer vb.) |
| `model_info.mode` | Kullanım modu (`chat`) |

---

## API Key Yönetimi

### `.env` Dosyası

API anahtarları `.env` dosyasında saklanır ve proxy başlatılırken yüklenir:

```env
ZAI_API_KEY=your-api-key-here
LITELLM_MASTER_KEY=your-master-key-here
```

| Değişken | Açıklama |
|----------|----------|
| `ZAI_API_KEY` | Z.ai platform API anahtarı — LLM çağrıları için gerekli |
| `LITELLM_MASTER_KEY` | LiteLLM proxy yönetici anahtarı — Proxy API'sine erişim için |

### API Key Yükleme Süreci

```
.env dosyası
    │
    ├── _load_env() fonksiyonu okur
    │   ├── # ile başlayan satırları atlar
    │   ├── = içermeyen satırları atlar
    │   └── os.environ'a ekler (zaten yoksa)
    │
    ├── ZAI_API_KEY → litellm config'de os.environ/ZAI_API_KEY olarak referans
    │
    └── LITELLM_MASTER_KEY → litellm config'de os.environ/LITELLM_MASTER_KEY olarak referans
```

### Güvenlik Notları

- `.env` dosyası asla versiyon kontrolüne (git) eklenmemelidir
- API anahtarları sadece yerel ortamda tutulur
- `litellm_params.api_key` değeri `os.environ/` prefix'i ile ortam değişkenine referans verir

---

## Proxy Başlatma

### `_start_proxy` Fonksiyonu

Proxy, `dqg_run.py` içindeki `_start_proxy` fonksiyonu ile başlatılır. Platforma göre farklı başlatma yöntemleri kullanılır:

#### Windows

```python
subprocess.Popen(
    [venv_py, "-c",
     "from litellm.proxy.proxy_cli import run_server; "
     "run_server(args=['--config', r'" + str(litellm_config) + "', '--port', '4000'])"],
    cwd=str(DQG_ROOT),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    startupinfo=_nt_startup(),
    creationflags=_nt_flags(),
)
```

**Özellikler:**
- `litellm.exe` yerine **Python wrapper** kullanılır — bozuk binary sorunlarını önler
- `CREATE_NO_WINDOW | DETACHED_PROCESS` flag'leri ile arka planda çalışır
- stdout/stderr `DEVNULL`'a yönlendirilir

#### Linux / macOS

```python
subprocess.Popen(
    [venv_py, "-m", "litellm", "--config", str(litellm_config), "--port", "4000"],
    cwd=str(DQG_ROOT),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
```

**Özellikler:**
- `-m litellm` modülü ile başlatılır
- `start_new_session=True` ile ayrı bir process grubunda çalışır

### Ortam Değişkenleri

Proxy başlatılırken şu ortam değişkenleri set edilir:

```python
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
```

### Proxy Hazır Olma Kontrolü

Proxy başlatıldıktan sonra `_wait_for` fonksiyonu ile hazır olma durumu kontrol edilir:

```python
_wait_for(_check_proxy, "PROXY", max_attempts=30, interval=2.0)
```

- Maksimum 30 deneme, her 2 saniyede bir
- Toplam 60 saniyeye kadar bekler
- `http://localhost:4000/health/liveliness` endpoint'ine istek atar

---

## Model Routing — Stage → Model Eşleştirmesi

Pipeline stage'leri doğrudan model adı değil, **model grup adı** kullanır. Eşleştirme `config/app.yaml` içindeki `model_aliases` bölümünde tanımlanır:

```yaml
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
```

### Stage → Model Eşleştirme Tablosu

| Pipeline Stage | Model Alias | Model Grubu | Gerçek Model |
|---------------|-------------|-------------|--------------|
| Critic A (multi) | `critic_a` | `cheap_large_context` | glm-5-turbo |
| Critic B (multi) | `critic_b` | `cheap_large_context_alt` | glm-5-turbo |
| Critic A Judge | `critic_judge` | `cheap_large_context` | glm-5-turbo |
| Critic B Judge | `critic_judge` | `cheap_large_context` | glm-5-turbo |
| Validator | `validator` | `strong_judge` | glm-5.1 |
| Reviser | `reviser` | `cheap_large_context` | glm-5-turbo |
| Scorer | `scorer` | `strong_judge` | glm-5.1 |
| Scorer (Promptfoo) | `scorer_promptfoo` | `fallback_general` | glm-5 |
| Meta-Judge | `meta_judge` | `strong_judge` | glm-5.1 |

### Routing Değiştirme

Model routing'i Web Dashboard → Settings sayfasından veya API üzerinden değiştirilebilir:

```bash
# API üzerinden routing güncelle
curl -X POST http://localhost:8080/api/models/routing \
  -H "Content-Type: application/json" \
  -d '{"routing": {"critic_a": "strong_judge", "validator": "strong_judge"}}'
```

---

## Router Settings

### Fallback Zinciri

Bir model grubu hata verirse, proxy otomatik olarak fallback modele geçer:

```yaml
router_settings:
  fallbacks:
  - cheap_large_context:
    - fallback_general
  - cheap_large_context_alt:
    - fallback_general
  - strong_judge:
    - cheap_large_context
    - fallback_general
```

**Fallback Akışları:**

```
cheap_large_context ──hata──► fallback_general (glm-5)
cheap_large_context_alt ──hata──► fallback_general (glm-5)
strong_judge ──hata──► cheap_large_context (glm-5-turbo) ──hata──► fallback_general (glm-5)
```

### Retry ve Timeout Ayarları

```yaml
router_settings:
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 300
  allowed_fails: 3
```

| Ayar | Değer | Açıklama |
|------|-------|----------|
| `routing_strategy` | `simple-shuffle` | Basit rastgele seçim |
| `num_retries` | 2 | Başarısız çağrı 2 kez tekrar denenir |
| `timeout` | 300 | Çağrı başına 300 saniye (5 dakika) timeout |
| `allowed_fails` | 3 | 3 başarısızlıktan sonra model cooldown'a alınır |

### LiteLLM Genel Ayarları

```yaml
litellm_settings:
  drop_params: true
  num_retries: 2
  request_timeout: 300
  fallbacks:
  - strong_judge:
    - fallback_general
```

| Ayar | Değer | Açıklama |
|------|-------|----------|
| `drop_params` | `true` | Desteklenmeyen parametreleri otomatik çıkar |
| `num_retries` | 2 | Genel retry sayısı |
| `request_timeout` | 300 | İstek timeout süresi |

### Kimlik Doğrulama

```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

Proxy API'sine erişim için `Authorization: Bearer LITELLM_MASTER_KEY` header'ı gereklidir.

---

## Troubleshooting — Yaygın Sorunlar ve Çözümleri

### 1. Proxy Başlamıyor

**Belirti:** `FATAL: LiteLLM proxy could not start`

**Olası Nedenler:**
- `ZAI_API_KEY` tanımlı değil veya geçersiz
- Port 4000 başka bir uygulama tarafından kullanılıyor
- Python virtual environment bozuk

**Çözüm:**

```bash
# API key kontrolü
python scripts/dqg_run.py check-proxy

# Port kontrolü (Windows)
powershell -Command "Get-NetTCPConnection -LocalPort 4000"

# Manuel proxy başlatma
cd C:\repos\doc-quailty-gate
.venv\Scripts\python.exe -m litellm --config config/litellm/config.yaml --port 4000
```

### 2. Proxy Timeout

**Belirti:** LLM çağrıları 300 saniye sonra timeout oluyor

**Çözüm:**
- Doküman boyutunu küçültün
- `config/litellm/config.yaml` dosyasında timeout değerini artırın
- Model değişikliğini düşünün

### 3. Fallback Tetikleniyor

**Belirti:** `strong_judge` modeli yerine `fallback_general` kullanılıyor

**Çözüm:**
- `strong_judge` modelinin API'sine erişilebilir olduğunu kontrol edin
- API kotasını kontrol edin
- `config/litellm/config.yaml` dosyasında `allowed_fails` değerini artırın

### 4. litellm.exe Bozuk (Windows)

**Belirti:** Proxy başlatma komutu çalışmıyor

**Çözüm:** DQG, `litellm.exe` yerine Python wrapper kullanır:

```python
# dqg_run.py Windows'ta bu şekilde başlatır:
subprocess.Popen([venv_py, "-c",
    "from litellm.proxy.proxy_cli import run_server; "
    "run_server(args=['--config', '...'])"])
```

Bu, bozuk binary sorunlarını önler.

### 5. API Key Geçersiz

**Belirti:** `401 Unauthorized` hataları

**Çözüm:**

```bash
# .env dosyasını kontrol edin
cat .env

# API key'in doğru olduğunu test edin
curl -H "Authorization: Bearer YOUR_KEY" https://api.z.ai/api/coding/paas/v4/models
```

### 6. Encoding Sorunları

**Belirti:** Türkçe karakterler bozuk görünüyor

**Çözüm:** Proxy başlatılırken encoding ayarları otomatik yapılır:

```python
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
```

Bu değişkenler `.env` dosyasında değil, proxy başlatma kodunda set edilir.

### 7. Proxy Çalışıyor Ama Dashboard "Down" Gösteriyor

**Belirti:** `check-proxy` → `PROXY_OK` ama dashboard kırmızı nokta

**Çözüm:** Dashboard her 15 saniyede bir `/api/status` endpoint'ini sorgular. Web sunucusunun proxy'ye erişebildiğinden emin olun. `httpx` kütüphanesinin kurulu olduğunu kontrol edin.
