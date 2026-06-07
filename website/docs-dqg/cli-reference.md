---
sidebar_position: 11
title: CLI Referansi
---

# CLI Referansı

## DQG Komut Satırı Arayüzü

DQG, `scripts/dqg_run.py` üzerinden çalışan ve herhangi bir dizinden çalıştırılabilen bir CLI arayüzüne sahiptir. Tüm komutlar Python standart kütüphanesi kullanılarak yazılmıştır ve ek bağımlılık gerektirmez.

### Çalıştırma Şekli

```bash
python scripts/dqg_run.py <komut> [argümanlar]
```

### Genel Akış

```
┌──────────────────────────────────────────────────┐
│              DQG CLI Komutları                    │
├──────────────────────────────────────────────────┤
│  Servis Gerektiren Komutlar                      │
│  ├── auto-review    (tam otomatik)               │
│  ├── launch         (async başlat)               │
│  ├── launch-from-jira  (async Jira)              │
│  ├── from-jira      (bloklayıcı Jira)            │
│  ├── start          (legacy detached)             │
│  └── review         (legacy bloklayıcı)           │
│                                                   │
│  Servis Gerektirmeyen Komutlar                    │
│  ├── poll           (sonuç bekle)                │
│  ├── rescore        (hızlı yeniden skorla)       │
│  ├── status         (aktif review durumu)         │
│  ├── report         (son raporu göster)           │
│  ├── check-proxy    (proxy durumu)                │
│  └── locate         (DQG kök dizini)              │
└──────────────────────────────────────────────────┘
```

---

## Servis Yönetimi

### `_ensure_services` — Otomatik Servis Başlatma

`launch`, `auto-review`, `from-jira`, `launch-from-jira`, `start` ve `review` komutları çalıştırılmadan önce `_ensure_services` otomatik olarak çağrılır. Bu fonksiyon:

1. LiteLLM proxy'sinin (port 4000) çalışıp çalışmadığını kontrol eder
2. Web sunucusunun (port 8080) çalışıp çalışmadığını kontrol eder
3. Çalışmayan servisleri otomatik olarak başlatır
4. Web sunucusu başladığında tarayıcıyı otomatik açar (`http://localhost:8080`)

```
Services already running (proxy + web).    ← İkisi de çalışıyor
Starting LiteLLM proxy...                  ← Proxy başlatılıyor
PROXY_READY                                ← Proxy hazır
Starting DQG web server...                 ← Web sunucusu başlatılıyor
WEB_READY                                  ← Web sunucusu hazır
WEB_UI_OPENED http://localhost:8080        ← Tarayıcı açıldı
```

---

## Komutlar

---

### `launch` — Servisleri Başlat + Async Review Başlat

Servisleri ayağa kaldırır ve bir review sürecini arka planda başlatır. Komut hemen geri döner, review arka planda devam eder. Sonuçları almak için `poll` komutunu kullanın.

**Sözdizimi**

```bash
python scripts/dqg_run.py launch <doc_path> [--project <path>] [--type <type>] [--cp <context_path>]
```

**Parametreler**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `doc_path` | Evet | İncelenecek dokümanın dosya yolu |
| `--project, -p` | Hayır | Cross-reference için hedef proje dizini |
| `--type, -t` | Hayır | Doküman türü: `feature_spec`, `implementation_plan`, `architecture_change`, `refactor_plan`, `migration_plan`, `incident_action_plan`, `custom` |
| `--cp` | Hayır | Domain context dizini yolu. Sağlanmazsa mevcut dizin kullanılır |

**Örnekler**

```bash
# Basit bir review başlat
python scripts/dqg_run.py launch docs/feature.md

# Proje cross-reference ile
python scripts/dqg_run.py launch docs/plan.md --project C:\my-project

# Doküman türü ve context ile
python scripts/dqg_run.py launch docs/spec.md --type implementation_plan --cp C:\context
```

**Çıktı Formatı**

```
DOC_PATH: C:\docs\feature.md
PROJECT_PATH: C:\my-project
CONTEXT_PATH: C:\context
REVIEW_STARTED review_id=a1b2c3d4e5f6
Use: python scripts/dqg_run.py poll a1b2c3d4e5f6
```

---

### `poll` — Review Sonuçlarını Bekle

