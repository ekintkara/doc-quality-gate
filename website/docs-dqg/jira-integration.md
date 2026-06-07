---
sidebar_position: 10
title: Jira Entegrasyonu
---

# Jira Entegrasyonu

## Jira Entegrasyonu Nedir?

Jira entegrasyonu, bir Jira task'ından **otomatik olarak implementasyon dökümanı üretme** ve bu dökümanı DQG kalite süzgecinden geçirme yeteneğidir. Manüel olarak döküman yazmak yerine, Jira'daki task bilgilerini kullanarak bir ilk taslak oluşturulur ve ardından bu taslak DQG pipeline'ı ile analiz edilir.

### Temel Akış

```
Jira Task → Task Analizi → Döküman Üretme → DQG Review → Skor ≥ 8.0 → Döküman Hazır
```

Bu entegrasyon, "from-jira" komutu olarak bilinir ve hem CLI hem de Web API üzerinden kullanılabilir.

---

## From-Jira Akışı

### Genel Bakış

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Jira'dan    │────▶│  Task        │────▶│  Döküman         │
│  Task Okuma  │     │  Analizi     │     │  Üretme (LLM)    │
└──────────────┘     └──────────────┘     └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌──────────────────┐
                                          │  DQG Pipeline    │
                                          │  (Full Review)   │
                                          └────────┬─────────┘
                                                   │
                                           ┌───────┴───────┐
                                           │               │
                                      Skor ≥ 8.0     Skor < 8.0
                                           │               │
                                           ▼               ▼
                                      ┌─────────┐   ┌───────────┐
                                      │ GEÇTİ   │   │ Düzeltme  │
                                      │ Hazır   │   │ Gerekli   │
                                      └─────────┘   └─────┬─────┘
                                                         │
                                                         ▼
                                                   ┌───────────┐
                                                   │ Rescore   │
                                                   │ veya Full │
                                                   └───────────┘
```

### Detaylı Adımlar

1. **Jira'dan Task Okuma** — `JiraReader` ile task bilgileri ve yorumlar çekilir
2. **Task Analizi** — `TaskAnalyzer` ile netlik skoru hesaplanır
3. **Döküman Üretme** — `DocumentGenerator` ile LLM kullanılarak implementasyon planı yazılır
4. **DQG Review** — Üretilen döküman tam DQG pipeline'ından geçirilir
5. **Sonuç Değerlendirme** — Skor 8.0 ve üzeri ise döküman hazır, altında ise düzeltme gerekir

---

## Task Analyzer

Task Analyzer (`task_analyzer.py`), bir Jira task'ının implementasyon dökümanı hazırlamak için ne kadar yeterli olduğunu değerlendirir.

### Jira ADF Açıklaması Parsing

Jira, task açıklamalarını Atlassian Document Format (ADF) olarak saklar. `JiraReader`, ADF formatını düz metne çevirerek task'ın açıklamasını okunabilir hale getirir. Ayrıca şu bilgileri çıkarır:

| Alan | Kaynak |
|------|--------|
| `summary` | Jira issue summary |
| `description` | ADF'den düz metin |
| `acceptance_criteria` | Açıklamadan "Acceptance Criteria" bölümü |
| `impacted_areas` | Açıklamadan "Etkilenen Alanlar" bölümü |
| `target_environment` | Stage/preprod/prod bilgisi |
| `dependencies` | Bağımlılık/blocker bilgisi |
| `labels` | Jira labels |
| `components` | Jira components |
| `priority` | Öncelik seviyesi |
| `assignee` / `reporter` | Atanan ve raporlayan |

### Yorum Okuma ve Harmanlama

Task yorumları, açıklamayı zenginleştirmek için kullanılır:

- AI yorumları (🤖 veya ❓ ile başlayanlar) filtrelenir
- En fazla 10 ilgili yorum eklenir
- Yorumlar, `[Yazar]: İçerik` formatında açıklamaya eklenir

```
Orijinal Açıklama

