---
sidebar_position: 3
title: Pipeline Stage'leri
---

# Pipeline Aşamaları (Stages)

DQG pipeline'ı, her biri belirli bir sorumluluğu olan 16 aşamadan (stage) oluşur. Aşamalar birbirini ardışık olarak besler ve paralel fan-out grupları sayesinde toplam süre minimize edilir. Bu sayfada her aşamanın amacı, girdisi, işleme mantığı, çıktısı, kullandığı model, ürettiği artifact'ler ve tipik süresi detaylı olarak açıklanmaktadır.

---

## Genel Akış

```
ingest → complexity_router → [domain_context + cross_reference + critic_a_multi + critic_b_multi] (paralel)
      → deep_analysis → [critic_a_judge + critic_b_judge] (paralel)
      → dedupe → validate → revise → score → meta_judge → fact_check → report
```

Köşeli parantez içindeki aşamalar paralel olarak yürütülür (fan-out). Pipeline profiline (`fast_track`, `standard`, `deep`) göre bazı aşamalar atlanabilir.

### Model Alias Sistemi

Her aşama doğrudan bir model adı bilmez; bir **model alias**'ına başvurur. Alias'lar, LiteLLM proxy üzerindeki model gruplarına eşlenir:

| Alias | Model Grubu | Açıklama |
|-------|-------------|----------|
| `critic_a` | `cheap_large_context` | Yüksek token kapasiteli model (critic, xref, deep analysis) |
| `critic_b` | `cheap_large_context_alt` | Farklı perspektif sağlayan alternatif model |
| `critic_judge` | `cheap_large_context` | Critic çıktılarını birleştiren hakem model |
| `validator` | `strong_judge` | Yüksek doğruluk gerektiren yargıç modeli |
| `reviser` | `cheap_large_context` | Doküman revizyon modeli |
| `scorer` | `strong_judge` | 8 boyutlu skorlama modeli |
| `scorer_promptfoo` | `fallback_general` | Promptfoo bağımsız değerlendirmesi |
| `meta_judge` | `strong_judge` | Nihai kalite değerlendirme modeli |

---

## 1. Ingest (Doküman Alımı)

### Amaç

Pipeline'ın giriş noktasıdır. Belirtilen dosyayı okur, içeriğini doğrular ve doküman türünü tespit eder. Pipeline'ın geri kalanı bu aşamanın ürettiği içerik ve tür bilgisiyle çalışır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `file_path` | `str` | İncelenecek dokümanın dosya yolu |
| `doc_type` | `str?` | Opsiyonel; belirtilirse otomatik tespit atlanır |

### İşleme Mantığı

1. Dosyanın varlığı ve okunabilirliği kontrol edilir
2. Dosya UTF-8 kodlamasıyla okunur; boş içerik kontrolü yapılır
3. `doc_type` belirtilmemişse **anahtar kelime tabanlı otomatik tespit** çalışır:
   - Doküman içeriği küçük harfe çevrilir
   - Her doküman türü için tanımlı anahtar kelimeler aranır (ör. "feature", "user story", "acceptance criteria" → `feature_spec`)
   - En yüksek eşleşme skoruna sahip tür seçilir; hiçbir eşleşme yoksa `custom` atanır
4. Dosya adı, tür ve uzunluk bilgisi loglanır

**Desteklenen doküman türleri:**

| Tür | Anahtar Kelimeler |
|-----|-------------------|
| `feature_spec` | feature, user story, specification, requirements, acceptance criteria |
| `implementation_plan` | implementation, plan, milestone, sprint, task breakdown, development plan |
| `architecture_change` | architecture, design, system design, component, refactor architecture, adr |
| `refactor_plan` | refactor, restructure, cleanup, technical debt, code quality |
| `migration_plan` | migration, migrate, data migration, platform migration, cutover |
| `incident_action_plan` | incident, outage, post-mortem, remediation, action plan, sev1, sev2 |
| `custom` | Hiçbir eşleşme yoksa varsayılan |

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `content` | `str` | Dosyanın tam içeriği |
| `resolved_type` | `DocumentType` | Tespit edilen veya belirtilen doküman türü |

### Kullanılan Model

LLM kullanılmaz — tamamen yerel dosya okuma ve anahtar kelime eşleştirmesiyle çalışır.

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `original.md` | Orijinal doküman içeriği |

### Tipik Süre

~0.5 saniye (yerel dosya okuma)

---

## 2. Complexity Router (Karmaşıklık Yönlendirme)

### Amaç

Sadece `profile=auto` seçildiğinde çalışır. Dokümanın karmaşıklığını LLM ile değerlendirir ve uygun pipeline profilini (`fast_track`, `standard`, `deep`) otomatik olarak seçer. Bu sayede basit dokümanlar gereksiz yere uzun bir pipeline'dan geçirilmezken, karmaşık dokümanlar tam derinlemesine analiz alır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `content` | `str` | Ingest aşamasından gelen doküman içeriği (ilk 8000 karakter) |
| `doc_type` | `str` | Tespit edilen doküman türü |

### İşleme Mantığı

1. Doküman içeriğinin ilk 8000 karakteri bir prompt ile LLM'e gönderilir
2. LLM, 1-10 arası bir karmaşıklık skoru ve `minor`/`standard`/`major` seviyesi döndürür:
   - **1-3 (Minor):** Küçük değişiklikler, typo düzeltmeleri, konfigürasyon ayarları, basit UI güncellemeleri. Mimari etkisi yok.
   - **4-6 (Standard):** Özellik eklemeleri, orta ölçekli refactor'lar, yeni endpoint'ler. Bazı mimari değerlendirmeler gerekli.
   - **7-10 (Major):** Mimari değişiklikler, migrasyonlar, breaking change'ler, çoklu servis etkileri. Tam derinlemesine analiz gerekli.
3. `pipeline_profiles.yaml` içindeki eşik değerleri ve profilleme kuralları ile sonuç harmanlanır
4. LLM yanıtı parse edilemezse varsayılan olarak `standard` profili seçilir (graceful fallback)

