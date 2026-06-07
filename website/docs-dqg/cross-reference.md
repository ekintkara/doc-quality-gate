---
sidebar_position: 9
title: Cross-Reference
---

# Cross-Reference ve Domain Analizi

## Cross-Reference Nedir?

Cross-reference, bir dokümanı **gerçek kod tabanıyla** karşılaştırarak uyuşmazlıkları, eksik referansları ve mimari uyumsuzlukları tespit eden DQG stage'idir. Bir doküman "API endpoint `/api/users` kullanılacak" dediğinde, bu endpoint'in gerçekten kod tabanında olup olmadığını kontrol eder.

Cross-reference modülü üç ana bileşenden oluşur:

1. **Domain Context Extraction** — Projenin domain kurallarını, mimari kararlarını ve konfigürasyonlarını çıkarır
2. **Cross-Reference Engine** — Dökümanı kod tabanıyla karşılaştırır
3. **Deep Analysis** — Domain violation'ları, mimari uyumsuzlukları ve risk faktörlerini analiz eder

Bu üç bileşen, fan-out paralelizasyonu sayesinde aynı anda çalışır ve toplam süreyi önemli ölçüde azaltır.

---

## Domain Context Extraction

Domain context, projenin teknik bağlamını, mimari kararlarını ve geliştirme standartlarını temsil eden metadır. `domain_context.py` modülü bu bağlamı üç öncelik seviyesinde çıkarır.

### Öncelik Sırası

Domain context çıkarma işlemi şu öncelik sırasına göre çalışır:

**Öncelik 1: Açık Context Yolu (`--context-path`)**

CLI'dan `--context-path` parametresi ile belirtilen dizin. Bu dizin yapılandırılmış domain context dosyaları içerir.

```
C:\projects\my-context\
├── architecture.md
├── conventions.md
├── glossary.md
├── prd.md
├── domain/
│   ├── flight.md
│   ├── hotel.md
│   └── bus.md
├── guides/
│   ├── new-controller.md
│   └── new-service.md
└── infrastructure/
    └── api-pipeline.md
```

Yapılandırılmış dosyalar öncelik sırasına göre yüklenir:
1. `architecture.md` — Mimari kararlar
2. `conventions.md` — Kodlama standartları
3. `glossary.md` — Terimler sözlüğü
4. `prd.md` — Ürün gereksinimleri
5. `domain/`, `guides/`, `infrastructure/` alt dizinleri

**Öncelik 2: Proje İçi `.context/` veya `context/` Dizini**

Eğer `--context-path` verilmezse, proje kök dizininde `.context/`, `context/` veya `docs/` alt dizinlerini arar. En az bir `.md` dosyası içeren ilk dizin kullanılır.

**Öncelik 3: LLM ile Dosya Sınıflandırma**

Proje içindeki tüm `.md` dosyaları taranır ve LLM ile domain'e uygun olup olmadıkları sınıflandırılır:

1. Proje kökünden maksimum 50 `.md` dosyası taranır
2. Dosya adlarındaki anahtar kelimelere göre ön puanlama yapılır (`architecture`, `convention`, `design`, `domain`, vb.)
3. Puanı düşük dosyalar LLM ile sınıflandırılır (maksimum 10 dosya)
4. En yüksek puanlı 5 dosya domain context olarak kullanılır

### Dosya Tarama Kuralları

Tarama sırasında şu dizinler otomatik olarak atlanır:

```
node_modules, .git, .venv, venv, __pycache__, .tox, .mypy_cache,
.pytest_cache, .ruff_cache, dist, build, .next, .nuxt, coverage,
.gradle, target, bin, obj, .idea, .vscode, .vs, vendor, .terraform
```

Maksimum dosya boyutu: 200 KB

### Çıktı Formatı

Domain context çıktısı `domain_context.md` dosyasına yazılır:

```markdown
# Project Domain Context

## architecture.md
[dosya içeriği]

---

## conventions.md
[dosya içeriği]

---
```

Metadata ise `domain_docs.json` dosyasına kaydedilir:

```json
[
  {"source": "context_path", "path": "C:\\projects\\my-context"},
  {"source": "md_scan", "path": "docs/api.md", "pre_score": 3}
]
```

---

## Cross-Reference Engine

Cross-reference engine, doküman içeriğini kod tabanı context'iyle karşılaştırarak uyuşmazlıkları tespit eder.

### Kod Tabanı Tarama (codebase_context.py)

Cross-reference öncesinde, `scan_project()` fonksiyonu hedef projeyi tarar:

**Taranan Bileşenler:**

