---
sidebar_position: 1
title: Genel Bakis
---

# Doc Quality Gate (DQG)

## Kod Yazmadan Önce Dokümanı Doğrula

Yazılım geliştirmede en pahalı hatalar kodda değil, **yanlış tasarım kararlarında** gizlidir. Eksik bir gereksinim, gözden kaçan bir uç durum (edge case) veya mevcut kod tabanıyla çelişen bir mimari öneri — bunların hepsi kod yazmaya başlandıktan sonra keşfedildiğinde onlarca saatlik iş gücüne mal olur.

**Doc Quality Gate (DQG)**, tam bu noktada devreye girer: kod yazılmadan **önce** implementasyon dokümanınızı çok katmanlı bir yapay zeka değerlendirme sürecinden geçirir, sorunları tespit eder ve düzeltilmiş bir doküman üretir.

DQG bir linter değildir. Bir spell-checker değildir. DQG, birden fazla bağımsız LLM eleştirmeninin (critic) dokümanınızı farklı perspektiflerden incelediği, bulgularını kod tabanınızla çapraz doğruladığı (cross-reference), 8 boyutlu bir skorlama sistemiyle nicel bir kalite raporu ürettiği ve nihayetinde bir **quality gate** kararı verdiği bir otomatik inceleme platformudur.

---

## DQG Nedir?

Doc Quality Gate, yazılım implementasyon dokümanlarını (feature spec, implementation plan, architecture change, refactor plan, migration plan, incident action plan vb.) kod yazılmadan önce inceleyen, doğrulayan, düzelten ve skorlayan çok-aşamalı (multi-stage) bir yapay zeka pipeline'ıdır.

### Çözdüğü Problemler

| Problem | DQG'nin Yaklaşımı |
|---------|-------------------|
| Eksik gereksinimler | İki bağımsız critic farklı açılardan dokümanı tarar |
| Mevcut kod tabanıyla tutarsızlıklar | Cross-reference aşaması dokümanı projenin gerçek koduyla karşılaştırır |
| Tek bir AI'ın kör noktaları | Çoklu critic + judge + meta-judge katmanlarıyla denge sağlanır |
| Öznel kalite değerlendirmesi | 8 boyutlu skorlama + Promptfoo rubrik tabanlı değerlendirme |
| Geç keşfedilen tasarım hataları | Early exit ile kritik ihlaller anında tespit edilir |
| Yavaş geri bildirim döngüsü | Paralel fan-out mimarisi ile dakikalar içinde sonuç |

---

## Neden İhtiyaç Var?

### 1. Doküman Kalitesi, Kod Kalitesinin Temelidir

Bir implementasyon dokümanı ne kadar iyi hazırlanmışsa, o dokümandan üretilen kod da o kadar az hatalı olur. DQG, "döküman yaz → kodla → test et → geri dönüp düzelt" döngüsünü "döküman yaz → **DQG ile doğrula** → kodla" akışına dönüştürür.

### 2. Yapay Zeka Destekli Geliştirmede Güvenlik Ağı

AI destekli kod üretim araçları (Copilot, Claude, Cursor vb.) ne kadar güçlü olursa olsun, kendilerine verilen implementasyon dokümanının kalitesine bağlıdır. Hatalı bir doküman, hatalı kod üretir. DQG, AI'ın eline verilen dokümanın kalitesini garanti altına alır.

### 3. Çapraz Doğrulama (Cross-Reference) Kritik

Bir doküman "X servisini oluştur" dediğinde — bu servis projede zaten var mı? Bahsedilen API endpoint'i gerçekten mevcut mu? Önerilen veri modeli mevcut şema ile çelişiyor mu? Bu soruların cevabı ancak kod tabanına bakılarak verilebilir. DQG bunu otomatik yapar.

### 4. Çoklu Perspektif Eksikliği

Tek bir AI reviewcusu her zaman yeterli değildir. Her modelin kör noktaları vardır. DQG, iki farklı modeli (Critic A ve Critic B) farklı bakış açılarıyla devreye sokar:

- **Critic A**: Mantıksal tutarlılık, çelişkiler, eksik gereksinimler, tamamlanmamış mantık, sıralama boşlukları
- **Critic B**: Uygulamaabilirlik, test edilebilirlik, rollout güvenliği, gözlemlenebilirlik, uç durumlar, operasyonel riskler

---

## Nasıl Çalışır?

DQG, bir implementasyon dokümanını birden fazla aşamadan (stage) geçiren bir pipeline mimarisi kullanır. Her aşamanın sorumluluğu nettir ve aşamalar konfigürasyona göre paralel veya sıralı çalışabilir.

### Yüksek Seviye Akış

```
Markdown Doküman
       │
       ▼
┌──────────────────┐
│     INGEST       │  Doküman türünü algıla veya kabul et
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ COMPLEXITY       │  Doküman karmaşıklığını değerlendir
│    ROUTER        │  (minor / standard / major)
└────────┬─────────┘  → Pipeline profili seçilir
         │              (fast_track / standard / deep)
         │
    ┌────┴─────────────────────────────────────┐
    │           FAN-OUT (Paralel)               │
    │  ┌─────────────────┐  ┌─────────────────┐│
    │  │  DOMAIN CONTEXT │  │ CROSS REFERENCE  ││
    │  │  (Alan Bağlamı) │  │ (Kod Tabanı      ││
    │  │                 │  │  Çapraz Kontrol) ││
    │  └─────────────────┘  └─────────────────┘│
    │  ┌─────────────────┐  ┌─────────────────┐│
    │  │   CRITIC A      │  │   CRITIC B       ││
    │  │  (Mantıksal     │  │  (Uygulama       ││
    │  │   İnceleme)     │  │  ebilirlik)      ││
    │  └─────────────────┘  └─────────────────┘│
    └──────────────────┬───────────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  DEEP ANALYSIS   │  Domain bağlamına
              │  (Derin Analiz)  │  karşı mimari ihlal kontrolü
              └────────┬─────────┘
                       │
                  ┌────┴────┐
                  │ EARLY   │  Kritik ihlal varsa?
                  │  EXIT?  │  → "KALDI" + aksiyon planı
                  └────┬────┘
                       │ (devam)
                       ▼
              ┌──────────────────┐
              │ CRITIC JUDGES    │  Her iki critic'in
              │  (Paralel)       │  bulgularını değerlendir
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │    DEDUPE        │  Örtüşen sorunları
              │   (Tekilleştir)  │  birleştir
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │   VALIDATE       │  Her sorunu geçerli /
              │                  │  geçersiz / belirsiz olarak sınıflandır
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │    REVISE        │  Geçerli sorunları
              │                  │  çözerek dokümanı yeniden yaz
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │     SCORE        │  8 boyutta 0-10 arası
              │                  │  çoklu scorer çalışması
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  META JUDGE      │  Skorlama adilliğini
              │                  │  değerlendir, ayarla
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  FACT CHECK      │  Bulguların gerçekliğini
              │                  │  doğrula (onayla / çürüt)
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │    REPORT        │  Markdown + HTML rapor
              │                  │  Skor kartı + Türkçe özet
              └──────────────────┘
```

### Aşama Detayları

#### 1. Ingest (Alım)

Doküman dosyası okunur ve türü algılanır veya kullanıcı tarafından belirtilir. Desteklenen türler:

- `feature_spec` — Yeni özellik spesifikasyonu
- `implementation_plan` — Implementasyon planı
- `architecture_change` — Mimari değişiklik teklifi
- `refactor_plan` — Refaktör planı
- `migration_plan` — Geçiş (migration) planı
- `incident_action_plan` — Olay aksiyon planı
- `custom` — Özel doküman türü

```bash
dqg review doküman.md --type implementation_plan
```

Tür belirtilmezse, DQG doküman içeriğinden otomatik olarak türü tespit eder.

#### 2. Complexity Router (Karmaşıklık Yönlendirici)

Dokümanın karmaşıklığını LLM ile değerlendirir ve uygun pipeline profilini seçer:

| Karmaşıklık | Skor Aralığı | Pipeline Profili | Tahmini Süre |
|-------------|-------------|------------------|-------------|
| Minor (Küçük) | 1-3 | `fast_track` | ~90 saniye |
| Standard (Standart) | 4-6 | `standard` | ~175 saniye |
| Major (Büyük) | 7-10 | `deep` | ~600 saniye |

```bash
# Otomatik yönlendirme
dqg review doküman.md --profile auto

# Manuel profil seçimi
dqg review doküman.md --profile deep
```

#### 3. Fan-Out Paralel Grup

Dört ağır aşama aynı anda çalışır:

- **Domain Context**: Projenin alan bilgisini (domain context) çıkarır — mimari dokümanlar, konvensiyonlar, varlık tanımları
- **Cross Reference**: Dokümanı projenin gerçek kod tabanıyla karşılaştırır — API route'ları, veri modelleri, bağımlılıklar
- **Critic A Multi-Run**: Birden fazla bağımsız çalıştırma ile mantıksal inceleme
- **Critic B Multi-Run**: Birden fazla bağımsız çalıştırma ile uygulanabilirlik incelemesi

#### 4. Deep Analysis (Derin Analiz)

Domain bağlamı ve kod tabanı bağlamını birleştirerek mimari ihlal kontrolü yapar. Kritik ihlaller tespit edilirse pipeline **early exit** ile durdurulur.

#### 5. Early Exit (Erken Çıkış)

Kritik hatalar tespit edildiğinde pipeline'ın tamamını çalıştırmak zaman israfıdır. Early exit mekanizması:

- Cross-reference aşamasında **1+ kritik** sorun → durdur
- Deep analysis aşamasında **2+ kritik** ihlal → durdur

```
⚠️ EARLY EXIT: Fatal cross-reference errors detected (3 fatal issues)
→ Pipeline durduruldu. Aksiyon planı sunuldu.
```

#### 6. Critic Judges + Dedupe

Her iki critic'in bulguları bağımsız judge modelleriyle değerlendirilir, ardından örtüşen sorunlar tekilleştirilir (deduplication).

#### 7. Validation (Doğrulama)

Her sorun üç kategoriden birine sınıflandırılır:

- **Geçerli (Valid)**: Gerçekten düzeltilmesi gereken sorun
- **Geçersiz (Invalid)**: Yanlış pozitif, düzeltme gereksiz
- **Belirsiz (Uncertain)**: Karar verilemeyen durumlar

Sadece geçerli sorunlar revizyon aşamasına aktarılır.

#### 8. Revise (Düzeltme)

LLM, orijinal dokümanı sadece geçerli sorunları çözerek yeniden yazar. Revize edilmiş doküman skorlama için kullanılır.

#### 9. Scoring (Skorlama)

Revize edilmiş doküman **8 boyutta** değerlendirilir:

| Boyut | Açıklama |
|-------|----------|
| **Correctness** (Doğruluk) | Teknik içerik doğru mu? |
| **Completeness** (Tamamlılık) | Tüm gereksinimler kapsanmış mı? |
| **Implementability** (Uygulanabilirlik) | Gerçekten implemente edilebilir mi? |
| **Consistency** (Tutarlılık) | Kendi içinde tutarlı mı? |
| **Edge Case Coverage** (Uç Durum Kapsamı) | Uç durumlar ele alınmış mı? |
| **Testability** (Test Edilebilirlik) | Test stratejisi yeterli mi? |
| **Risk Awareness** (Risk Farkındalığı) | Riskler tanımlanmış mı? |
| **Clarity** (Açıklık) | Anlaşılır ve net mi? |

Skorlama iki bağımsız sistemle gerçekleştirilir:

1. **LLM Scorer** (çoğunluk ağırlık: %60): Birden fazla paralel çalıştırma, medyan skor
2. **Promptfoo Rubrik Scorer** (%40 ağırlık): Yapılandırılmış rubrik tabanlı değerlendirme

Her boyut için ağırlıklar doküman türüne göre özelleştirilir (örneğin migration planlarında `risk_awareness` ağırlığı 1.5x).

#### 10. Meta Judge

Skorlama sonucunun adilliğini değerlendirir:

- **Fair**: Skorlar makul
- **Over-optimistic**: Skorlar fazla iyimser
- **Over-pessimistic**: Skorlar fazla kötümser
- **Needs adjustment**: Ayarlama gerekli

Meta judge, her boyut için maksimum +/-1.5 puan ayarlama yapabilir. Yüksek güvenilirlik (>= %85) ve Promptfoo anlaşması varsa otomatik olarak atlanır.

#### 11. Fact Check

Bulguların gerçekliğini bağımsız bir LLM ile doğrular:

- **Onaylandı (Confirmed)**: Sorun gerçekten var
- **Çürütüldü (Refuted)**: Sorun gerçek dışı (yanlış pozitif)
- **Belirsiz (Uncertain)**: Doğrulanamadı

#### 12. Report (Raporlama)

Nihai çıktılar üretilir:

- `report.md` — Markdown formatında detaylı rapor
- `report.html` — Görselleştirilmiş HTML rapor
- `scorecard.json` — Yapılandırılmış skor kartı
- `metadata.json` — Çalışma meta verileri (süre, token kullanımı, modeller)
- Türkçe özet — Pipeline sonucunun Türkçe kısa özeti

### Gate Karar Mantığı

```
SKOR >= 8.0 ve kritik boyutlar >= 6.0 ve çözülmemiş kritik sorun yok
    → GEÇTİ (implement)
    → Sonraki adım: Kodlamaya başla

SKOR >= 6.0
    → KALDI (revise_again)
    → Sonraki adım: Sorunları düzelt, tekrar çalıştır

SKOR < 6.0
    → KALDI (human_review)
    → Sonraki adım: İnsan incelemesi gerekli
```

---

## Temel Özellikler

### Çoklu Ajan (Multi-Agent) İnceleme

DQG'nin kalbinde **iki bağımsız critic** sistemi yatar:

**Critic A — Mantıksal İnceleme:**
- Çelişkiler (contradictions)
- Hatalı varsayımlar (incorrect assumptions)
- Eksik gereksinimler (missing requirements)
- Tamamlanmamış mantık (incomplete logic)
- Sıralama boşlukları (sequencing gaps)
- Bağımlılık eksiklikleri (dependency gaps)

**Critic B — Uygulamaebilirlik İnceleme:**
- Uygulamaebilirlik (implementability)
- Test edilebilirlik (testability)
- Rollout güvenliği (rollout safety)
- Gözlemlenebilirlik (observability)
- Uç durumlar (edge cases)
- Geçiş riskleri (migration risks)
- Operasyonel riskler (operational risks)
- Bakım kolaylığı (maintainability)

Her critic birden fazla kez çalıştırılır (`critic_runs` parametresi, varsayılan: 2) ve sonuçlar bir judge modeliyle değerlendirilir. Bu, tek bir çalıştırmanın kör noktalarını ortadan kaldırır.

### Kod Tabanı Çapraz Doğrulama (Cross-Reference)

DQG, dokümanınızı projenin gerçek koduyla karşılaştırır:

```
┌─────────────────┐     ┌──────────────────┐
│   DOKÜMAN       │     │   KOD TABANI      │
│                 │     │                  │
│ "X servisini    │ ──→ │ X servisi zaten  │
│  oluştur"       │     │ mevcut!          │
│                 │     │                  │
│ "POST /api/v2/  │ ──→ │ Bu endpoint      │
│  users"         │     │ tanımlı değil    │
└─────────────────┘     └──────────────────┘
```

Tespit edilen sorunlar:
- Mevcut olmayan API endpoint'leri
- Mevcut olmayan veri modelleri
- Eksik bağımlılıklar
- Mimari tutarsızlıklar
- Zaten mevcut olan bileşenler (gereksiz iş)

Kullanım:

```bash
dqg review plan.md --project /path/to/project
```

### 8 Boyutlu Skorlama Sistemi

Her doküman 8 bağımsız boyutta değerlendirilir ve her boyut 0-10 arasında skor alır:

```
┌──────────────────────┬───────┐
│ Correctness          │  8.5  │ ████████░░
│ Completeness         │  7.2  │ ███████░░░
│ Implementability     │  9.0  │ █████████░
│ Consistency          │  8.0  │ ████████░░
│ Edge Case Coverage   │  6.5  │ ██████░░░░
│ Testability          │  7.8  │ ████████░░
│ Risk Awareness       │  8.2  │ ████████░░
│ Clarity              │  9.1  │ █████████░
├──────────────────────┼───────┤
│ GENEL ORTALAMA       │ 8.04  │ GEÇTİ ✓
└──────────────────────┴───────┘
```

Boyut ağırlıkları doküman türüne göre özelleştirilir. Örneğin:

- **Migration Plan**: `risk_awareness` 1.5x, `correctness` 1.5x
- **Incident Action Plan**: `implementability` 1.5x, `risk_awareness` 1.5x
- **Implementation Plan**: `correctness` 1.5x, `completeness` 1.5x, `implementability` 1.5x

### Pipeline Profilleri

DQG, doküman karmaşıklığına göre farklı pipeline derinlikleri sunar:

#### Fast Track (~90 saniye)
Küçük değişiklikler için. Sadece temel inceleme ve skorlama.

```yaml
# fast_track profili
stages: [ingest, validate, revise, score, report]
skip: [domain_context, cross_reference, deep_analysis, critic_a, critic_b, meta_judge, fact_check]
quality_confidence: 0.70
```

#### Standard (~175 saniye)
Dengeli inceleme. Critic'ler ve cross-reference dahil, derin analiz hariç.

```yaml
# standard profili
stages: [ingest, domain_context, cross_reference, critic_a, critic_b, judges, dedupe, validate, revise, score, report]
early_exit: true (cross_reference sonrası)
quality_confidence: 0.92
```

#### Deep (~600 saniye)
Tam 14 aşamalı pipeline. Maksimum kalite güvencesi.

```yaml
# deep profili
stages: [tüm aşamalar]
early_exit: true (cross_reference + deep_analysis sonrası)
quality_confidence: 0.98
```

#### Auto (Otomatik Yönlendirme)

```bash
dqg review plan.md --profile auto
# → Karmaşıklık değerlendirmesi yapılır
# → Uygun profil otomatik seçilir
```

### Karmaşıklık Tabanlı Otomatik Yönlendirme

DQG, dokümanın karmaşıklığını LLM ile analiz eder ve en uygun pipeline profilini otomatik olarak seçer:

```
Doküman → Complexity Router (LLM) → Skor (1-10)
                                          │
                              ┌───────────┼───────────┐
                              │           │           │
                          Skor ≤ 3    4 ≤ Skor ≤ 6   Skor ≥ 7
                              │           │           │
                        fast_track    standard       deep
                        (~90 sn)     (~175 sn)     (~600 sn)
```

### Early Exit (Erken Çıkış)

Kritik hataların erken tespiti ile gereksiz pipeline aşamaları atlanır:

- **Cross-reference sonrası**: 1+ kritik sorun tespit edilirse pipeline durdurulur
- **Deep analysis sonrası**: 2+ kritik mimari ihlal tespit edilirse pipeline durdurulur

Bu özellik, özellikle `standard` ve `deep` profillerinde etkindir.

### Agresif Fan-Out Paralelleştirme

Dört ağır aşama eşzamanlı olarak çalışır:

```
                    Thread Pool (max 4 workers)
                    ┌──────────────────────────┐
                    │  domain_context    │ 30sn │
                    │  cross_reference   │ 33sn │
                    │  critic_a_multi    │ 42sn │──→ max = 42sn
                    │  critic_b_multi    │ 39sn │    (sıralı: 144sn)
                    └──────────────────────────┘
                    %71 zaman tasarrufu
```

`ThreadPoolExecutor` ile paralel çalışır, sıralı yürütmeye göre %50-70 zaman tasarrufu sağlar.

### Rescore Mode (Hızlı Yeniden Çalıştırma)

Bir önceki çalıştırmanın bulgularını yeniden skorlar. Doküman düzeltildikten sonra tüm pipeline'ı tekrar çalıştırmak yerine sadece skorlama aşamasını çalıştırır:

```bash
dqg rescore --previous-run outputs/runs/abc123
```

Web API üzerinden:

```bash
curl -X POST http://localhost:8080/api/review/rescore \
  -H "Content-Type: application/json" \
  -d '{"previous_review_id": "abc123"}'
```

### Gerçek Zamanlı Web Dashboard (SSE)

Pipeline'ın her aşamasını gerçek zamanlı olarak takip edin:

```bash
dqg web --port 8080
```

Dashboard özellikleri:
- **Gerçek zamanlı ilerleme**: Server-Sent Events (SSE) ile anlık güncelleme
- **Aşama durumu**: Her pipeline aşamasının running/done/failed/skipped durumu
- **Canlı log akışı**: Structured log'ların gerçek zamanlı akışı
- **Run geçmişi**: Tüm geçmiş çalıştırmaların listesi ve detayları
- **Skor kartı görselleştirme**: 8 boyutlu skorların interaktif grafiği
- **Model yönetimi**: Model grupları ve routing ayarları
- **Smoke test**: Proxy ve model bağlantı kontrolü
- **Pipeline simülatörü**: Farklı profillerin süre tahminleri

### Jira Entegrasyonu (`from-jira`)

Bir Jira task'ından otomatik olarak implementasyon dokümanı üretin ve DQG analizi yapın:

```bash
dqg from-jira PDB-11139 --cp C:\OBTaskManager\obiletcontext
```

**Jira akışı:**

```
Jira Task (PDB-11139)
       │
       ▼
┌──────────────┐
│  Task Okuma  │  ADF açıklaması parse edilir, yorumlar alınır
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Netlik     │  Task netlik/kalite analizi (clarity score)
│   Analizi    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Doküman    │  LLM ile implementasyon dokümanı üretilir
│   Üretimi    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  DQG Review  │  Full pipeline: critic → validate → score
└──────┬───────┘
       │
       ▼
   Skor >= 8.0? ──→ Evet → Doküman hazır, kodlamaya başla
       │
       Hayır
       │
       ▼
┌──────────────┐
│   Düzeltme   │  Sorunları düzelt, tekrar çalıştır
│   Döngüsü    │  (Score >= 8.0 olana kadar)
└──────────────┘
```

Konfigürasyon:

```env
DQG_JIRA_BASE_URL=https://obilet.atlassian.net
DQG_JIRA_EMAIL=your.email@company.com
DQG_JIRA_API_TOKEN=your-api-token
DQG_JIRA_PROJECT=PDB
DQG_JIRA_DEFAULT_CONTEXT_PATH=C:\path\to\context
```

Sadece doküman üretimi (analiz yok):

```bash
dqg from-jira PDB-11139 --cp C:\context --generate-only
```

### Pipeline Simülatörü

Farklı pipeline profillerinin tahmini sürelerini ve kalite güvenilirliklerini karşılaştırın:

Web UI üzerinden `http://localhost:8080/simulator` veya API üzerinden:

```bash
curl -X POST http://localhost:8080/api/simulator/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "standard",
    "early_exit": true,
    "fan_out": true,
    "pruning": true,
    "has_project": true
  }'
```

### Self-Healing Proxy Yönetimi

LiteLLM proxy otomatik başlatılır ve sağlık kontrolü yapılır:

```bash
# Proxy durumu kontrol et
dqg smoke-test

# Proxy'yi başlat
python scripts/start_proxy.py
```

Proxy yapılandırması (`config/litellm/config.yaml`):

| Model Grubu | Temel Model | Sağlayıcı | Kullanım Amacı |
|-------------|-------------|-----------|----------------|
| `cheap_large_context` | `zai/glm-4.5` | Z.AI | Yüksek token aşamaları (critic, reviser) |
| `cheap_large_context_alt` | `zai/glm-4.5-air` | Z.AI | Alternatif critic perspektifi |
| `strong_judge` | `github/gpt-4o` | GitHub Models | Doğrulama ve skorlama |
| `fallback_general` | `zai/glm-4.5-flash` | Z.AI | Ücretsiz katman yedek |