**Karmaşıklık-Profil Eşleştirmesi:**

| Seviye | Skor Aralığı | Pipeline Profili |
|--------|-------------|------------------|
| Minor | 1-3 | `fast_track` |
| Standard | 4-6 | `standard` |
| Major | 7-10 | `deep` |

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `level` | `ComplexityLevel` | `minor`, `standard` veya `major` |
| `score` | `int` | 1-10 arası karmaşıklık skoru |
| `reasoning` | `str` | LLM'in tek cümlelik açıklaması |
| `profile` | `str` | Seçilen pipeline profili adı |
| `estimated_latency_seconds` | `int` | Tahmini toplam pipeline süresi |

### Kullanılan Model

`critic_a` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `complexity_router.json` | Karmaşıklık sonucu (skor, seviye, profil, gerekçe) |
| `pipeline_profile.json` | Seçilen profil, aktif/atlanan aşamalar, early exit durumu |

### Tipik Süre

~5 saniye (tek LLM çağrısı, düşük token)

---

## 3. Domain Context (Alan Bilgisi Çıkarımı)

### Amaç

Hedef projeye ait alan bilgisi (domain context) çıkarır. Bu bilgi, dokümanın proje standartlarına uygun olup olmadığını değerlendirmek için sonraki aşamalarda (deep_analysis, validate) kullanılır. Projenin mimari kararlarını, isimlendirme kurallarını ve tasarım desenlerini anlamak için gereklidir.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `project_path` | `str` | Hedef projenin kök dizini |
| `document_type` | `str` | Doküman türü |
| `context_path` | `str?` | Opsiyonel; açıkça belirtilen context dizini (`--cp` parametresi) |

### İşleme Mantığı

Üç öncelikli kaynak sırasıyla denenir; ilk başarılı olan kullanılır:

**Öncelik 1: Açık Context Yolu (`--cp`)**
- Kullanıcı tarafından `--cp` parametresi ile belirtilen dizin okunur
- Öncelik sırasına göre dosyalar yüklenir: `architecture.md` → `conventions.md` → `glossary.md` → `prd.md`
- Ardından `domain/`, `guides/`, `infrastructure/` alt dizinlerindeki dosyalar taranır
- Kalan `.md` dosyaları yüklenir

**Öncelik 2: Proje İçi Context Dizini**
- Proje kökünde `.context/`, `context/` veya `docs/` dizinleri aranır
- Bulunan ilk dizindeki `.md` dosyaları aynı öncelik mantığıyla yüklenir

**Öncelik 3: LLM Destekli Dosya Sınıflandırma**
- Projenin tüm `.md` dosyaları taranır (node_modules, .git, .venv gibi dizinler atlanır)
- Dosya adlarındaki anahtar kelimelere göre ön skorlama yapılır (`architecture`, `convention`, `pattern`, vb.)
- Yüksek ön skorlu dosyalar doğrudan seçilir
- Düşük ön skorlu dosyalar (en fazla 10 adet) LLM'e gönderilerek **ilgi düzeyi sınıflandırması** yapılır:
  - `RELEVANT`: Alan kuralları, mimari kararlar, isimlendirme standartları içeriyor
  - `NOT_RELEVANT`: Genel readme, changelog, license vb.
- Toplamda en fazla 5 dosya, maksimum 50.000 karakter sınırıyla birleştirilir

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `domain_context_str` | `str` | Birleştirilmiş alan bilgisi metni (markdown formatında) |
| `source_meta` | `list[dict]` | Kaynak dosyaların meta bilgileri (dosya yolu, ön skor, kaynak türü) |

### Kullanılan Model

`critic_a` alias'ı → `cheap_large_context` (yalnızca Öncelik 3'te LLM sınıflandırma gerektiğinde)

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `domain_context.md` | Birleştirilmiş domain context metni |
| `domain_docs.json` | Kaynak dosya meta bilgileri |

### Tipik Süre

~30 saniye (dosya tarama + LLM sınıflandırma)

---

## 4. Cross-Reference (Çapraz Referans)

### Amaç

Dokümanı hedef projenin gerçek kod tabanıyla karşılaştırır. Dokümanda bahsedilen API route'ları, veri modelleri, bağımlılıklar ve mimari yapılar projede gerçekten var mı diye kontrol eder. Eksik, çelişen veya gereksiz önerileri tespit eder.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `project_path` | `str` | Hedef projenin kök dizini |

### İşleme Mantığı

1. **Kod tabanı taraması** (`scan_project`):
   - Proje dizininde API route'ları, veritabanı modelleri, servis sınıfları, konfigürasyon dosyaları taranır
   - Bulunan yapılar bir context metni olarak formatlanır

2. **LLM karşılaştırması**:
   - Kod tabanı context'i ve doküman içeriği birlikte LLM'e gönderilir
   - LLM, dokümanın kod tabanıyla tutarsız olduğu noktaları tespit eder:
     - Var olmayan API endpoint'leri
     - Mevcut olmayan veri modelleri
     - Eksik bağımlılıklar (package.json, requirements.txt vb.)
     - Mevcut mimariyle çelişen öneriler
     - Zaten mevcut olan bileşenlerin yeniden oluşturulması

3. Bulunan her sorun bir `Issue` nesnesi olarak yapılandırılır ve `XR-` (cross-reference) öneki ile ID'lenir

4. **Early Exit Kontrolü** (eğer aktif profilde `early_exit` etkinleştirilmişse):
   - Kritik seviyeli çapraz referans sorunları belirli bir eşiği aşarsa pipeline erken sonlandırılır
   - Kullanıcıya "KALDI" kararı ve aksiyon planı döndürülür

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `issues` | `list[Issue]` | Tespit edilen çapraz referans sorunları |
| `codebase_context` | `str?` | Kod tabanının yapısal özeti |

### Kullanılan Model