| Bileşen | Açıklama | Yöntem |
|---------|----------|--------|
| **Dizin Yapısı** | Proje ağacı | `os.walk` ile maksimum 4 derinlik |
| **API Endpoint'ler** | HTTP route'ları | Regex ile FastAPI, Express, Spring, vb. tarama |
| **Veritabanı Modelleri** | DB tabloları ve alanları | ORM class tarama (SQLAlchemy, Prisma, vb.) |
| **Bağımlılıklar** | Kütüphane listeleri | `package.json`, `requirements.txt`, `pyproject.toml` |
| **Konfigürasyon** | Config dosyaları | `.yaml`, `.json`, `.toml`, `.env` dosyaları |
| **Anahtar Dosyalar** | README, Dockerfile, vb. | Glob pattern eşleştirme |

**API Endpoint Tarama Desenleri:**

```python
# FastAPI
@router.get("/api/users") → GET /api/users
app.post("/api/orders")   → POST /api/orders

# Express
router.get("/api/users")  → GET /api/users

# Spring
@GetMapping("/api/users") → GET /api/users
```

**Veritabanı Modeli Tarama:**

```python
class User(Base):           → User modeli
    id: int
    email: str
    name: str

class Order(SQLModel):      → Order modeli
    id: int
    user_id: int
```

### Context String Oluşturma

Taranan bilgiler, LLM prompt'u için yapılandırılmış bir metne dönüştürülür (`build_context_string()`):

```markdown
# Codebase: my-project

## Directory Structure
```
src/
  controllers/
  services/
  models/
  ...
```

## API Routes / Endpoints
- `GET /api/users` — src/controllers/user_controller.py
- `POST /api/orders` — src/controllers/order_controller.py

## Database Models / Schemas
- `User` (src/models/user.py): id, email, name
- `Order` (src/models/order.py): id, user_id, total

## Dependencies
### pip
- fastapi>=0.100.0
- sqlalchemy>=2.0
```

### Cross-Reference LLM Analizi

`run_cross_reference()` fonksiyonu, `config/prompts/cross_reference.md` prompt template'ini kullanarak LLM ile analiz yapar:

1. Kod tabanı context string'i prompt'a eklenir
2. Doküman içeriği ve tipi prompt'a eklenir
3. LLM, doküman ile kod tabanı arasındaki uyuşmazlıkları JSON olarak listeler

**Tespit Edilen Sorun Türleri:**

| Sorun Türü | Örnek |
|-----------|-------|
| Eksik API Endpoint | Döküman `/api/notifications` diyor, kod tabanında yok |
| Eksik Model | Döküman `NotificationLog` modeli diyor, tanımlı değil |
| Eksik Bağımlılık | `redis` gerekli diyor, `requirements.txt`'te yok |
| Uyuşmaz Route | Döküman `POST` diyor, kod tabanında `PUT` |
| Fazladan Özellik | Zaten var olan bir servisi yeniden yazma önerisi |

### Çıktı Formatı

Cross-reference sorunları `cross_ref_issues.json` dosyasına yazılır:

```json
[
  {
    "id": "XR-001",
    "title": "API endpoint not found in codebase",
    "severity": "critical",
    "category": "missing_endpoint",
    "rationale": "Document references POST /api/notifications but no such route exists",
    "evidence_quote": "POST /api/notifications endpoint will be created",
    "affected_section": "Section 3.2",
    "proposed_fix": "Verify endpoint path or add new route definition",
    "source_pass": "cross_ref"
  }
]
```

Kod tabanı context'i `codebase_context.md` dosyasına kaydedilir.

---

## Deep Analysis

Deep analysis, domain context ve codebase context'i birlikte kullanarak derinlemesine analiz yapan stage'dir. `deep_analysis.py` modülü tarafından yürütülür.

### Çalışma Koşulları

Deep analysis sadece şu koşullarda çalışır:

1. Profil'de `deep_analysis` stage'i aktif
2. `domain_context_str` boş değil (domain context bulunmuş olmalı)

Bu, domain context bulunamazsa deep analysis'in anlamlı olmaması nedeniyle tasarlanmıştır.

### Analiz Çıktıları

Deep analysis şu alanları üretir:

**Domain Patterns Found** — Dökümanın doğru takip ettiği pattern'ler:

```json
{
  "domain_patterns_found": [
    "Service layer pattern correctly followed",
    "Repository pattern used for data access"
  ]
}
```

**Domain Violations** — Domain kurallarına aykırı durumlar:

```json
{
  "domain_violations": [
    {
      "rule": "R-003",
      "description": "Direct DB access in controller layer",
      "evidence": "Controller calls User.query() directly",
      "existing_pattern": "Should use UserService layer",
      "severity": "high"
    }
  ]
}
```

**Intentional Patterns** — Domain'e uygun ama şüpheli görünen pattern'ler:

```json
{
  "intentional_patterns": [
    {
      "pattern": "CQRS separation",
      "domain_evidence": "Project uses separate read/write models",
      "confidence": 0.95
    }
  ]
}
```