---

### Yorumlar / Tartışmalar
- [Ahmet]: Backend'de caching eklememiz lazım
- [Ayşe]: Redis kullanabiliriz, hazır bir wrapper var
- [Mehmet]: Load test sonuçlarına göre karar verelim
```

### Netlik Skoru (Clarity Score)

Task netliği 0-10 arasında puanlanır. Değerlendirme iki aşamalıdır:

**Statik Değerlendirme:**

| Alan | Eksikse Puan Kaybı |
|------|---------------------|
| Summary boş | -2.0 |
| Summary < 10 karakter | -1.0 |
| Description boş | -3.0 |
| Description < 50 karakter | -1.5 |
| Acceptance criteria yok | -2.0 |
| Impacted areas yok | -1.0 |
| Target environment yok | -0.5 |
| Dependencies yok | -0.5 |

**LLM Değerlendirmesi:**

Statik puanın üzerine, LLM ile task'ın karmaşıklığı ve netliği değerlendirilir:

```json
{
  "clarity_score": 7.5,
  "missing_fields": ["target_environment"],
  "missing_details": ["target_environment: Hedef ortam belirtilmemiş"],
  "strengths": ["Detaylı acceptance criteria", "Teknik gereksinimler net"],
  "suggested_questions": ["Hedef ortam stage mi preprod mu?"],
  "overall_assessment": "Genel olarak net bir task, hedef ortam eksik"
}
```

### Netlik Durumları (Clarity Status)

| Durum | Skor Aralığı | Anlam |
|-------|-------------|-------|
| `CLEAR` | ≥ 7.0 ve eksik yok | Döküman güvenle üretilebilir |
| `NEEDS_CLARIFICATION` | 4.0 - 6.9 | Bazı bölümler belirsiz, uyarı ile üretilebilir |
| `INSUFFICIENT` | < 4.0 | Task çok belirsiz, üretim önerilmez |

---

## Document Generator

Document Generator (`document_generator.py`), task analizi sonuçlarını kullanarak bir implementasyon planı dökümanı üretir.

### Döküman Şablonu

Üretilen döküman şu bölümleri içerir:

```markdown
# {Task Başlığı}

**Task:** https://obilet.atlassian.net/browse/{TASK_KEY}
**Öncelik:** {priority} | **Durum:** {status}
**Atanan:** {assignee} | **Raporlayan:** {reporter}
**Oluşturulma:** {created_date}

---

## 1. Özet
{summary}

## 2. Arka Plan ve Bağlam
{LLM tarafından üretilir}

## 3. Teknik Gereksinimler
{LLM tarafından üretilir}

