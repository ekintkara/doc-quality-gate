---
sidebar_position: 12
title: Web Dashboard
---

# Web Dashboard

## Gerçek Zamanlı Pipeline İzleme

DQG, pipeline süreçlerini gerçek zamanlı olarak izleyebileceğiniz yerleşik bir web dashboard'a sahiptir. Dashboard, `http://localhost:8080` adresinde çalışır ve SSE (Server-Sent Events) teknolojisi ile anlık güncelleme sağlar.

---

## Web Dashboard Nedir?

DQG Web Dashboard, çalışan bir review pipeline'ını baştan sona izlemenizi sağlayan interaktif bir arayüzdür. Terminal çıktısının aksine, dashboard şu olanakları sunar:

- **Gerçek zamanlı stage takibi** — Her pipeline aşamasının durumunu anında görün
- **Live log akışı** — Pipeline log'larını canlı olarak izleyin, filtreleyin
- **LLM çağrı detayları** — Her LLM çağrısının request/response, token kullanımı ve süresi
- **Pipeline çıktıları** — Üretilen dosyaları (doküman, issues, scorecard vb.) anında görüntüleyin
- **Geçmiş çalışmalar** — Tüm review'ların listesi ve detayları
- **İptal mekanizması** — Çalışan pipeline'ı durdurma butonu

---

## Sayfa Yapısı

Dashboard beş ana bölümden oluşur:

```
┌─────────────────────────────────────────────┐
│  DQG   Dashboard | Runs | Settings | Smoke  │
│                     | Simulator              │
├─────────────────────────────────────────────┤
│  Durum Kartları                              │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│  │Proxy │ │ Web  │ │ Pipe │ │ Son  │       │
│  │ Dur. │ │ Dur. │ │ Dur. │ │ Puan │       │
│  └──────┘ └──────┘ └──────┘ └──────┘       │
├─────────────────────────────────────────────┤
│  Pipeline Stages                             │
│  ✓ Ingest            0.5s                   │
│  ▶ Cross-Reference   çalışıyor...           │
│  ○ Critic A          bekliyor               │
│  ○ Score             bekliyor               │
├─────────────────────────────────────────────┤
│  Pipeline Çıktıları                          │
│  [Task Analiz] [Doküman] [Sorunlar]         │
│  ┌─────────────────────────────────────┐    │
│  │  Dosya içeriği burada gösterilir     │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  Live Logs                                   │
│  14:32:05 INFO  Pipeline başlatıldı          │
│  14:32:12 INFO  Cross-reference tamamlandı   │
│  14:32:15 WARN  2 kritik sorun tespit edildi │
└─────────────────────────────────────────────┘
```

### Navigasyon

| Sayfa | URL | Açıklama |
|-------|-----|----------|
| Dashboard | `/dashboard` veya `/` | Canlı pipeline izleme |
| Çalışmalar | `/runs` | Geçmiş review listesi |
| Çalışma Detayı | `/run/{run_id}` | Tek bir review'un detaylı görünümü |
| Ayarlar | `/settings` | Model ve routing konfigürasyonu |
| Smoke Test | `/smoke` | Sistem sağlık testi |
| Simulator | `/simulator` | Pipeline optimizasyon simülasyonu |

---

## SSE (Server-Sent Events) — Gerçek Zamanlı Güncellemeler

Dashboard'un gerçek zamanlı yeteneği **SSE (Server-Sent Events)** teknolojisine dayanır. SSE, sunucudan tarayıcıya tek yönlü, kalıcı bir bağlantı sağlar.

### SSE Nasıl Çalışır?

```
┌───────────────┐                  ┌──────────────┐
│  DQG Pipeline │                  │   Browser     │
│  (Sunucu)     │                  │  (Dashboard)  │
│               │   SSE Stream     │               │
│  LogBroadcaster├────────────────►│  EventSource  │
│               │  data: {...}     │               │
│               │                  │  → Stage güncelle │
│               │                  │  → Log ekle       │
│               │                  │  → LLM çağrı göster│
└───────────────┘                  └──────────────┘
```

1. Tarayıcı `GET /api/events` endpoint'ine bağlanır
2. Sunucu bir `StreamingResponse` açar (`text/event-stream`)
3. Pipeline çalışırken `LogBroadcaster` her eventi tüm abonelere publish eder
4. Tarayıcı her mesajı alıp DOM'u günceller
5. 30 saniye boyunca mesaj gelmezse keepalive sinyali gönderilir
6. Bağlantı koparsa tarayıcı otomatik yeniden bağlanır

### SSE Endpoint

**`GET /api/events`** — Ana SSE akışı

Tarayıcı tarafında kullanılan kod:

```javascript
var es = new EventSource('/api/events');
es.onmessage = function(e) {
    var m = JSON.parse(e.data);
    // Event tipine göre işle
};
```

### Keepalive Mekanizması

30 saniyelik timeout ile keepalive sinyali gönderilir:

```python
async def event_generator():
    while True:
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=30)
            yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
```

---

## Pipeline Event Türleri

