---
sidebar_position: 16
title: Hizli Baslangic
---

# Hızlı Başlangıç

## DQG'yi 5 Dakikada Ayağa Kaldırın

Bu rehber, DQG'yi sıfırdan kurup ilk review'unuzu çalıştırmanız için adım adım bir kılavuzdur.

---

## 1. Ön Koşullar

Başlamadan önce sisteminizde şu yazılımların kurulu olduğundan emin olun:

| Gereksinim | Minimum Versiyon | Kontrol Komutu |
|-----------|-----------------|----------------|
| Python | 3.10+ | `python --version` |
| Git | 2.0+ | `git --version` |
| pip | En son | `pip --version` |

### API Anahtarı

DQG, LLM çağrıları için bir **Z.ai API anahtarına** ihtiyaç duyar. Başlamadan önce API anahtarınızı temin edin.

---

## 2. Kurulum

### Adım 1: Repoyu Klonlayın

```bash
git clone <repo-url> doc-quality-gate
cd doc-quality-gate
```

### Adım 2: Virtual Environment Oluşturun

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### Adım 3: Bağımlılıkları Kurun

```bash
pip install -r requirements.txt
```

### Adım 4: `.env` Dosyasını Yapılandırın

```bash
# .env dosyasını oluşturun
cp .env.example .env   # veya manuel oluşturun
```

`.env` dosyasını düzenleyin:

```env
ZAI_API_KEY=your-zai-api-key-here
LITELLM_MASTER_KEY=your-master-key-here
```

**Zorunlu değişkenler:**

| Değişken | Açıklama |
|----------|----------|
| `ZAI_API_KEY` | Z.ai platform API anahtarı |
| `LITELLM_MASTER_KEY` | LiteLLM proxy yönetici anahtarı (herhangi bir UUID olabilir) |

### Adım 5: Otomatik Kurulum (Opsiyonel)

Platformunuza özel setup betiğini çalıştırarak bağımlılık kurulumu, `.env` yapılandırması ve proxy başlatma işlemlerini otomatik yapabilirsiniz:

| Platform | Komut |
|----------|-------|
| Windows | `powershell -File scripts/win/setup.ps1` |
| macOS | `bash scripts/mac/setup.sh` |
| Linux | `bash scripts/linux/setup.sh` |

---

## 3. İlk Çalıştırma

### Servisleri Ayağa Kaldırma

DQG, iki arka plan servisine ihtiyaç duyar:

1. **LiteLLM Proxy** (port 4000) — LLM çağrılarını yönetir
2. **Web Server** (port 8080) — Dashboard'u sunar

Bu servisler ilk review komutunuzda **otomatik olarak başlatılır**. Manuel kontrol:

```bash
# Proxy durumunu kontrol et
python scripts/dqg_run.py check-proxy
# Çıktı: PROXY_OK veya PROXY_DOWN
```

### Servislerin Başlatılmasını Bekleyin

İlk çalıştırmada proxy'nin hazır olması 10-30 saniye sürebilir. Çıktıyı izleyin:

```
Starting LiteLLM proxy...
PROXY_READY
Starting DQG web server...
WEB_READY
WEB_UI_OPENED http://localhost:8080
```

Tarayıcınız otomatik olarak `http://localhost:8080` adresine açılacaktır.

---

## 4. Basit Bir Review

### Adım 1: Test Dokümanı Oluşturun

Bir implementasyon planı oluşturun:

```bash
# Örnek bir doküman oluşturun
```
cat > my-feature.md \<\< 'EOF'
```
# Kullanıcı Profil Sayfası Yenileme

## Amaç
Mevcut kullanıcı profil sayfasını modern bir tasarıma güncellemek.

## Değişiklikler
1. Profil fotoğrafı yükleme özelliği eklenecek
2. Kullanıcı bilgileri düzenlenebilir hale getirilecek
3. Şifre değiştirme modülü eklenecek

## Teknik Detaylar
- Frontend: React bileşenleri kullanılacak
- Backend: REST API endpoint'leri oluşturulacak
- Veritabanı: users tablosuna yeni alanlar eklenecek

## API Endpoint'leri
- GET /api/v1/users/{id}/profile
- PUT /api/v1/users/{id}/profile
- POST /api/v1/users/{id}/avatar

## Test Planı
- Unit testler yazılacak
- Integration testler yapılacak
EOF
```

### Adım 2: Review'u Başlatın

```bash
# Hızlı başlat + sonuçları bekle
python scripts/dqg_run.py auto-review my-feature.md --project C:\my-project
```

**Alternatif — Arka planda başlat:**