## 4. Kabul Kriterleri
{Jira'dan alınır}

## 5. Etkilenen Alanlar
{Jira'dan alınır}

## 6. Uygulama Adımları
{LLM tarafından üretilir}

## 7. Bağımlılıklar ve Engelleyiciler
{Jira'dan alınır}

## 8. Risk Değerlendirmesi
{LLM tarafından üretilir}

## 9. Test Stratejisi
{LLM tarafından üretilir}

## 10. Geri Alma Planı
{LLM tarafından üretilir}

---
*Bu döküman otomatik olarak Doc Quality Gate tarafından Jira task'tan üretilmiştir.*
*Task Analiz Skoru: {clarity_score}/10 | Netlik Durumu: {clarity_status}*
```

### LLM ile İçerik Üretme

Arka plan, teknik gereksinimler, uygulama adımları, risk, test ve geri alma bölümleri LLM tarafından üretilir. Üretim sırasında:

1. **Domain Context Entegrasyonu** — Eğer `--context-path` verilmişse, task ile ilgili domain dosyaları filtrelenir
2. **Spesifik İçerik** — LLM, domain context'teki sınıf isimlerini, API endpoint'lerini ve mimari pattern'leri referans alarak yazar
3. **Fallback** — LLM başarısız olursa, task bilgilerinden basit bir fallback içerik üretilir

### Domain Context Filtreleme

Context dizininde çok sayıda dosya varsa, LLM ile task ile ilgili olanlar filtrelenir:

```python
# Her zaman dahil edilen dosyalar
_ALWAYS_INCLUDE = {"architecture.md", "conventions.md", "common-patterns.md", "api-pipeline.md"}

# Task ile ilgili domain dosyaları LLM ile seçilir
# Örnek: Flight task'ı için flight.md seçilir, hotel.md seçilmez
```

### Netlik Uyarısı

Eğer task netlik durumu `CLEAR` değilse, dökümana bir uyarı eklenir:

```markdown
> **⚠️ Netlik Uyarısı:** Bu task needs_clarification durumunda.
> Analiz Skoru: 5.5/10
> Eksik alanlar: target_environment, dependencies
> Üretilen döküman bu eksiklikleri içerebilir. Tamamlanması önerilir.
```

---

## CLI Kullanımı

### from-jira Komutu

Jira task'ından döküman üretip DQG review çalıştırır (bloklanarak, sonuçlar terminale yazılır):

```powershell
python scripts/dqg_run.py from-jira PDB-11139 --cp C:\OBTaskManager\obiletcontext
```

**Tüm Parametreler:**

| Parametre | Zorunlu | Açıklama |
|-----------|---------|----------|
| `task_key` | Evet | Jira task anahtarı (örn: `PDB-11139`) |
| `--cp` | Hayır | Domain context dizini yolu |
| `--project` | Hayır | Cross-reference için hedef proje yolu |
| `--generate-only` | Hayır | Sadece döküman üret, DQG review atla |

**Örnekler:**

```powershell
# Sadece context ile
python scripts/dqg_run.py from-jira PDB-11139 --cp C:\OBTaskManager\obiletcontext

# Context + proje cross-reference ile
python scripts/dqg_run.py from-jira PDB-11139 \
  --cp C:\OBTaskManager\obiletcontext \
  --project C:\obilet-core-v2

# Sadece döküman üret (DQG review yok)
python scripts/dqg_run.py from-jira PDB-11139 \
  --cp C:\OBTaskManager\obiletcontext \
  --generate-only
```

### launch-from-jira Komutu

Review'ı arka planda başlatır ve hemen geri döner. Sonuçları `poll` komutu ile takip edebilirsiniz:

```powershell
# Başlat
python scripts/dqg_run.py launch-from-jira PDB-11139 --cp C:\OBTaskManager\obiletcontext

# Çıktı: REVIEW_STARTED review_id=abc123def456

# Sonuçları bekle
python scripts/dqg_run.py poll abc123def456
```

### Otomatik Servis Başlatma

Hem `from-jira` hem `launch-from-jira` komutları, gerekli servisleri otomatik olarak başlatır:

1. LiteLLM proxy (`localhost:4000`) — LLM model yönlendirme
2. DQG web server (`localhost:8080`) — API ve web UI

---

## İteratif Döngü

### Score < 8.0 Senaryosu

Jira'dan üretilen döküman ilk çalıştırmada genellikle 6-8 arasında skor alır. Bunun nedenleri:

- LLM'in ürettiği bölümler bazen generic olabilir
- Domain context'teki tüm kurallar tam olarak yansımayabilir
- Cross-reference sorunları tespit edilebilir

### Düzeltme ve Tekrar Çalıştırma

```
1. from-jira → Skor: 6.5/10
2. report.md dosyasını incele
3. Dökümanı düzelt (output dizinindeki dosyayı düzenle)
4. Rescore veya Full Run:

   # Küçük düzeltmeler:
   python scripts/dqg_run.py rescore {review_id}

   # Köklü değişiklikler:
   python scripts/dqg_run.py launch {düzeltilmiş-dosya.md} \
     --project C:\obilet-core-v2 \
     --cp C:\OBTaskManager\obiletcontext
```

### Önerilen İterasyon Sayısı

| İterasyon | Beklenen Skor Artışı | Önerilen Aksiyon |
|-----------|---------------------|-----------------|
| İlk üretim | 5.0 - 7.5 | Report.md'yi incele |
| 1. düzeltme | +1.0 - +2.0 | Rescore |
| 2. düzeltme | +0.5 - +1.0 | Rescore |
| 3. düzeltme | +0.0 - +0.5 | Full run yapmayı düşün |

> **İpucu:** 3 iterasyondan sonra hâlâ 8.0 altındaysa, dökümanı kökten yeniden yazmayı düşünün. Çoğu durumda domain context ile ilk üretim yeterli kalitededir.

---

## Konfigürasyon

### .env Dosyası

Jira entegrasyonu için `.env` dosyasına şu değişkenler eklenmelidir:

```env
# Jira Bağlantı Bilgileri
DQG_JIRA_BASE_URL=https://obilet.atlassian.net
DQG_JIRA_EMAIL=your.email@obilet.com
DQG_JIRA_API_TOKEN=your-api-token

# Jira Proje Konfigürasyonu
DQG_JIRA_PROJECT=PDB

# Varsayılan Domain Context Yolu
DQG_JIRA_DEFAULT_CONTEXT_PATH=C:\OBTaskManager\obiletcontext
```

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `DQG_JIRA_BASE_URL` | Evet | Jira instance URL'si |
| `DQG_JIRA_EMAIL` | Evet | Jira kullanıcı e-postası |
| `DQG_JIRA_API_TOKEN` | Evet | Jira API token (Settings > Security > API tokens) |
| `DQG_JIRA_PROJECT` | Hayır | Varsayılan proje anahtarı |
| `DQG_JIRA_DEFAULT_CONTEXT_PATH` | Hayır | `--cp` belirtilmezse kullanılacak context yolu |

### API Token Alma

1. `https://id.atlassian.com/manage-profile/security/api-tokens` adresine gidin
2. "Create API token" butonuna tıklayın
3. Token'ı kopyalayıp `.env` dosyasına yapıştırın

### Web API

Jira entegrasyonu Web API üzerinden de kullanılabilir:

**POST /api/review/from-jira**

```json
{
  "task_key": "PDB-11139",
  "context_path": "C:\\OBTaskManager\\obiletcontext",
  "project_path": "C:\\obilet-core-v2",
  "generate_only": false
}
```

| Alan | Zorunlu | Açıklama |
|------|---------|----------|
| `task_key` | Evet | Jira task anahtarı |
| `context_path` | Hayır | Domain context dizini |
| `project_path` | Hayır | Cross-reference için proje yolu |
| `generate_only` | Hayır | Sadece üretim, review yok (varsayılan: false) |

**Response:**

```json
{
  "review_id": "abc123def456",
  "status": "queued"
}
```

Durum takibi: `GET /api/review/status/{review_id}`

---

## Troubleshooting

### "Jira credentials not configured"

`.env` dosyasında `DQG_JIRA_EMAIL` ve `DQG_JIRA_API_TOKEN` değerlerini kontrol edin.

### "Could not fetch Jira issue"

- Task anahtarının doğru yazıldığından emin olun (örn: `PDB-11139`)
- API token'ın geçerli olduğunu doğrulayın
- Jira projesine erişim izniniz olduğunu kontrol edin

### "Domain context empty"

- `--cp` parametresiyle verilen dizinde `.md` dosyaları olduğundan emin olun
- `DQG_JIRA_DEFAULT_CONTEXT_PATH` ayarının doğru yolu gösterdiğini kontrol edin

### Üretilen Döküman Generic

- Domain context dosyalarının yeterince spesifik olduğundan emin olun
- `architecture.md` ve `conventions.md` dosyalarının güncel olduğunu kontrol edin
- `--project` parametresiyle proje yolu vererek cross-reference'i aktive edin