### 1. `pipeline_stage` — Stage Durum Güncellemesi

Bir pipeline aşaması başladığında, tamamlandığında veya hata verdiğinde gönderilir.

```json
{
    "type": "pipeline_stage",
    "run_id": "a1b2c3d4e5f6",
    "stage": "cross_reference",
    "status": "done",
    "detail": "Found 5 issues",
    "duration_ms": 33000,
    "timestamp": 1704612345.678
}
```

| Alan | Açıklama |
|------|----------|
| `stage` | Aşama adı (`ingest`, `cross_reference`, `critic_a_multi`, vb.) |
| `status` | `running`, `done`, `error`, `cancelled` |
| `detail` | Aşama hakkında ek bilgi |
| `duration_ms` | Aşama süresi (ms), sadece `done` ve `error` durumunda |

### 2. `pipeline_done` — Pipeline Tamamlandı

Tüm pipeline tamamlandığında gönderilir.

```json
{
    "type": "pipeline_done",
    "run_id": "a1b2c3d4e5f6",
    "score": 8.5,
    "passed": true,
    "duration_ms": 175000,
    "turkish_summary": "Doküman 8.5/10 puan ile geçti.",
    "timestamp": 1704612520.123
}
```

### 3. `log` — Log Mesajı

Pipeline çalışırken üretilen log mesajları.

```json
{
    "type": "log",
    "level": "info",
    "message": "Cross-reference tamamlandı: 5 sorun bulundu",
    "source": "pipeline",
    "timestamp": 1704612345.678,
    "run_id": "a1b2c3d4e5f6"
}
```

| Level | Anlamı |
|-------|--------|
| `info` | Bilgilendirme |
| `warning` | Uyarı |
| `error` | Hata |
| `debug` | Detaylı bilgi |

### 4. `llm_call` — LLM Çağrı Detayı

Her LLM çağrısı hakkında detaylı bilgi.

```json
{
    "type": "llm_call",
    "stage": "critic_a_multi",
    "model_group": "cheap_large_context",
    "model_used": "openai/glm-5-turbo",
    "request_summary": [
        {"role": "system", "preview": "Sen bir doküman eleştirmenisin..."},
        {"role": "user", "preview": "Şu dokümanı incele..."}
    ],
    "response_preview": "İnceleme sonucu: 3 kritik sorun...",
    "response_length": 5420,
    "tokens_prompt": 3250,
    "tokens_completion": 1800,
    "tokens_total": 5050,
    "duration_ms": 4200,
    "timestamp": 1704612345.678,
    "run_id": "a1b2c3d4e5f6"
}
```

### 5. `setup_step` / `setup_done` — Kurulum Adımları

Sistem kurulumu sırasında gönderilen eventler.

```json
{
    "type": "setup_step",
    "step": "Loading configuration",
    "step_number": 2,
    "total_steps": 7,
    "status": "running",
    "timestamp": 1704612300.0
}
```

---

## Stage Progress — Aşama İlerleme Takibi

Dashboard, tüm pipeline aşamalarının durumunu görsel olarak gösterir. Her aşama bir simge ve renk ile temsil edilir:

| Durum | Simge | Renk | Anlamı |
|-------|-------|------|--------|
| Bekliyor | ○ | Gri | Henüz başlamadı |
| Çalışıyor | ▶ | Mavi (sol border) | Şu anda çalışıyor |
| Tamamlandı | ✓ | Yeşil (sol border) | Başarıyla tamamlandı |
| Hata | ✗ | Kırmızı (sol border) | Hata ile sonlandı |
| İptal | ■ | Kırmızı (sol border) | Kullanıcı tarafından iptal edildi |

### İzlenen Aşamalar

Dashboard şu aşamaları izler:

```
jira_fetch → task_analysis → document_generation → ingest → domain_context →
cross_reference → deep_analysis → critic_a_multi → critic_a_judge →
critic_b_multi → critic_b_judge → dedup → validate → revise → score →
meta_judge → fact_check → report
```

Her aşamanın yanında süresi (ms cinsinden) gösterilir.

---

## Review Status API

### `GET /api/review/status/{review_id}`

Arka planda çalışan bir review'un mevcut durumunu sorgular.

**İstek**

```
GET /api/review/status/a1b2c3d4e5f6
```

**Yanıt (Çalışıyorken)**

```json
{
    "review_id": "a1b2c3d4e5f6",
    "status": "running",
    "result": null,
    "error": null
}
```

**Yanıt (Tamamlandığında)**

```json
{
    "review_id": "a1b2c3d4e5f6",
    "status": "complete",
    "result": {
        "run_id": "a1b2c3d4e5f6",
        "output_dir": "outputs/runs/20240101_120000_a1b2",
        "issues_count": 5,
        "valid_issues": 3,
        "overall_score": 8.5,
        "passed": true,
        "recommended_next_action": "proceed"
    },
    "error": null
}
```

**Yanıt (Hata Durumunda)**

```json
{
    "review_id": "a1b2c3d4e5f6",
    "status": "failed",
    "result": null,
    "error": "Proxy connection timeout"
}
```