`critic_a` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `codebase_context.md` | Kod tabanının yapısal özeti |
| `cross_ref_issues.json` | Tespit edilen çapraz referans sorunları |
| `early_exit.json` | *(koşullu)* Early exit tetiklendiyse abort bilgisi |

### Tipik Süre

~35 saniye (kod tarama + LLM analizi)

---

## 5. Deep Analysis (Derin Alan Analizi)

### Amaç

Domain context ve codebase context bilgilerini kullanarak dokümanın proje standartlarına uygunluğunu derinlemesine analiz eder. Hangi tasarım desenlerinin doğru uygulandığını, hangi alan kurallarının ihlal edildiğini ve bunların kasıtlı mı yoksa hata mı olduğunu belirler.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `domain_context` | `str` | Domain Context aşamasından gelen alan bilgisi |
| `codebase_context` | `str` | Cross-Reference aşamasından gelen kod tabanı özeti |

### İşleme Mantığı

1. Dört ana girdi (domain context, codebase context, doküman türü, doküman içeriği) bir prompt şablonuna yerleştirilir
2. LLM, dokümanı alan kuralları açısından analiz eder ve beş ana bölüm döndürür:

**Tespit Edilen Domain Desenleri (`domain_patterns_found`)**
- Dokümanın doğru bir şekilde takip ettiği proje standartları

**Domain İhlalleri (`domain_violations`)**
- Proje standartlarıyla çelişen gerçek sorunlar
- Her ihlal için: kural, açıklama, kanıt ve olması gereken desen belirtilir

**Kasıtlı Desenler (`intentional_patterns`)**
- İhlal gibi görünen ancak bilinçli tasarım kararları
- Güven skoru (confidence) ile birlikte raporlanır
- Bu desenler sonraki aşamalarda "sorun değil" olarak işaretlenir

**Risk Değerlendirmesi (`risk_assessment`)**
- Genel risk seviyesi (`low`, `medium`, `high`, `critical`)
- Risk faktörleri ve etkilenen kritik yollar

**Mevcut Altyapı (`existing_infrastructure`)**
- Dokümanda yeniden oluşturulması önerilen ancak halihazırda projede var olan yapılar

3. Analiz sonucu hem JSON hem de insan-okunabilir markdown formatında saklanır
4. **Early Exit Kontrolü**: Kritik seviyeli mimari ihlaller belirli bir eşiği aşarsa pipeline erken sonlandırılır

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `analysis` | `dict` | Detaylı domain analiz sonucu (ihlaller, desenler, risk, altyapı) |

### Kullanılan Model

`critic_a` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `domain_analysis.json` | Analiz sonucunun ham JSON hali |
| `domain_analysis.md` | İnsan-okunabilir format (doğrulama aşamasında kullanılır) |
| `early_exit.json` | *(koşullu)* Early exit tetiklendiyse abort bilgisi |

### Tipik Süre

~25 saniye

---

## 6. Critic A Multi (İlk Bağımsız Eleştirmen)

### Amaç

Dokümanı mantıksal tutarlılık, çelişkiler, eksik gereksinimler, tamamlanmamış mantık ve sıralama boşlukları açısından inceler. Birden fazla bağımsız çalıştırma (run) ile her çalıştırmada farklı sorunlar tespit edilir, böylece tek bir çağrının kör noktaları ortadan kaldırılır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `n_runs` | `int` | Çalıştırma sayısı (varsayılan: 3) |
| `max_workers` | `int` | Paralel thread sayısı (varsayılan: 1) |
| `delay_seconds` | `float` | Çalıştırmalar arası bekleme süresi (varsayılan: 5.0 saniye) |

### İşleme Mantığı

1. `config/prompts/critic_a.md` prompt şablonu yüklenir
2. Şablondaki `{{document_content}}` ve `{{document_type}}` yer tutucuları gerçek verilerle değiştirilir
3. Her çalıştırma (`run_index`) için:
   - Prompt LLM'e gönderilir (`temperature=0.3` — biraz yaratıcılık ile farklı sorunlar yakalanır)
   - Yanıttan JSON dizi çıkarımı yapılır
   - Her sorun bir `Issue` nesnesine dönüştürülür:
     - ID formatı: `A-{run_index}-{sıra}` (ör. `A-0-001`, `A-2-003`)
     - Önem derecesi (`severity`): `low`, `medium`, `high`, `critical`
     - Kategori, gerekçe, kanıt alıntısı, etkilenen bölüm ve önerilen düzeltme
     - Kaynak: `CRITIC_A`
4. Çalıştırmalar arasında `delay_seconds` kadar bekleme süresi uygulanır (rate limiting için)
5. Tüm çalıştırmalar `ThreadPoolExecutor` ile paralel veya ardışık yürütülür

**Critic A'nın Odak Alanları:**
- Mantıksal tutarlılık ve iç çelişkiler
- Eksik gereksinimler ve tamamlanmamış mantık
- Sıralama ve akış boşlukları
- Belirsiz veya yetersiz açıklamalar
- Tutarlı terminoloji kullanımı

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `runs` | `list[list[Issue]]` | Her çalıştırma için tespit edilen sorunların listesi |

### Kullanılan Model

`critic_a` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

Aşama sonunda doğrudan artifact yazılmaz; çıktısı sonraki aşamalara (Critic A Judge) aktarılır.

### Tipik Süre

~60 saniye (3 çalıştırma × ~20 saniye, paralel ise ~20 saniye)

---

## 7. Critic B Multi (İkinci Bağımsız Eleştirmen)

### Amaç

Critic A'dan farklı bir perspektiften dokümanı inceler. Critic A mantıksal tutarlılığa odaklanırken, Critic B uygulamaabilirlik, test edilebilirlik, rollout güvenliği, gözlemlenebilirlik, uç durumlar ve operasyonel risklere odaklanır. Farklı bir model (alias) kullanılarak "görüş birliği" (consensus) sağlanır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `n_runs` | `int` | Çalıştırma sayısı (varsayılan: 3) |
| `max_workers` | `int` | Paralel thread sayısı (varsayılan: 1) |
| `delay_seconds` | `float` | Çalıştırmalar arası bekleme süresi (varsayılan: 5.0 saniye) |