---

## Kullanım Senaryoları

### Ne Zaman DQG Kullanmalı?

| Senaryo | Öneri |
|---------|-------|
| Yeni bir feature spec yazıyorsanız | Standard veya deep profil |
| Jira task'ından implementasyon planı üretiyorsanız | `from-jira` komutu |
| Mimari bir değişiklik teklif ediyorsanız | Deep profil + cross-reference |
| Basit bir refactor yapıyorsanız | Fast track profili |
| Bir migration planı hazırlıyorsanız | Deep profil (risk_awareness kritik) |
| Bir incident sonrası aksiyon planı yazıyorsanız | Standard profil |
| Dokümanı düzelttikten sonra tekrar kontrol etmek istiyorsanız | Rescore modu |
| AI ile kod üretmeden önce doküman kalitesini garanti etmek istiyorsanız | Her zaman! |

### Tipik İş Akışları

**Yeni Feature Geliştirme:**

```bash
# 1. Implementasyon dokümanını yaz
vim feature-x-plan.md

# 2. DQG ile doğrula
dqg review feature-x-plan.md --project /path/to/project --profile standard

# 3. Skoru kontrol et
# → Skor >= 8.0: Kodlamaya başla
# → Skor < 8.0: Raporu incele, düzelt, tekrar çalıştır
```

**Jira Task'tan Otomatik Üretim:**

```bash
# 1. Jira task'ından doküman üret + analiz
dqg from-jira PDB-12345 --cp /path/to/context --project /path/to/project

# 2. Skor < 8.0 ise düzelt ve tekrar çalıştır
dqg review outputs/jira-PDB-12345-impl-plan.md --cp /path/to/context

# 3. Skor >= 8.0 → doküman hazır
```

**CI/CD Entegrasyonu:**

```bash
# CI pipeline'da kalite kapısı
dqg review docs/implementation-plan.md --profile standard
# Exit code: 0 = geçti, 1 = kaldı
```

---

## Teknoloji Yığını

DQG, şeffaf, denetlenebilir ve "sıkıcı" (boring) teknolojilerle inşa edilmiştir. Özel bir AI framework'ü, LangGraph benzeri bir sistem veya karmaşık bir orkestrasyon katmanı yoktur.

| Teknoloji | Kullanım Amacı |
|-----------|---------------|
| **Python 3.11+** | Ana programlama dili |
| **FastAPI** | Web API ve SSE dashboard |
| **LiteLLM** | Model proxy ve yönlendirme (Z.AI, GitHub Models, Copilot) |
| **Uvicorn** | ASGI sunucusu |
| **Typer + Rich** | CLI arayüzü ve renkli çıktı |
| **Pydantic** | Veri şemaları ve doğrulama |
| **Structlog** | Yapılandırılmış loglama |
| **SSE (Server-Sent Events)** | Gerçek zamanlı dashboard güncellemeleri |
| **ThreadPoolExecutor** | Fan-out paralelleştirme |
| **Promptfoo** | Rubrik tabanlı skorlama |
| **YAML** | Konfigürasyon dosyaları |
| **PyYAML** | YAML ayrıştırma |

### Mimari Prensipler

- **Şeffaflık**: Her aşama bağımsız bir fonksiyon, her çıktı bir JSON/MD dosyası
- **Denetlenebilirlik**: Tüm ara sonuçlar (`issues.json`, `validations.json`, `scorecard.json`) kaydedilir
- **Konfigürasyon odaklı**: Pipeline profilleri, eşik değerleri, model routing — hepsi YAML ile yönetilir
- **Framework'süz**: LangGraph, CrewAI veya benzeri bir framework kullanılmaz. Saf Python + ThreadPoolExecutor
- **Modüler**: Her aşama (`stages/`) bağımsız bir modül, değiştirilebilir ve genişletilebilir

### Proje Yapısı

