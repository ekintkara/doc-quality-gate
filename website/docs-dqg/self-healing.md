---
sidebar_position: 14
title: Self-Healing
---

# Self-Healing Mekanizması

## Otomatik Hata Tespiti ve Düzeltme

DQG, çalışan servislerin sürekli available olmasını sağlamak için bir **self-healing (kendi kendini onarma)** mekanizmasına sahiptir. Bu mekanizma, servis başlatma sırasında ve her review komutu çalıştırıldığında devreye girer.

---

## Self-Healing Nedir?

DQG iki kritik servise bağlıdır: **LiteLLM Proxy** (port 4000) ve **Web Server** (port 8080). Bu servislerin herhangi bir nedenle çökmesi veya yanıt vermemesi durumunda, DQG otomatik olarak:

1. Sorunu tespit eder (health check ile)
2. Çökmüş süreci temizler (port serbest bırakma)
3. Servisi yeniden başlatır
4. Hazır olana kadar bekler
5. Başarısız olursa kullanıcıya hata bildirir

```
┌───────────────────────────────────────────────────┐
│             Self-Healing Akışı                     │
│                                                    │
│  Kullanıcı Komutu (launch, auto-review, vb.)       │
│       │                                            │
│       ▼                                            │
│  _ensure_services()                                │
│       │                                            │
│       ├── Proxy sağlık kontrolü (_check_proxy)     │
│       │   ├── OK → devam                          │
│       │   └── DOWN → _kill_proxy → _start_proxy    │
│       │                 │                          │
│       │                 └── _wait_for (max 30x2s)  │
│       │                     ├── READY → devam      │
│       │                     └── TIMEOUT → FATAL    │
│       │                                            │
│       └── Web sağlık kontrolü (_check_web)         │
│           ├── OK → devam                          │
│           └── DOWN → _kill_web → _start_web_server │
│                         │                          │
│                         └── _wait_for (max 15x2s)  │
│                             ├── READY → devam      │
│                             └── TIMEOUT → FATAL    │
│                                                    │
│  Servisler hazır → komut çalıştırılır              │
└───────────────────────────────────────────────────┘
```

---

## `_ensure_services` — Çalışan Servisleri Kontrol Et

`_ensure_services` fonksiyonu, servis gerektiren tüm komutlardan önce otomatik olarak çağrılır. Bu fonksiyon iki servisin durumunu kontrol eder ve gerektiğinde başlatır.

### Servis Gerektiren Komutlar

```python
_SERVICE_COMMANDS = {"launch", "launch-from-jira", "auto-review", "from-jira", "review", "start"}
```

Bu komutlardan herhangi biri çalıştırıldığında:

```python
if args.command in _SERVICE_COMMANDS:
    _ensure_services()
```

### `_ensure_services` Akışı

```python
def _ensure_services():
    # 1. Her iki servis çalışıyor mu?
    proxy_up = _check_proxy()
    web_up = _check_web()

    if proxy_up and web_up:
        print("Services already running (proxy + web).")
        return

    # 2. Web sunucusu çalışıyorsa, aktif pipeline'ı iptal et
    if web_up:
        print("Cancelling active pipeline (if any)...")
        _api_post("http://localhost:8080/api/pipeline/cancel", {}, timeout=5)
        time.sleep(1)

    # 3. Proxy çalışmıyorsa başlat
    if not proxy_up:
        print("Starting LiteLLM proxy...")
        _start_proxy()
        if not _wait_for(_check_proxy, "PROXY", max_attempts=30, interval=2.0):
            print("FATAL: LiteLLM proxy could not start.")
            sys.exit(1)

    # 4. Web sunucusu çalışmıyorsa başlat
    if not web_up:
        print("Starting DQG web server...")
        _start_web_server()
        if not _wait_for(_check_web, "WEB", max_attempts=15, interval=2.0):
            print("FATAL: DQG web server could not start.")
            sys.exit(1)

        # 5. Tarayıcıyı otomatik aç
        import webbrowser
        webbrowser.open("http://localhost:8080")
        print("WEB_UI_OPENED http://localhost:8080")
```

### Health Check Fonksiyonları

**Proxy Kontrolü:**

```python
def _check_proxy():
    return _check_url("http://localhost:4000/health/liveliness")
```

**Web Sunucu Kontrolü:**

```python
def _check_web():
    return _check_url("http://localhost:8080/api/status")
```

**Genel URL Kontrolü:**

```python
def _check_url(url):
    try:
        return urlopen(url, timeout=3).status == 200
    except Exception:
        return False
```

Her health check 3 saniyelik timeout ile çalışır. Yanıt alınamazsa servis "down" kabul edilir.

---

## Proxy Recovery — LiteLLM Proxy Kurtarma