Arka planda çalışan bir review sürecinin tamamlanmasını bekler ve sonuçları gösterir. Varsayılan olarak 6 deneme yapar (her 10 saniyede bir, ~1 dakika).

**Sözdizimi**

```bash
python scripts/dqg_run.py poll <review_id> [--max-attempts <n>]
```

**Parametreler**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `review_id` | Evet | `launch` veya `launch-from-jira` komutundan alınan review ID |
| `--max-attempts, -n` | Hayır | Maksimum deneme sayısı (varsayılan: 6) |

**Örnekler**

```bash
# Varsayılan deneme ile
python scripts/dqg_run.py poll a1b2c3d4e5f6

# Daha uzun bekleme ile
python scripts/dqg_run.py poll a1b2c3d4e5f6 --max-attempts 120
```

**Çıktı Formatı**

```
STATUS: running (attempt 3/120)
STATUS: running (attempt 4/120)
REVIEW_COMPLETE
SCORE: 8.5/10 | PASS | Action: proceed

CROSS_REF_ISSUES (2):
  - [high] API endpoint /api/v2/users zaten mevcut
  - [medium] UserService sınıfı projede tanımlı

QUALITY_ISSUES (3):
  - [critical] Rollback stratejisi tanımlanmamış
  - [high] Edge case: null değer kontrolü eksik
  - [medium] Test coverage hedefi belirtilmemiş

DIMENSION_SCORES:
  correctness: 8.2
  completeness: 7.5
  implementability: 9.0
  consistency: 8.8
  edge_case_coverage: 6.5
  testability: 7.0
  risk_awareness: 8.0
  clarity: 9.2

REVIEW_ID: a1b2c3d4e5f6
```

**Hata Durumu Çıktısı**

```
REVIEW_FAILED: Proxy connection timeout
```

**Zaman Aşımı Durumu**

```
POLL_INCOMPLETE status=running - run again with same command to continue polling
```

---

### `auto-review` — Başlat + Bekle (Tek Komut)

Servisleri başlatır, review'u arka planda başlatır ve sonuçları bekler. `launch` + `poll` komutlarının birleşik halidir. Çalışan review uzun sürerse zaman aşımına uğrayabilir.

**Sözdizimi**

```bash
python scripts/dqg_run.py auto-review <doc_path> [--project <path>] [--type <type>] [--cp <context_path>]
```

**Parametreler**

`launch` komutuyla aynı parametreler. Dahili olarak `max_attempts=120` ile poll yapar.

**Örnekler**

```bash
# Basit auto-review
python scripts/dqg_run.py auto-review docs/plan.md

# Proje ve context ile
python scripts/dqg_run.py auto-review docs/spec.md --project C:\my-project --cp C:\context
```

**Çıktı Formatı**

Önce `launch` çıktısını, ardından `poll` çıktısını gösterir.

---

### `rescore` — Hızlı Yeniden Skorlama

Önceki bir review'u yalnızca `score` ve `meta_judge` aşamalarını çalıştırarak hızlıca yeniden skorlar. Tüm pipeline'ı tekrar çalıştırmaz.

**Sözdizimi**

```bash
python scripts/dqg_run.py rescore <review_id> [--revised <file_path>]
```

**Parametreler**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `review_id` | Evet | Yeniden skorlanacak önceki review ID |
| `--revised` | Hayır | Düzeltilmiş doküman yolu. Belirtilmezse önceki review'daki `revised.md` kullanılır |

**Örnekler**

```bash
# Önceki review'u aynı dosyayla yeniden skorla
python scripts/dqg_run.py rescore a1b2c3d4e5f6

# Düzeltilmiş dosyayla yeniden skorla
python scripts/dqg_run.py rescore a1b2c3d4e5f6 --revised docs/plan_v2.md
```

**Çıktı Formatı**

```
RESCORE_STARTED review_id=f6e5d4c3b2a1 from=a1b2c3d4e5f6
Use: python scripts/dqg_run.py poll f6e5d4c3b2a1
```

---

### `from-jira` — Jira Task'tan Doküman Üret + Review (Bloklayıcı)

Bir Jira task'ından otomatik implementasyon dokümanı üretir ve DQG review pipeline'ını çalıştırır. Süreç tamamlanana kadar komut bekler.

**Sözdizimi**

```bash
python scripts/dqg_run.py from-jira <task_key> [--cp <context_path>] [--project <path>] [--generate-only]
```