**Risk Assessment** — Genel risk değerlendirmesi:

```json
{
  "risk_assessment": {
    "overall_risk": "medium",
    "risk_factors": [
      "New table creation required",
      "External API dependency"
    ],
    "critical_paths_affected": [
      "/api/orders",
      "/api/payments"
    ]
  }
}
```

**Existing Infrastructure** — Yeniden kullanılabilecek mevcut altyapı:

```json
{
  "existing_infrastructure": {
    "services": ["UserService", "PaymentService"],
    "repositories": ["UserRepository", "OrderRepository"],
    "middleware": ["AuthMiddleware", "LoggingMiddleware"]
  }
}
```

### Çıktı Dosyaları

| Dosya | İçerik |
|-------|--------|
| `domain_analysis.json` | Ham analiz sonucu (JSON) |
| `domain_analysis.md` | Validator için formatlanmış metin |

`domain_analysis.md` dosyası, sonraki validate stage'inde kullanılmak üzere yapılandırılmış bir formata sahiptir:

```markdown
# Deep Domain Analysis

## Patterns Correctly Followed
- Service layer pattern correctly followed

## Domain Violations (genuine issues)
- **Rule R-003**: Direct DB access in controller layer
  - Evidence: Controller calls User.query() directly
  - Should use: UserService layer

## Intentional Domain Patterns (NOT issues)
- **CQRS separation** (confidence: 0.95)
  - Domain evidence: Project uses separate read/write models

## Risk Assessment
- Overall risk: medium
- Risk factor: New table creation required

## Existing Infrastructure (reusable)
- services: UserService, PaymentService
```

### Early Exit

Deep analysis sonucunda **kritik domain violation'ları** tespit edilirse, pipeline erken durdurulabilir. Bu, `pipeline_profiles.yaml`'daki `early_exit_rules` ile yapılandırılır:

```yaml
early_exit_rules:
  deep_analysis:
    fatal_severities:
      - critical
    min_fatal_count: 2
    abort_message: "Critical architectural violations detected"
```

Eğer 2 veya daha fazla `critical` seviye violation tespit edilirse, pipeline durur ve sonuç raporlanır.

---

## Çıktı Formatları

Cross-reference ve domain analiz sürecinde üretilen tüm dosyalar run dizininde saklanır:

```
outputs/runs/{run_id}/
├── domain_context.md         # Domain context metni
├── domain_docs.json          # Domain context metadata
├── codebase_context.md       # Kod tabanı context metni
├── cross_ref_issues.json     # Cross-reference sorunları
├── domain_analysis.json      # Deep analysis ham sonuç
├── domain_analysis.md        # Deep analysis formatlı metin
└── pipeline_profile.json     # Kullanılan profil bilgisi
```

---

## Gerçek Dünyada Kullanım

### Örnek 1: Eksik API Endpoint

**Dökümanda yazan:**
> `/api/notifications/preferences` endpoint'i üzerinden kullanıcı bildirim tercihleri yönetilecektir.

**Cross-reference sonucu:**
```json
{
  "id": "XR-003",
  "title": "Notification preferences endpoint missing",
  "severity": "critical",
  "category": "missing_endpoint",
  "rationale": "No route matching /api/notifications/preferences found in codebase",
  "proposed_fix": "Either create this endpoint or use existing /api/users/{id}/preferences"
}
```

### Örnek 2: Mimari Uyumsuzluk

**Dökümanda yazan:**
> Controller katmanında doğrudan veritabanı sorguları yazılacaktır.

**Deep analysis sonucu:**
```json
{
  "rule": "R-001",
  "description": "Direct DB access in controller layer violates project architecture",
  "existing_pattern": "Project uses Repository pattern with UserService layer",
  "severity": "high"
}
```

### Örnek 3: Fazladan İş (Redundant Work)

**Dökümanda yazan:**
> Yeni bir `EmailService` sınıfı oluşturulacaktır.

**Cross-reference sonucu:**
```json
{
  "id": "XR-007",
  "title": "EmailService already exists",
  "severity": "medium",
  "category": "redundant_implementation",
  "rationale": "src/services/email_service.py already implements email sending",
  "proposed_fix": "Reuse existing EmailService instead of creating new one"
}
```

### Örnek 4: Domain Context ile Spesifik Tespit

Domain context'te `conventions.md` dosyasında "Tüm API'ler `/api/v2/` prefix'i kullanmalı" kuralı varsa:

**Dökümanda yazan:**
> Yeni endpoint: `POST /users/activate`

**Deep analysis sonucu:**
```json
{
  "rule": "API_VERSIONING",
  "description": "Endpoint missing /api/v2/ prefix per convention",
  "severity": "medium",
  "existing_pattern": "All APIs use /api/v2/ prefix as per conventions.md"
}
```