```
doc-quality-gate/
├── src/app/
│   ├── orchestrator.py          # Ana pipeline orkestratörü
│   ├── config.py                # Konfigürasyon yönetimi
│   ├── schemas.py               # Pydantic veri modelleri
│   ├── cli.py                   # Typer CLI arayüzü
│   ├── stages/                  # Pipeline aşamaları
│   │   ├── ingest.py            # Doküman alımı
│   │   ├── complexity_router.py # Karmaşıklık yönlendirme
│   │   ├── critic.py            # İki bağımsız critic
│   │   ├── critic_judge.py      # Critic değerlendirmesi
│   │   ├── cross_reference.py   # Kod tabanı çapraz kontrol
│   │   ├── deep_analysis.py     # Derin mimari analiz
│   │   ├── dedupe.py            # Tekilleştirme
│   │   ├── validate.py          # Sorun doğrulama
│   │   ├── revise.py            # Doküman düzeltme
│   │   ├── score.py             # 8 boyutlu skorlama
│   │   ├── meta_judge.py        # Meta judge değerlendirmesi
│   │   ├── fact_check.py        # Gerçeklik kontrolü
│   │   ├── domain_context.py    # Domain bağlam çıkarma
│   │   ├── document_generator.py# Jira'dan doküman üretimi
│   │   ├── task_analyzer.py     # Task netlik analizi
│   │   └── report.py            # Rapor üretimi
│   ├── integrations/
│   │   ├── litellm_client.py    # LLM istemcisi
│   │   ├── jira_reader.py       # Jira entegrasyonu
│   │   └── promptfoo_runner.py  # Promptfoo skorlayıcı
│   ├── web/
│   │   ├── app.py               # FastAPI web uygulaması
│   │   └── log_stream.py        # SSE log yayını
│   ├── simulator/               # Pipeline simülatörü
│   └── utils/                   # Yardımcı araçlar
├── config/
│   ├── app.yaml                 # Uygulama konfigürasyonu
│   ├── thresholds.yaml          # Eşik değerleri
│   ├── pipeline_profiles.yaml   # Pipeline profilleri
│   ├── model_routing.yaml       # Model yönlendirme
│   ├── litellm/config.yaml      # LiteLLM proxy ayarları
│   └── prompts/                 # LLM prompt şablonları
├── scripts/
│   ├── start_proxy.py           # Proxy başlatma
│   └── dqg_run.py               # Çalıştırma yardımcısı
└── docs/                        # Dokümantasyon
```

---

## Hızlı Başlangıç

```bash
# 1. Repoyu klonla
git clone https://github.com/ekintkara/doc-quailty-gate.git doc-quality-gate
cd doc-quality-gate

# 2. Kurulumu çalıştır
bash scripts/setup.sh          # Linux/macOS
powershell -File scripts/win/setup.ps1   # Windows

# 3. Proxy'yi başlat
python scripts/start_proxy.py

# 4. İlk incelemeyi yap
python -m app.cli review examples/feature_spec/sample.md --type feature_spec

# 5. Web dashboard'u aç
python -m app.cli web
# → http://localhost:8080
```

---

## CLI Referansı

| Komut | Açıklama |
|-------|----------|
| `dqg review <file>` | Full pipeline incelemesi |
| `dqg from-jira KEY` | Jira task'ından doküman üret + analiz |
| `dqg smoke-test` | Proxy ve model bağlantı testi |
| `dqg web` | Web dashboard'u başlat |
| `dqg demo` | Örnek dokümanlarla demo |
| `dqg eval-only <run_id>` | Mevcut run'ı yeniden skorla |
| `dqg fact-check <run_id>` | Bulguların gerçeklik kontrolü |
| `dqg apply-fixes <run_id>` | Onaylanan düzeltmeleri uygula |

### Temel Seçenekler

```bash
dqg review <file> [SEÇENEKLER]

Seçenekler:
  --type, -t         Doküman türü (auto-detected if not specified)
  --project, -p      Proje dizini (cross-reference için)
  --context-path, --cp  Domain bağlam dizini
  --profile          Pipeline profili: fast_track, standard, deep, auto
  --config, -c       Konfigürasyon dizini
```

---

*Doc Quality Gate — Kod yazmadan önce dokümanı doğrula, kaliteyi garanti altına al.*