```bash
# Başlat
python scripts/dqg_run.py launch my-feature.md --project C:\my-project

# Sonuçları bekle
python scripts/dqg_run.py poll <review_id>
```

### Adım 3: Dashboard'da İzleyin

`http://localhost:8080` adresinde dashboard'u açın. Pipeline'ın aşama aşama ilerlemesini göreceksiniz:

```
✓ Ingest               0.5s
✓ Domain Context        30s
▶ Cross-Reference       çalışıyor...
○ Critic A              bekliyor
○ Critic B              bekliyor
○ Score                 bekliyor
```

### Adım 4: Sonuçları Okuyun

Terminalde veya dashboard'da sonuçları göreceksiniz:

```
REVIEW_COMPLETE
SCORE: 6.2/10 | FAIL | Action: revise_and_resubmit

CROSS_REF_ISSUES (2):
  - [critical] PUT /api/v1/users/{id}/profile endpoint'i zaten mevcut
  - [high] users tablosunda avatar_url alanı tanımlı

QUALITY_ISSUES (4):
  - [critical] Rollback stratejisi belirtilmemiş
  - [high] Fotoğraf yükleme için dosya boyutu limiti tanımlanmamış
  - [medium] Rate limiting politikası eksik
  - [medium] Error handling detayları yetersiz

DIMENSION_SCORES:
  correctness: 7.0
  completeness: 5.5
  implementability: 7.0
  consistency: 6.5
  edge_case_coverage: 4.0
  testability: 6.0
  risk_awareness: 5.0
  clarity: 7.5
```

---

## 5. Jira'dan Review

Jira entegrasyonu ile bir task'tan otomatik doküman üretip review yapabilirsiniz.

### Ön Koşul: Jira Değişkenleri

`.env` dosyasına Jira değişkenlerini ekleyin:

```env
DQG_JIRA_BASE_URL=https://your-domain.atlassian.net
DQG_JIRA_EMAIL=your.email@domain.com
DQG_JIRA_API_TOKEN=your-jira-api-token
DQG_JIRA_PROJECT=YOUR_PROJECT_KEY
DQG_JIRA_DEFAULT_CONTEXT_PATH=C:\path\to\context
```

### Jira Task'tan Review

```bash
# Bloklayıcı — sonuçları bekler
python scripts/dqg_run.py from-jira PDB-11139 --cp C:\context

# Veya arka planda başlat
python scripts/dqg_run.py launch-from-jira PDB-11139 --cp C:\context
python scripts/dqg_run.py poll <review_id>
```

### Jira Akışı

```
Jira Task (PDB-11139)
    │
    ├── 1. Task okunur
    │   ├── ADF açıklaması parse edilir
    │   └── Yorumlar alınır
    │
    ├── 2. Task analizi
    │   ├── Clarity score hesaplanır
    │   └── Eksik alanlar tespit edilir
    │
    ├── 3. Doküman üretimi
    │   └── LLM ile implementasyon planı oluşturulur
    │
    ├── 4. DQG pipeline
    │   ├── Cross-reference
    │   ├── Multi-critic
    │   ├── Validation
    │   └── Scoring
    │
    └── 5. Sonuçlar
        ├── Score >= 8.0 → Doküman hazır
        └── Score < 8.0 → Düzeltme gerekli
```

---

## 6. Sonuçları Okuma

### Score (Genel Puan)

```
SCORE: 8.5/10 | PASS | Action: proceed
```

| Bileşen | Açıklama |
|---------|----------|
| `8.5/10` | Genel puan — 8.0 ve üzeri geçer |
| `PASS` / `FAIL` | Quality gate kararı |
| `proceed` / `revise_and_resubmit` | Önerilen aksiyon |

### Dimension Scores (Boyut Puanları)

```
DIMENSION_SCORES:
  correctness: 8.2        ← Doğruluk
  completeness: 7.5       ← Tamlık
  implementability: 9.0   ← Uygulanabilirlik
  consistency: 8.8        ← Tutarlılık
  edge_case_coverage: 6.5 ← Uç durum kapsamı
  testability: 7.0        ← Test edilebilirlik
  risk_awareness: 8.0     ← Risk farkındalığı
  clarity: 9.2            ← Netlik
```

| Renk | Aralık | Anlamı |
|------|--------|--------|
| Yeşil | 8.0 - 10.0 | İyi |
| Sarı | 6.0 - 7.9 | Kabul edilebilir |
| Kırmızı | 0.0 - 5.9 | Düzeltilmeli |

### Issues (Sorunlar)