### `litellm.exe` Bozuksa Python Wrapper Kullanma

Windows ortamında `litellm.exe` bazen bozuk olabilir veya eksik olabilir. DQG, bu sorunu **Python wrapper** kullanarak çözer:

```python
# Windows'ta direkt litellm.exe yerine Python ile başlatma:
subprocess.Popen(
    [venv_py, "-c",
     "from litellm.proxy.proxy_cli import run_server; "
     "run_server(args=['--config', r'" + str(litellm_config) + "', '--port', '4000'])"],
    ...)
```

**Neden Python wrapper?**

| Sorun | Çözüm |
|-------|-------|
| `litellm.exe` bulunamıyor | Python modül import ile başlatma |
| Binary bozuk veya uyumsuz | Python wrapper her zaman çalışır |
| Versiyon uyumsuzluğu | Virtual environment'daki litellm paketi kullanılır |

### `_kill_proxy` — Çökmüş Proxy'yi Temizle

Proxy yeniden başlatılmadan önce, port 4000'i tutan eski süreçler temizlenir:

**Windows:**

```python
subprocess.run(
    ["powershell", "-Command",
     "Get-NetTCPConnection -LocalPort 4000 -ErrorAction SilentlyContinue | "
     "Select-Object -ExpandProperty OwningProcess | "
     "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
    capture_output=True, timeout=10,
)
```

**Linux / macOS:**

```python
subprocess.run(["pkill", "-f", "litellm.*--port 4000"], capture_output=True, timeout=10)
```

---

## Port Management — Port Yönetimi

DQG iki port kullanır:

### Port 4000 — LiteLLM Proxy

| Özellik | Değer |
|---------|-------|
| Port | 4000 |
| Servis | LiteLLM Proxy |
| Health Endpoint | `GET /health/liveliness` |
| Başlatma | `_start_proxy()` |
| Durdurma | `_kill_proxy()` |
| Timeout | 300 saniye (çağrı başına) |
| Bekleme | Maks. 30 deneme × 2 saniye = 60 saniye |

### Port 8080 — Web Server

| Özellik | Değer |
|---------|-------|
| Port | 8080 |
| Servis | FastAPI (Uvicorn) |
| Health Endpoint | `GET /api/status` |
| Başlatma | `_start_web_server()` |
| Durdurma | `_kill_web_server()` |
| Host | `0.0.0.0` (tüm arayüzler) |
| Bekleme | Maks. 15 deneme × 2 saniye = 30 saniye |

### `_kill_web_server` — Çökmüş Web Sunucusunu Temizle

**Windows:**

```python
subprocess.run(
    ["powershell", "-Command",
     "Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | "
     "Select-Object -ExpandProperty OwningProcess | "
     "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
    capture_output=True, timeout=10,
)
```

### Port Çakışma Senaryoları

| Senaryo | Belirti | Çözüm |
|---------|---------|-------|
| Başka uygulama 4000 kullanıyor | Proxy başlamıyor | Port 4000'i serbest bırakın veya değiştirin |
| Başka uygulama 8080 kullanıyor | Web başlamıyor | Port 8080'i serbest bırakın veya değiştirin |
| Eski DQG süreci hala çalışıyor | Servisler hazır ama yanıt vermiyor | `_kill_proxy` ve `_kill_web_server` otomatik temizler |

---

## `_wait_for` — Hazır Olma Bekleme

Servisler başlatıldıktan sonra hazır olma durumu `_wait_for` fonksiyonu ile poll edilir:

```python
def _wait_for(check_fn, label, max_attempts=30, interval=2.0):
    for i in range(max_attempts):
        if check_fn():
            print(f"{label}_READY")
            return True
        time.sleep(interval)
    print(f"{label}_TIMEOUT")
    return False
```

| Parametre | Proxy | Web |
|-----------|-------|-----|
| `max_attempts` | 30 | 15 |
| `interval` | 2.0 saniye | 2.0 saniye |
| Toplam bekleme | 60 saniye | 30 saniye |
| `check_fn` | `_check_proxy` | `_check_web` |

---

## Hata Senaryoları ve Çözümleri

### Senaryo 1: Proxy Çökmüş, Yeniden Başlatma Gerekli

```
Kullanıcı: python scripts/dqg_run.py launch doc.md
    │
    ├── _ensure_services()
    │   ├── _check_proxy() → False
    │   ├── _kill_proxy() → eski süreç temizlenir
    │   ├── _start_proxy() → yeni süreç başlatılır
    │   ├── _wait_for(_check_proxy, "PROXY") → 30 deneme
    │   │   ├── Deneme 1-3: False (henüz hazır değil)
    │   │   └── Deneme 4: True → "PROXY_READY"
    │   └── _check_web() → True (zaten çalışıyor)
    │
    └── cmd_launch() → review başlatılır
```