**Parametreler**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `task_key` | Evet | Jira task anahtarı (örn. `PDB-11139`) |
| `--cp` | Hayır | Domain context dizini yolu. Sağlanmazsa `.env` dosyasındaki `DQG_JIRA_DEFAULT_CONTEXT_PATH` kullanılır |
| `--project, -p` | Hayır | Cross-reference için hedef proje dizini |
| `--generate-only` | Hayır | Sadece doküman üret, DQG review yapma |

**Örnekler**

```bash
# Jira task'tan review yap
python scripts/dqg_run.py from-jira PDB-11139

# Context ve proje ile
python scripts/dqg_run.py from-jira PDB-11139 --cp C:\context --project C:\my-project

# Sadece doküman üret
python scripts/dqg_run.py from-jira PDB-11139 --generate-only
```

**Çıktı Formatı**

```
JIRA_TASK: PDB-11139
CONTEXT_PATH: C:\context
PROJECT_PATH: C:\my-project
REVIEW_ID: a1b2c3d4e5f6
STATUS: running (attempt 5/200)
...
REVIEW_COMPLETE
SCORE: 7.2/10 | FAIL | Action: revise_and_resubmit
```

**Jira Akışı**

```
Jira Task
    │
    ├── 1. Task okunur (ADF açıklaması parse edilir, yorumlar alınır)
    ├── 2. Task netlik/kalite analizi yapılır (clarity score)
    ├── 3. LLM ile implementasyon dokümanı üretilir
    ├── 4. DQG pipeline'ı çalışır (critic → validate → score)
    ├── 5. Score < 8.0 ise düzeltme aksiyon planı sunulur
    └── 6. Sonuçlar gösterilir
```

---

### `launch-from-jira` — Jira Task'tan Async Review Başlat

`from-jira` ile aynı işlemi yapar ancak bloklayıcı değildir. Review'u arka planda başlatır ve hemen geri döner.

**Sözdizimi**

```bash
python scripts/dqg_run.py launch-from-jira <task_key> [--cp <context_path>] [--project <path>] [--generate-only]
```

**Parametreler**

`from-jira` ile aynı.

**Örnekler**

```bash
python scripts/dqg_run.py launch-from-jira PDB-11139 --cp C:\context
```

**Çıktı Formatı**

```
JIRA_TASK: PDB-11139
CONTEXT_PATH: C:\context
REVIEW_STARTED review_id=a1b2c3d4e5f6
Use: python scripts/dqg_run.py poll a1b2c3d4e5f6
```

---

### `start` — Legacy Detached Review

Review sürecini arka planda ayrı bir process olarak başlatır. Yeni projelerde `launch` komutu tercih edilmelidir.

**Sözdizimi**

```bash
python scripts/dqg_run.py start <doc_path> --project <path> [--type <type>] [--cp <context_path>]
```

**Parametreler**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `doc_path` | Evet | İncelenecek dokümanın dosya yolu |
| `--project, -p` | Evet | Hedef proje dizini |
| `--type, -t` | Hayır | Doküman türü |
| `--cp` | Hayır | Domain context dizini yolu |

**Örnekler**

```bash
python scripts/dqg_run.py start docs/plan.md --project C:\my-project
```

**Çıktı Formatı**

```
REVIEW_STARTED
PID: 12345
Run ID: abc123def456
```

---

### `status` — Aktif Review Durumu

Son başlatılan review sürecinin durumunu kontrol eder. Marker dosyası (`outputs/.active_review`) üzerinden takip eder.

**Sözdizimi**

```bash
python scripts/dqg_run.py status
```

**Parametreler**

Parametre almaz.

**Örnekler**

```bash
python scripts/dqg_run.py status
```

**Çıktı Formatları**

```
# Çalışıyor
RUNNING
PID: 12345

# Tamamlandı
COMPLETE
Run: 20240101_120000_a1b2
Score: 8.5/10 | PASS

# Başarısız
FAILED

# Aktif review yok
NO_ACTIVE_REVIEW
```

---

### `report` — Son Raporu Göster

En son tamamlanan review'un Markdown raporunu terminale yazdırır.

**Sözdizimi**

```bash
python scripts/dqg_run.py report
```

**Parametreler**

Parametre almaz.

**Örnekler**

```bash
python scripts/dqg_run.py report
```