### İşleme Mantığı

1. `config/prompts/critic_b.md` prompt şablonu yüklenir (Critic A'dan farklı prompt)
2. Critic A ile aynı mekanizma çalışır, ancak:
   - Farklı model alias'ı kullanılır (`critic_b` → `cheap_large_context_alt`)
   - ID formatı: `B-{run_index}-{sıra}` (ör. `B-0-001`)
   - Kaynak: `CRITIC_B`
   - Farklı odak alanları ile farklı sorunlar tespit edilir

**Critic B'nin Odak Alanları:**
- Uygulamaabilirlik (implementability)
- Test edilebilirlik ve test stratejisi
- Rollout ve dağıtım güvenliği
- Gözlemlenebilirlik (logging, monitoring, alerting)
- Uç durumlar (edge cases) ve hata senaryoları
- Operasyonel riskler ve geri dönüş (rollback) planları
- Performans ve ölçeklenebilirlik

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `runs` | `list[list[Issue]]` | Her çalıştırma için tespit edilen sorunların listesi |

### Kullanılan Model

`critic_b` alias'ı → `cheap_large_context_alt` model grubu

### Artifact'ler

Aşama sonunda doğrudan artifact yazılmaz; çıktısı sonraki aşamalara (Critic B Judge) aktarılır.

### Tipik Süre

~60 saniye (3 çalıştırma × ~20 saniye, paralel ise ~20 saniye)

---

## 8. Critic A Judge (Critic A Hakemi)

### Amaç

Critic A'nın birden fazla çalıştırmasından gelen sorunları birleştirir, tekrarlayanları eler ve her sorunun geçerliliğini değerlendirir. Birden fazla çalıştırmada tekrarlanan sorunlar daha yüksek güvenle (consensus score) kabul edilir; yalnızca bir çalıştırmada görünen sorunlar ise reddedilebilir.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `runs` | `list[list[Issue]]` | Critic A Multi'nin tüm çalıştırma sonuçları |
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `critic_name` | `str` | `"critic_a"` |

### İşleme Mantığı

1. Tüm çalıştırmaların sorunları JSON formatında birleştirilir
2. `config/prompts/critic_judge.md` prompt şablonu yüklenir
3. Şablondaki `{{num_runs}}`, `{{critic_name}}`, `{{runs_json}}` ve `{{document_content}}` yer tutucuları doldurulur
4. LLM, her sorun için üç olası karar verir:
   - **`keep`**: Sorun geçerli, korunmalı
   - **`rejected`**: Sorun geçersiz (yanlış pozitif), reddedilmeli
   - **`inferred`**: Doğrudan belirtilmemiş ama dokümandan çıkarılabilen bir sorun (yeni tespit)
5. Her korunan sorun için:
   - Yeni ID atanır: `A-{sıra:03d}` (ör. `A-001`, `A-015`)
   - `consensus_score`: Sorunun kaç çalıştırmada tekrarlandığını gösteren 0.0-1.0 arası skor
   - `run_origins`: Sorunun hangi çalıştırmalardan geldiği
   - Kaynak: `CRITIC_A`
6. Reddedilen ve çıkarılan (inferred) sorun sayıları loglanır

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `kept_issues` | `list[Issue]` | Judge tarafından kabul edilen, konsolide edilmiş sorunlar |

### Kullanılan Model

`critic_judge` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

Aşama sonunda doğrudan artifact yazılmaz; çıktısı Dedupe aşamasına aktarılır.

### Tipik Süre

~20 saniye

---

## 9. Critic B Judge (Critic B Hakemi)

### Amaç

Critic B'nin birden fazla çalıştırmasından gelen sorunları birleştirir. Critic A Judge ile aynı mantık çalışır, ancak Critic B'nin sonuçları üzerinde uygulanır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `runs` | `list[list[Issue]]` | Critic B Multi'nin tüm çalıştırma sonuçları |
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `critic_name` | `str` | `"critic_b"` |

### İşleme Mantığı

Critic A Judge ile birebir aynı işleme mantığı:
1. Çalıştırma sonuçları JSON olarak birleştirilir
2. LLM her sorunu değerlendirir: `keep`, `rejected` veya `inferred`
3. Korunan sorunlara `B-{sıra:03d}` ID atanır
4. Kaynak: `CRITIC_B`

**Not:** Critic A Judge ve Critic B Judge paralel olarak yürütülür (ayrı thread'lerde).

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `kept_issues` | `list[Issue]` | Judge tarafından kabul edilen, konsolide edilmiş sorunlar |

### Kullanılan Model

`critic_judge` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

Aşama sonunda doğrudan artifact yazılmaz; çıktısı Dedupe aşamasına aktarılır.

### Tipik Süre

~20 saniye

---

## 10. Deduplication (Tekilleştirme)

### Amaç

Critic A Judge ve Critic B Judge çıktılarını birleştirir ve iki critic tarafından bağımsız olarak tespit edilen aynı sorunu tek bir sorun olarak birleştirir. Bu, iki farklı perspektiften onaylanan sorunların öncelik kazanmasını sağlar.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `issues_a` | `list[Issue]` | Critic A Judge tarafından kabul edilen sorunlar |
| `issues_b` | `list[Issue]` | Critic B Judge tarafından kabul edilen sorunlar |

### İşleme Mantığı

1. **Benzerlik hesaplama**: Her A sorunu için tüm B sorunlarıyla Jaccard benzerliği hesaplanır:
   - Başlık ve gerekçe metinlerinin kelime kümeleri karşılaştırılır
   - Başlık benzerliği ve gerekçe benzerliğinin ortalaması alınır
   - Eşik: >= 0.5 (iki sorun "yeterince benzer" kabul edilir)

2. **Birleştirme**: Eşleşen sorunlar tek bir sorun haline getirilir:
   - Yeni ID: `{A-ID}+{B-ID}` (ör. `A-001+B-003`)
   - Önem derecesi: İki sorunun daha yüksek olanı alınır
   - Gerekçe: Her iki critic'in gerekçeleri birleştirilir (`[Critic A] ... [Critic B] ...`)
   - Kanıt ve önerilen düzeltme: Dolu olan değer tercih edilir
   - Kaynak: `BOTH`

3. **Eşleşmeyenler**: Herhangi bir eşleşme bulamayan sorunlar olduğu gibi korunur

4. Cross-reference sorunları da bu aşamada birleştirilir (ID'leri `XR-` önekli)

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `merged` | `list[Issue]` | Tekilleştirilmiş sorun listesi |

### Kullanılan Model

LLM kullanılmaz — tamamen algoritmik (Jaccard benzerliği)

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `issues.json` | Cross-reference sorunları + tekilleştirilmiş critic sorunlarının tam listesi |

### Tipik Süre

~1 saniye

---

## 11. Validation (Sorun Doğrulama)

### Amaç

Her sorunu orijinal doküman, domain context, codebase context ve domain analizi bağlamında doğrular. LLM, her sorunun gerçekten geçerli olup olmadığına, yanlış pozitif olup olmadığına veya belirsiz olduğuna karar verir. Bu aşama, düşük kaliteli veya hatalı tespitlerin elenmesini sağlar.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `issues` | `list[Issue]` | Tekilleştirilmiş tüm sorunlar |
| `document_content` | `str` | Orijinal doküman içeriği |
| `domain_context` | `str` | Domain context (boş olabilir) |
| `codebase_context` | `str` | Codebase context (boş olabilir) |
| `domain_analysis` | `str` | Deep analysis çıktısı (boş olabilir) |

### İşleme Mantığı

1. `config/prompts/validator.md` prompt şablonu yüklenir
2. Sorunlar JSON formatında serileştirilir ve şablona yerleştirilir
3. Domain context, codebase context ve domain analizi (varsa) şablona eklenir; yoksa yer tutucu metin kullanılır
4. LLM her sorun için bir doğrulama kararı verir:

**Karar Tipleri (`ValidationDecision`):**

| Karar | Açıklama |
|-------|----------|
| `valid` | Sorun gerçek ve doğru tespit edilmiş |
| `invalid` | Yanlış pozitif; sorun gerçek değil |
| `uncertain` | Yeterli kanıt yok, kesin karar verilemiyor |

5. Her doğrulama için:
   - **Güven skoru** (`confidence`): 0.0-1.0 arası
   - **Gerekçe** (`reason`): Kararın açıklaması
   - **Otomatik uygulanabilirlik** (`should_auto_apply`): Yalnızca `valid` ve `confidence >= 0.8` ise `true`

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `validations` | `list[Validation]` | Her sorun için doğrulama kararı |

### Kullanılan Model

`validator` alias'ı → `strong_judge` model grubu (yüksek doğruluk gerektiren aşama)

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `validations.json` | Her sorunun doğrulama sonucu (karar, güven, gerekçe, otomatik uygulanabilirlik) |

### Tipik Süre

~30 saniye

---

## 12. Revise (Doküman Revizyonu)

### Amaç

Doğrulanmış sorunları kullanarak orijinal dokümanın düzeltilmiş bir versiyonunu üretir. Sadece doğrulama aşamasında `valid` kararı verilmiş ve `should_auto_apply=true` olan sorunlar düzeltme için kullanılır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `document_content` | `str` | Orijinal doküman içeriği |
| `document_type` | `str` | Doküman türü |
| `valid_issues` | `list[Issue]` | Doğrulanmış ve otomatik uygulanabilir sorunlar |

### İşleme Mantığı

1. Doğrulanmış sorunlar filtrelenir: Sadece `should_auto_apply=true` ve `decision=valid` olanlar alınır
2. Eğer geçerli sorun yoksa orijinal doküman değiştirilmeden döndürülür
3. `config/prompts/reviser.md` prompt şablonu yüklenir
4. Sorunlar JSON formatında şablona yerleştirilir
5. LLM, orijinal dokümanı koruyarak sadece belirtilen sorunları düzelten bir revize doküman üretir:
   - Orijinal başlık yapısı korunur
   - Orijinal ton ve üslup korunur
   - Sadece belirtilen sorunlar düzeltilir, başka değişiklik yapılmaz
6. Yanıttaki Markdown kod bloğu işaretleri (``` ```) temizlenir

**Not:** Birleştirilmiş sorunların ID'leri `+` içerir (ör. `A-001+B-003`). Revize aşaması, ID'nin herhangi bir parçası doğrulanmışsa sorunu ele alır.

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `revised` | `str` | Düzeltilmiş doküman içeriği (markdown) |

### Kullanılan Model

`reviser` alias'ı → `cheap_large_context` model grubu

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `revised.md` | Revize edilmiş doküman |

### Tipik Süre

~25 saniye

---

## 13. Score (8 Boyutlu Skorlama)

### Amaç

Revize edilmiş dokümanı 8 boyutta değerlendirir, ağırlıklı bir genel puan hesaplar ve bir quality gate kararı verir. Hem LLM tabanlı skorlama hem de Promptfoo rubrik tabanlı bağımsız değerlendirme çalışır; sonuçlar birleştirilir.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `revised_content` | `str` | Revize edilmiş doküman |
| `document_type` | `str` | Doküman türü |
| `original_content` | `str` | Orijinal doküman (karşılaştırma için) |
| `issues` | `list[Issue]` | Tüm tespit edilen sorunlar |
| `validations` | `list[Validation]` | Doğrulama sonuçları |
| `threshold_config` | `ThresholdConfig` | Eşik değerleri ve ağırlıklar |

### İşleme Mantığı

**Adım 1: Çoklu LLM Skorlama**
- Varsayılan 3 bağımsız çalıştırma yapılır (paralel)
- Her çalıştırmada LLM 8 boyut puanı verir (0.0-10.0):

| Boyut | Açıklama |
|-------|----------|
| `correctness` | Doğruluk — dokümandaki teknik bilgiler doğru mu |
| `completeness` | Tamlık — tüm gerekli bilgiler mevcut mu |
| `implementability` | Uygulamaabilirlik — dokümandan kod yazılabilir mi |
| `consistency` | Tutarlılık — iç çelişki yok mu |
| `edge_case_coverage` | Uç durum kapsamı — edge case'ler düşünülmüş mü |
| `testability` | Test edilebilirlik — test stratejisi belirtilmiş mi |
| `risk_awareness` | Risk farkındalığı — riskler ve azaltımlar belirtilmiş mi |
| `clarity` | Netlik — anlaşılır ve belirsizlik yok mu |

- Her çalıştırmada ayrıca: güçlü yönler, kalan endişeler, genel değerlendirme ve güven skoru üretilir

**Adım 2: Skorların Birleştirilmesi**
- Her boyut için tüm çalıştırmaların **medyan** değeri alınır
- Boyutlar arası varyans hesaplanır → güven skoru türetilir (düşük varyans = yüksek güven)
- Güçlü yönler ve endişeler: En sık tekrarlayan 5 tanesi seçilir

**Adım 3: Promptfoo Bağımsız Değerlendirmesi**
- Farklı bir model ile Promptfoo rubrik tabanlı değerlendirme çalışır
- Aynı 8 boyut için bağımsız skorlar üretilir

**Adım 4: LLM ve Promptfoo Skorlarının Birleştirilmesi**
- Ağırlıklı ortalama: LLM %60, Promptfoo %40
- İki değerlendiricinin uyuşma oranı hesaplanır:
  - `agree`: 7/8+ boyutta aynı eşiğin üstünde/altında (güven cezası yok)
  - `partial`: 5-6/8 boyutta uyuşma (%8 güven cezası)
  - `disagree`: 4 veya daha az boyutta uyuşma (%15 güven cezası)

**Adım 5: Quality Gate Mantığı**
- Ağırlıklı genel puan hesaplanır (boyut ağırlıkları `threshold_config`'den)
- Gate kararı:

| Koşul | Sonuç | Sonraki Adım |
|-------|-------|-------------|
| Puan >= eşik | GEÇTİ | `IMPLEMENT` |
| Eşik - 2.0 `<=` puan `<` eşik | KALDI (yakın) | `REVISE_AGAIN` |
| Puan < eşik - 2.0 | KALDI (uzak) | `HUMAN_REVIEW` |

- Ek kontroller:
  - Kritik boyutlar (ör. `correctness`) ayrı eşik kontrolünden geçer
  - Çözülmemiş kritik/high sorun sayısı engelleyici neden olarak eklenir

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `scorecard` | `Scorecard` | Tüm skor bilgilerini içeren kapsamlı sonuç nesnesi |
| `promptfoo_raw` | `dict?` | Promptfoo ham değerlendirme sonucu |

### Kullanılan Model

| Bileşen | Alias | Model Grubu |
|---------|-------|-------------|
| LLM Scorer | `scorer` | `strong_judge` |
| Promptfoo | `scorer_promptfoo` | `fallback_general` |

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `scorecard.json` | Tüm skor bilgileri (boyutlar, genel puan, gate kararı, güçlü yönler, endişeler, güven, varyans) |
| `promptfoo_raw.json` | *(koşullu)* Promptfoo ham sonucu |

### Tipik Süre

~60 saniye (LLM 3 çalıştırma + Promptfoo değerlendirmesi)

---

## 14. Meta Judge (Üst Hakem)

### Amaç

Skorlama aşamasının adaletini değerlendirir. Skorlar aşırı iyimser mi, aşırı kötümser mi, yoksa adil mi? Gerekirse boyut puanlarını ince ayarlarla düzeltir ve genel skoru yeniden hesaplar. Bu aşama, tek bir modelin kendi skorunu denetlemesini engelleyen bir "denetler denetlenir" mekanizmasıdır.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `scorecard` | `Scorecard` | Score aşamasından gelen skor kartı |
| `revised_content` | `str` | Revize edilmiş doküman (ilk 8000 karakter) |
| `document_type` | `str` | Doküman türü |

### İşleme Mantığı

1. **Atlama kontrolü**: Aşağıdaki koşulların hepsi sağlanıyorsa meta-judge atlanır:
   - Güven skoru >= 0.85
   - Promptfoo uyuşması `agree` veya yok
   - Engelleyici neden yok
   Bu durumda skorlar olduğu gibi kabul edilir.

2. `config/prompts/meta_judge.md` prompt şablonu yüklenir
3. Skor kartı bilgileri (boyut puanları, çalıştırma sayısı, varyans, güven, promptfoo sonuçları) şablona yerleştirilir
4. LLM şu kararları verir:

**Karar Tipleri (`verdict`):**

| Karar | Açıklama |
|-------|----------|
| `fair` | Skorlar adil, düzeltme gereksiz |
| `over_optimistic` | Skorlar çok yüksek, aşağı çekilmeli |
| `over_pessimistic` | Skorlar çok düşük, yukarı çekilmeli |
| `needs_adjustment` | Belirli boyutlarda ince ayar gerekli |

5. **Düzeltmeler** (`adjustments`): Her boyut için -1.5 ile +1.5 arası ince ayar değeri (sıfır olmayanlar raporlanır)
6. **Güven düzeltmesi** (`confidence_adjustment`): -0.1 ile +0.1 arası

7. Düzeltmeler uygulandığında:
   - Boyut puanları 0.0-10.0 aralığına kırpılır
   - Ağırlıklı genel puan yeniden hesaplanır
   - Gate mantığı yeniden değerlendirilir
   - Yeni `IMPLEMENT` / `REVISE_AGAIN` / `HUMAN_REVIEW` kararı verilir

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `meta_result` | `MetaJudgeResult` | Karar, düzeltmeler, gerekçe ve güven düzeltmesi |
| `adjusted_scorecard` | `Scorecard` | Düzeltilmiş (veya aynen korunmuş) skor kartı |

### Kullanılan Model

`meta_judge` alias'ı → `strong_judge` model grubu

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `meta_judge.json` | Meta-judge sonucu (karar, düzeltmeler, gerekçe) |
| `scorecard.json` | *(güncellenir)* Düzeltilmiş skor kartı |

### Tipik Süre

~20 saniye (koşullu; yüksek güvenle atlanabilir)

---

## 15. Fact Check (Gerçeklik Doğrulama)

### Amaç

Tüm tespit edilen sorunların gerçekliğini (reality) değerlendirir. Her sorunun gerçek bir sorun olup olmadığını, yoksa yanlış pozitif mi olduğunu veya kasıtlı bir tasarım kararı mı olduğunu belirler. Onaylanan sorunlar için düzeltme önerileri üretir ve otomatik uygulanabilirlik kararını verir.

### Girdi

Fact Check aşaması, önceki aşamaların artifact dosyalarını doğrudan run dizininden okur:

| Dosya | Kullanım |
|-------|----------|
| `issues.json` | Değerlendirilecek sorun listesi |
| `domain_analysis.json` | Domain ihlalleri ve kasıtlı desenler |
| `meta_judge.json` | Meta-judge değerlendirmesi |
| `scorecard.json` | Kalan endişeler |
| `validations.json` | Önceki doğrulama kararları |
| `original.md` | Orijinal doküman içeriği |

### İşleme Mantığı

1. Run dizinindeki artifact dosyaları yüklenir
2. Domain ihlalleri, kasıtlı desenler ve doğrulama sonuçları özetlenir
3. `config/prompts/fact_check.md` prompt şablonu yüklenir
4. Sorunlar ve tüm context bilgileri LLM'e gönderilir
5. LLM her sorun için bir gerçeklik kararı verir:

**Gerçeklik Kararları (`RealityVerdict`):**

| Karar | Açıklama |
|-------|----------|
| `confirmed` | Sorun gerçek ve geçerli |
| `refuted` | Yanlış pozitif; sorun gerçek değil (kasıtlı tasarım kararı olabilir) |
| `uncertain` | Yeterli kanıt yok |

6. Her değerlendirme için:
   - **Gerçeklik skoru** (`reality_score`): 0.0-1.0 arası güven skoru
   - **Destekleyen kanıtlar** (`evidence_for`): Sorunun gerçek olduğunu gösteren nedenler
   - **Karşı kanıtlar** (`evidence_against`): Sorunun geçersiz olduğunu gösteren nedenler
   - **Düzeltme önerisi** (`proposed_fix`): Sadece `confirmed` sorunlar için:
     - Etkilenen bölüm, mevcut metin, önerilen metin ve açıklama
   - **Otomatik uygulanabilirlik**: `confirmed` ve `reality_score >= 0.8` ise `true`

7. Özet rapor üretilir (Türkçe)

**Düzeltme Uygulama Akışı:**
- Onaylanan düzeltmeler `approved_fixes.json` dosyasına yazılabilir
- `dqg apply-fixes <run_id>` komutu ile otomatik olarak uygulanabilir
- Uygulama, LLM (reviser modeli) tarafından yapılır; sadece onaylanan bölümler değiştirilir

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `fact_check_result` | `FactCheckResult` | Tüm sorunların gerçeklik değerlendirmesi ve özet |

### Kullanılan Model

`meta_judge` alias'ı → `strong_judge` model grubu

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `fact_check.json` | Tüm fact-check sonuçları (detaylı) |
| `fact_check.md` | İnsan-okunabilir fact-check raporu |

### Tipik Süre

~30 saniye

---

## 16. Report (Rapor Üretimi)

### Amaç

Pipeline'ın tüm sonuçlarını kapsamlı ve görsel olarak düzenlenmiş Markdown ve HTML raporları olarak sunar. Kullanıcıya tek bakışta anlaşılır bir özet sunar: gate kararı, boyut puanları, sorun listesi, fact-check sonuçları, token kullanımı ve model yapılandırması.

### Girdi

| Parametre | Tür | Açıklama |
|-----------|-----|----------|
| `artifacts` | `RunArtifacts` | Pipeline'ın tüm çıktıları (sorunlar, doğrulamalar, skor kartı, metadata, fact-check) |
| `threshold_config` | `ThresholdConfig` | Eşik değerleri ve boyut ağırlıkları |

### İşleme Mantığı

1. **Veri hazırlığı**:
   - Skor kartındaki 8 boyut, ağırlıklarıyla birlikte formatlanır
   - Her sorun, doğrulama durumuyla eşleştirilir
   - Fact-check sonuçları etiketlenir (onaylanan, çürütülen, belirsiz)
   - Token kullanım istatistikleri toplanır

2. **Markdown raporu** (`report.md`):
   - Jinja2 şablonu ile render edilir
   - Bölümler: Kapı Kararı, Boyut Puanları, Sorun Özeti, Fact-Check Sonuçları, Model Yapılandırması, Token Kullanımı

3. **HTML raporu** (`report.html`):
   - Tamamen kendi içinde (self-contained) bir HTML dosyası
   - Responsive tasarım (mobil uyumlu)
   - Renk kodlu önem derecesi badge'leri (critical=kırmızı, high=turuncu, medium=sarı, low=mor)
   - Renk kodlu skor çubukları (`>=`8 yeşil, 6-7.9 sarı, `<`6 kırmızı)
   - Gate sonucu kutusu: GEÇTİ (yeşil) veya KALDI (kırmızı)

### Rapor Bölümleri

| Bölüm | İçerik |
|-------|--------|
| **Kapı Kararı** | Genel puan, GEÇTİ/KALDI, sonraki adım, çözülmemiş kritik sorun sayısı, güven, scorer çalıştırma sayısı, engelleyici nedenler |
| **Boyut Puanları** | 8 boyut tablosu (puan, ağırlık, ağırlıklı değer) |
| **Sorun Özeti** | Toplam/geçerli/geçersiz/belirsiz sayıları, sorun tablosu (ID, başlık, önem, kategori, kaynak, doğrulama durumu) |
| **Fact-Check** | Onaylanan/çürütülen/belirsiz sayıları, detaylı sonuç tablosu, onaylanan sorunlar için düzeltme önerileri |
| **Model Yapılandırması** | Her aşamanın kullandığı model alias ve gerçek model |
| **Token Kullanımı** | Toplam token, prompt/completion dağılımı, çağrı sayısı, model bazında detay |

### Çıktı

| Çıktı | Tür | Açıklama |
|-------|-----|----------|
| `md_report` | `str` | Markdown formatında rapor |
| `html_report` | `str` | HTML formatında rapor |

### Kullanılan Model

LLM kullanılmaz — Jinja2 şablonu ile render

### Artifact'ler

| Dosya | Açıklama |
|-------|----------|
| `report.md` | Markdown raporu |
| `report.html` | HTML raporu |
| `metadata.json` | Çalışma meta verisi (zaman damgası, model aliases, token kullanımı, süre) |
| `token_report.json` | Detaylı token kullanım raporu |

### Tipik Süre

~2 saniye

---

## Run Dizini Artifact Özeti

Bir pipeline çalışması tamamlandığında, `outputs/` dizini altında `{run_id}` adlı bir dizin oluşturulur. Bu dizinde aşağıdaki dosyalar bulunur:

```
outputs/{run_id}/
├── original.md              # Orijinal doküman
├── revised.md               # Revize edilmiş doküman
├── issues.json              # Tespit edilen tüm sorunlar
├── validations.json         # Her sorunun doğrulama sonucu
├── scorecard.json           # 8 boyutlu skor kartı + gate kararı
├── report.md                # Markdown raporu
├── report.html              # HTML raporu
├── metadata.json            # Çalışma meta verisi
├── token_report.json        # Token kullanım raporu
├── complexity_router.json   # *(koşullu)* Karmaşıklık yönlendirme sonucu
├── pipeline_profile.json    # *(koşullu)* Seçilen pipeline profili
├── domain_context.md        # *(koşullu)* Domain context
├── domain_docs.json         # *(koşullu)* Domain kaynak dosya meta verileri
├── codebase_context.md      # *(koşullu)* Kod tabanı yapısal özeti
├── cross_ref_issues.json    # *(koşullu)* Çapraz referans sorunları
├── domain_analysis.json     # *(koşullu)* Derin domain analizi (JSON)
├── domain_analysis.md       # *(koşullu)* Derin domain analizi (Markdown)
├── meta_judge.json          # *(koşullu)* Meta-judge değerlendirmesi
├── fact_check.json          # *(koşullu)* Fact-check sonuçları
├── fact_check.md            # *(koşullu)* Fact-check raporu
├── promptfoo_raw.json       # *(koşullu)* Promptfoo ham sonucu
├── early_exit.json          # *(koşullu)* Early exit bilgisi
```

*(koşullu)* işaretli dosyalar, yalnızca ilgili aşama çalıştırıldığında ve bir sonuç ürettiğinde oluşturulur.

---

## Pipeline Profilleri

DQG, dokümanın karmaşıklığına göre farklı derinlikte analiz yapabilen üç profil sunar:

| Profil | Aşama Sayısı | Tahmini Süre | Açıklama |
|--------|-------------|-------------|----------|
| `fast_track` | ~8 | ~2-3 dakika | Basit değişiklikler için; deep_analysis, meta_judge, fact_check atlanır |
| `standard` | ~11 | ~3-4 dakika | Orta karmaşıklıkta; domain_context + critic + score + report |
| `deep` | 14+ | ~6-8 dakika | Tam derinlemesine analiz; tüm aşamalar dahil |

`profile=auto` seçildiğinde Complexity Router aşaması otomatik olarak uygun profili seçer.

---

## Paralel Yürütme Grupları

Pipeline'ın toplam süresini minimize etmek için bazı aşamalar paralel olarak yürütülür:

### Fan-Out Grup 1 (Aşama 3-7)

```
domain_context ─┐
cross_reference ─┤  (paralel)
critic_a_multi ──┤
critic_b_multi ──┘
```

Dört aşama aynı anda başlatılır; hepsi tamamlandığında sonraki aşamalara geçilir.

### Critic Judges (Aşama 8-9)

```
critic_a_judge ──┐  (paralel)
critic_b_judge ──┘
```

İki judge aşaması paralel yürütülür.

---

## Tipik Pipeline Süreleri

| Aşama | Süre (sn) | Not |
|-------|-----------|-----|
| Ingest | 0.5 | Yerel dosya okuma |
| Complexity Router | 5 | Tek LLM çağrısı |
| Domain Context | 30 | Dosya tarama + LLM sınıflandırma |
| Cross-Reference | 35 | Kod taraması + LLM analizi |
| Deep Analysis | 25 | LLM analizi |
| Critic A Multi (3 run) | 60 | 3× LLM çağrısı |
| Critic B Multi (3 run) | 60 | 3× LLM çağrısı |
| Critic A Judge | 20 | Tek LLM çağrısı |
| Critic B Judge | 20 | Tek LLM çağrısı |
| Dedupe | 1 | Algoritmik, LLM yok |
| Validation | 30 | LLM çağrısı |
| Revise | 25 | LLM üretim |
| Score | 60 | LLM 3 run + Promptfoo |
| Meta Judge | 20 | Koşullu; atlanabilir |
| Fact Check | 30 | Koşullu |
| Report | 2 | Şablon render |

**Toplam (deep profil, paralel fan-out ile):** ~6-8 dakika
**Toplam (fast_track profil):** ~2-3 dakika