### Senaryo 2: Web Sunucusu Çökmüş

```
Kullanıcı: python scripts/dqg_run.py auto-review doc.md
    │
    ├── _ensure_services()
    │   ├── _check_proxy() → True
    │   ├── _check_web() → False
    │   ├── _kill_web_server() → eski süreç temizlenir
    │   ├── _start_web_server() → yeni süreç başlatılır
    │   ├── _wait_for(_check_web, "WEB") → 15 deneme
    │   │   └── True → "WEB_READY"
    │   └── webbrowser.open("http://localhost:8080")
    │
    └── cmd_auto_review() → review başlatılır
```

### Senaryo 3: Her İki Servis de Çökmüş

```
Kullanıcı: python scripts/dqg_run.py from-jira PDB-11139
    │
    ├── _ensure_services()
    │   ├── _check_proxy() → False
    │   ├── _check_web() → False
    │   ├── _kill_proxy() → temizlenir
    │   ├── _start_proxy() → başlatılır
    │   ├── _wait_for(_check_proxy) → PROXY_READY
    │   ├── _kill_web_server() → temizlenir
    │   ├── _start_web_server() → başlatılır
    │   ├── _wait_for(_check_web) → WEB_READY
    │   └── webbrowser.open() → tarayıcı açılır
    │
    └── cmd_from_jira() → Jira review başlatılır
```

### Senaryo 4: Proxy Başlatılamıyor (Kalıcı Hata)

```
Kullanıcı: python scripts/dqg_run.py launch doc.md
    │
    ├── _ensure_services()
    │   ├── _check_proxy() → False
    │   ├── _kill_proxy()
    │   ├── _start_proxy()
    │   ├── _wait_for(_check_proxy, max_attempts=30) → 30 deneme, hepsi başarısız
    │   └── "FATAL: LiteLLM proxy could not start. Check .env for ZAI_API_KEY."
    │
    └── sys.exit(1) → process sonlanır
```

### Senaryo 5: Aktif Pipeline Varken Yeni Review

```
Kullanıcı: python scripts/dqg_run.py launch doc2.md
    │
    ├── _ensure_services()
    │   ├── _check_proxy() → True
    │   ├── _check_web() → True
    │   ├── "Cancelling active pipeline (if any)..."
    │   ├── POST /api/pipeline/cancel → aktif pipeline iptal edilir
    │   └── time.sleep(1) → iptal işleminin tamamlanması beklenir
    │
    └── cmd_launch() → yeni review başlatılır
```

---

## Servislerin Yaşam Döngüsü

### Başlatma Sırası

```
1. _load_env()          → .env dosyasından ortam değişkenlerini yükle
2. _check_proxy()       → Proxy çalışıyor mu?
3. _check_web()         → Web sunucusu çalışıyor mu?
4. _kill_proxy()        → (gerekirse) Eski proxy sürecini temizle
5. _start_proxy()       → (gerekirse) Yeni proxy süreci başlat
6. _wait_for(proxy)     → Proxy hazır olana kadar bekle
7. _kill_web_server()   → (gerekirse) Eski web sürecini temizle
8. _start_web_server()  → (gerekirse) Yeni web süreci başlat
9. _wait_for(web)       → Web sunucusu hazır olana kadar bekle
10. webbrowser.open()   → Tarayıcıyı aç
11. Komut çalıştır      → Artık servisler hazır
```

### Process Özellikleri

| Servis | Windows Flag | Linux Flag | Detached |
|--------|-------------|------------|----------|
| Proxy | `CREATE_NO_WINDOW \| DETACHED_PROCESS` | `start_new_session=True` | Evet |
| Web | `CREATE_NO_WINDOW \| DETACHED_PROCESS` | `start_new_session=True` | Evet |

Her iki servis de:
- **Daemon process** olarak çalışır (ana process sonlansa bile yaşamaya devam eder)
- **stdout/stderr** proxy'de `DEVNULL`, web'de `outputs/web_server.log` dosyasına yazılır
- **`PYTHONUTF8=1`** ve **`PYTHONIOENCODING=utf-8`** ile Türkçe karakter desteği sağlanır

### `_start_web_server` Detayları

Web sunucusu başlatılırken özel log dosyası oluşturulur:

```python
log_dir = DQG_ROOT / "outputs"
log_dir.mkdir(parents=True, exist_ok=True)
web_log = open(str(log_dir / "web_server.log"), "w", encoding="utf-8")
```

Web sunucusu loglarını incelemek için:

```bash
# Windows
type C:\repos\doc-quality-gate\outputs\web_server.log

# Linux / macOS
cat /path/to/doc-quality-gate/outputs/web_server.log
```