```
CROSS_REF_ISSUES (2):
  - [critical] API endpoint zaten mevcut
  - [high] users tablosunda alan tanımlı

QUALITY_ISSUES (4):
  - [critical] Rollback stratejisi yok
  - [high] Dosya boyutu limiti yok
  - [medium] Rate limiting eksik
  - [low] Error handling detaysız
```

**Severity seviyeleri:**

| Seviye | Renk | Anlamı |
|--------|------|--------|
| `critical` | Kırmızı | Mutlaka düzeltilmeli, bloklayıcı |
| `high` | Turuncu | Yüksek öncelikli, düzeltilmeli |
| `medium` | Sarı | Orta öncelikli, gözden geçirilmeli |
| `low` | Gri | Düşük öncelikli, bilgi amaçlı |

### Çıktı Dosyaları

Her review, `outputs/runs/` dizini altında bir klasöre kaydeder:

```
outputs/runs/20240101_120000_a1b2c3d4/
├── metadata.json        ← Çalışma meta verileri
├── original.md          ← Orijinal doküman
├── domain_context.md    ← Domain bağlamı
├── domain_analysis.md   ← Domain analizi
├── codebase_context.md  ← Kod tabanı bağlamı
├── issues.json          ← Tespit edilen sorunlar
├── validations.json     ← Sorun doğrulama sonuçları
├── revised.md           ← Düzeltilmiş doküman
├── scorecard.json       ← Skor kartı
├── report.md            ← Markdown rapor
├── report.html          ← HTML rapor
├── fact_check.json      ← Gerçeklik kontrolü (deep profil)
└── fact_check.md        ← Gerçeklik kontrolü raporu
```

**Raporu görüntüleme:**

```bash
# Terminalde
python scripts/dqg_run.py report

# Dashboard'da
# http://localhost:8080/runs → çalışmaya tıkla → Full Report
```

---

## 7. Sonraki Adımlar

### Pipeline Profillerini Keşfedin

DQG üç farklı derinlik seviyesi sunar:

```bash
# Hızlı — küçük değişiklikler (~90sn)
# config/pipeline_profiles.yaml → fast_track

# Standart — dengeli (~175sn)
# config/pipeline_profiles.yaml → standard

# Derin — tam analiz (~600sn)
# config/pipeline_profiles.yaml → deep
```

Detaylar için: [Konfigürasyon](15-configuration.md)

### Rescore ile Hızlı Yeniden Değerlendirme

Dokümanınızı düzelttikten sonra tam pipeline yerine sadece skorlama çalıştırın:

```bash
# Önceki review'dan düzeltilmiş dosyayla rescore
python scripts/dqg_run.py rescore <review_id> --revised docs/plan_v2.md

# Sonuçları bekle
python scripts/dqg_run.py poll <new_review_id>
```

Detaylar için: [Rescore Modu](08-rescore-mode.md)

### Simulator ile Optimizasyon

Pipeline'ın farklı konfigürasyonlardaki tahmini süresini ve kalite güvenirliğini karşılaştırın:

```
http://localhost:8080/simulator
```

Detaylar için: [Simulator](07-simulator.md)

### Web Dashboard'u Keşfedin

Dashboard, pipeline'ı gerçek zamanlı izlemenizi sağlar:

- **Live logs** — Pipeline log'larını canlı izleyin
- **LLM çağrıları** — Her LLM çağrısının detayını görün
- **Pipeline çıktıları** — Dosyalar oluştukça anında görüntüleyin
- **Geçmiş çalışmalar** — Tüm review geçmişine erişin

```
http://localhost:8080/dashboard
```

Detaylar için: [Web Dashboard](12-web-dashboard.md)

### CLI Referansı

Tüm komutların detaylı açıklamaları:

Detaylar için: [CLI Referansı](11-cli-reference.md)

---

## Sık Karşılaşılan Sorunlar

### Proxy Başlamıyor

```bash
# API key'in doğru olduğunu kontrol edin
cat .env | grep ZAI_API_KEY

# Manuel proxy başlatma ile hata mesajını görün
.venv\Scripts\python.exe -m litellm --config config/litellm/config.yaml --port 4000
```

### Virtual Environment Bulunamıyor

```bash
# Venv oluşturun
python -m venv .venv

# Aktive edin
.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate    # Linux/macOS

# Bağımlılıkları kurun
pip install -r requirements.txt
```

### Port Çakışması

```bash
# Windows — port kullanan süreçleri bulun
powershell -Command "Get-NetTCPConnection -LocalPort 4000"
powershell -Command "Get-NetTCPConnection -LocalPort 8080"
```