**Çıktı Formatı**

Markdown formatında rapor içeriği. Rapor yoksa:

```
No report found.
```

---

### `check-proxy` — Proxy Durumunu Kontrol Et

LiteLLM proxy'sinin `http://localhost:4000/health/liveliness` endpoint'ine istek atarak çalışıp çalışmadığını kontrol eder.

**Sözdizimi**

```bash
python scripts/dqg_run.py check-proxy
```

**Parametreler**

Parametre almaz.

**Örnekler**

```bash
python scripts/dqg_run.py check-proxy
```

**Çıktı Formatı**

```
PROXY_OK       # Proxy çalışıyor
PROXY_DOWN     # Proxy çalışmıyor
```

---

### `locate` — DQG Kök Dizinini Göster

DQG projesinin kök dizininin tam yolunu yazdırır. Betiklerin veya entegrasyonların DQG yolunu bulması için kullanılır.

**Sözdizimi**

```bash
python scripts/dqg_run.py locate
```

**Parametreler**

Parametre almaz.

**Örnekler**

```bash
python scripts/dqg_run.py locate
```

**Çıktı Formatı**

```
C:\repos\doc-quailty-gate
```

---

### `review` — Bloklayıcı Review (Legacy)

Review sürecini ön planda çalıştırır. Süreç tamamlanana kadar terminal bloklanır. Yeni projelerde `auto-review` komutu tercih edilmelidir.

**Sözdizimi**

```bash
python scripts/dqg_run.py review <doc_path> --project <path> [--type <type>] [--cp <context_path>]
```

**Parametreler**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `doc_path` | Evet | İncelenecek dokümanın dosya yolu |
| `--project, -p` | Evet | Hedef proje dizini |
| `--type, -t` | Hayır | Doküman türü |
| `--cp` | Hayır | Domain context dizini yolu |

**Örnekler**

```bash
python scripts/dqg_run.py review docs/plan.md --project C:\my-project --type implementation_plan
```

---

## Hata Kodları ve Çözümleri

| Çıktı | Anlamı | Çözüm |
|-------|--------|-------|
| `FATAL: LiteLLM proxy could not start` | Proxy 60 saniye içinde başlayamadı | `.env` dosyasında `ZAI_API_KEY` olup olmadığını kontrol edin |
| `FATAL: DQG web server could not start` | Web sunucusu 30 saniye içinde başlayamadı | Port 8080'in başka bir uygulama tarafından kullanılmadığından emin olun |
| `FATAL: Could not start review` | API çağrısı başarısız oldu | Servislerin çalıştığından emin olun: `check-proxy` |
| `FATAL: No review_id in response` | API beklenmeyen yanıt döndü | Web sunucusu loglarını kontrol edin: `outputs/web_server.log` |
| `POLL_INCOMPLETE` | Zaman aşımı, review hala çalışıyor | `poll` komutunu aynı review_id ile tekrar çalıştırın |
| `REVIEW_FAILED` | Review sırasında hata oluştu | Hata mesajını okuyun ve log dosyalarını inceleyin |

---

## Ortam Değişkenleri

CLI, `.env` dosyasından aşağıdaki değişkenleri otomatik yükler:

| Değişken | Açıklama |
|----------|----------|
| `ZAI_API_KEY` | LLM API anahtarı (LiteLLM proxy için gerekli) |
| `LITELLM_MASTER_KEY` | LiteLLM proxy kimlik doğrulama anahtarı |
| `DQG_JIRA_BASE_URL` | Jira sunucu URL'si (from-jira için) |
| `DQG_JIRA_EMAIL` | Jira kullanıcı e-postası |
| `DQG_JIRA_API_TOKEN` | Jira API token |
| `DQG_JIRA_PROJECT` | Jira proje anahtarı (örn. PDB) |
| `DQG_JIRA_DEFAULT_CONTEXT_PATH` | Varsayılan context dizini yolu |

---

## Platform Notları

### Windows

- `.venv\Scripts\python.exe` kullanılır
- Servisler `CREATE_NO_WINDOW | DETACHED_PROCESS` flag'leriyle başlatılır
- Port yönetimi PowerShell komutlarıyla yapılır

### Linux / macOS

- `.venv/bin/python` kullanılır
- Servisler `start_new_session=True` ile başlatılır
- Port yönetimi `pkill` komutuyla yapılır