**Durum Değerleri**

| Status | Açıklama |
|--------|----------|
| `queued` | Review sıraya alındı, henüz başlamadı |
| `running` | Pipeline çalışıyor |
| `complete` | Başarıyla tamamlandı |
| `failed` | Hata ile sonlandı |
| `cancelled` | Kullanıcı tarafından iptal edildi |

---

## LogBroadcaster — Event Dağıtım Sistemi

`LogBroadcaster` sınıfı, pipeline eventlerinin tüm SSE abonelerine dağıtılmasını sağlar. Singleton pattern ile çalışır.

### Temel Özellikler

- **Maksimum 500 mesajlık history** — Yeni bağlanan istemciler geçmiş mesajları alır
- **Thread-safe publish** — Pipeline thread'inden güvenli publish
- **Queue-based subscriber yönetimi** — Her istemci için ayrıca `asyncio.Queue`
- **HTTP forward** — CLI sürecinden web sunucusuna log iletme

### HTTP Forward Mekanizması

CLI süreci (pipeline worker) ile web sunucusu farklı process'lerde çalışır. LogBroadcaster, pipeline log'larını web sunucusuna HTTP POST ile iletir:

```
CLI Process                     Web Server
    │                              │
    │  LogBroadcaster              │  /api/events/ingest
    │  publish(event)              │
    │  → forward_buffer            │
    │  → 150ms interval            │
    │  POST /api/events/ingest ───►│  broadcaster.publish(event)
    │  {"events": [...]}           │  → SSE abonelerine dağıt
    │                              │
```

---

## Tarayıcıda İzleme — `localhost:8080`

### Servislerin Başlatılması

Dashboard'a erişmek için web sunucusunun çalışıyor olması gerekir. `launch`, `auto-review` veya `from-jira` komutları çalıştırıldığında servisler otomatik başlar.

Manuel kontrol:

```bash
# Proxy durumunu kontrol et
python scripts/dqg_run.py check-proxy

# Tarayıcıda aç
# http://localhost:8080
```

### Dashboard Özellikleri

#### Durum Kartları

Dashboard üst kısmında beş durum kartı bulunur:

| Kart | Açıklama |
|------|----------|
| LiteLLM Proxy | Proxy sağlık durumu (her 15 saniyede güncellenir) |
| Web Server | Web sunucusu durumu |
| Active Pipeline | Çalışan pipeline ID ve durumu |
| Son Puan | Son review puanı (yeşil/kırmızı) |
| Süre | Pipeline çalışma süresi (canlı sayaç) |

#### Log Filtreleme

Log bölümünde filtre seçenekleri:

| Filtre | Açıklama |
|--------|----------|
| All | Tüm logları göster |
| Active Pipeline | Sadece aktif pipeline logları |
| LLM Calls | Sadece LLM çağrı kartları |
| Info+ | Info ve üzeri seviye |
| Warn+ | Warning ve üzeri seviye |
| Error | Sadece hatalar |

#### LLM Çağrı Kartları

Her LLM çağrısı genişletilebilir bir kart olarak gösterilir:

- **Stage** — Hangi pipeline aşamasında çağrıldı
- **Model** — Kullanılan model grubu ve gerçek model
- **Süre** — Çağrı süresi
- **Token** — Prompt, completion ve total token sayısı
- **Request** — Mesaj önizlemesi (genişletilebilir)
- **Response** — Yanıt önizlemesi (genişletilebilir)

---

## Otomatik Açılma

Web sunucusu başarıyla başlatıldığında, tarayıcı otomatik olarak `http://localhost:8080` adresine açılır. Bu davranış `_ensure_services` fonksiyonu içinde `webbrowser.open()` çağrısı ile gerçekleştirilir.

```python
import webbrowser
webbrowser.open("http://localhost:8080")
```

Tarayıcı açıldıktan sonra dashboard gerçek zamanlı olarak pipeline ilerlemesini göstermeye başlar.

---

## API Endpoint'leri Özeti

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/events` | GET (SSE) | Gerçek zamanlı event akışı |
| `/api/events/ingest` | POST | CLI'den event alma |
| `/api/status` | GET | Proxy ve web sunucusu durumu |
| `/api/review/start` | POST | Yeni async review başlat |
| `/api/review/from-jira` | POST | Jira'dan review başlat |
| `/api/review/status/{id}` | GET | Review durumu sorgula |
| `/api/review/rescore` | POST | Rescore başlat |
| `/api/pipeline/cancel` | POST | Pipeline iptal et |
| `/api/runs` | GET | Tüm çalışmaların listesi |
| `/api/runs/{id}` | GET | Çalışma detayı |
| `/api/runs/{id}/files` | GET | Çalışma dosya listesi |
| `/api/runs/{id}/file/{name}` | GET | Tek dosya içeriği |
| `/api/runs/{id}/report` | GET | HTML/Markdown rapor |
| `/api/models` | GET | Model grupları ve routing |
| `/api/models/routing` | POST | Stage routing güncelle |
| `/api/models/group/{name}` | POST | Model grubu güncelle |
