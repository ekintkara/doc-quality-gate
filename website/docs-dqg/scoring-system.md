---
sidebar_position: 5
title: Skorlama Sistemi
---

# Skorlama Sistemi (Scoring System)

Doc Quality Gate (DQG), doküman kalitesini tek bir öznel yoruma değil, **8 bağımsız boyut** üzerinden nicel bir skorlamaya dönüştürür. Bu skorlama, çoklu çalıştırma (multi-run), bağımsız Promptfoo doğrulaması ve meta-judge düzeltmesi ile sağlamlaştırılır. Nihai sonuç, geçme/kalma (PASS/FAIL) kararını belirleyen bir **Scorecard** nesnesidir.

---

## İçindekiler

1. [Skorlama Sistemine Genel Bakış](#1-skorlama-sistemine-genel-bakış)
2. [8 Boyut (Dimensions)](#2-8-boyut-dimensions)
3. [Skor Hesaplama](#3-skor-hesaplama)
4. [Multi-Run Scoring](#4-multi-run-scoring)
5. [Promptfoo Entegrasyonu](#5-promptfoo-entegrasyonu)
6. [Meta Judge](#6-meta-judge)
7. [Threshold Konfigürasyonu](#7-threshold-konfigürasyonu)
8. [Scorecard Çıktısı](#8-scorecard-çıktısı)
9. [Geçme/Kalma Kriterleri](#9-gecmekalma-kriterleri)

---

## 1. Skorlama Sistemine Genel Bakış

### Akış Diyagramı

```
                          ┌──────────────────┐
                          │  Revize Doküman  │
                          └────────┬─────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
             ┌──────────┐  ┌──────────┐   ┌──────────────┐
             │  Run #1  │  │  Run #2  │   │  Run #N      │
             │ (LLM)    │  │ (LLM)    │   │ (LLM)        │
             └────┬─────┘  └────┬─────┘   └──────┬───────┘
                  │              │                │
                  └──────────────┼────────────────┘
                                 │
                                 ▼
                     ┌─────────────────────┐
                     │  Aggregate (Median) │
                     │  + Varyans Hesabı   │
                     └──────────┬──────────┘
                                │
                     ┌──────────┼──────────┐
                     │                       │
                     ▼                       ▼
            ┌─────────────────┐    ┌──────────────────┐
            │ LLM Scorer      │    │ Promptfoo Runner  │
            │ Sonuçları       │    │ (Farklı Model)    │
            └────────┬────────┘    └────────┬─────────┘
                     │                      │
                     └──────────┬───────────┘
                                │
                                ▼
                   ┌──────────────────────────┐
                   │  Merge (Ağırlıklı Ort.)  │
                   │  LLM: %60  PF: %40      │
                   └────────────┬─────────────┘
                                │
                                ▼
                   ┌──────────────────────────┐
                   │     Meta Judge           │
                   │  (Skor Adilliği Kontrolü)│
                   └────────────┬─────────────┘
                                │
                                ▼
                   ┌──────────────────────────┐
                   │     Gate Logic           │
                   │  (PASS / FAIL Kararı)    │
                   └────────────┬─────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │  Scorecard   │
                        └──────────────┘
```

### Temel İlkeler

| İlke | Açıklama |
|------|----------|
| **Çoklu Çalıştırma** | Aynı doküman N kez skorlanır, sonuçların medyanı alınır |
| **Bağımsız Doğrulama** | Promptfoo ile farklı bir model aynı dokümanı değerlendirir |
| **Ağırlıklı Birleştirme** | LLM scorer %60, Promptfoo %40 ağırlığıyla birleştirilir |
| **Meta-Judge** | Son skorların adilliğini üçüncü bir model denetler |
| **Boyut Bazlı Eşik** | Sadece genel skor değil, kritik boyutlar da ayrıca kontrol edilir |
| **Ağırlıklı (Weighted) Ortalama** | Her boyut doküman türüne göre farklı ağırlığa sahip olabilir |

### Kaynak Dosyalar

| Bileşen | Dosya Yolu |
|---------|-----------|
| Skorlama mantığı | `src/app/stages/score.py` |
| Meta-Judge | `src/app/stages/meta_judge.py` |
| Veri modelleri | `src/app/schemas.py` |
| Threshold konfigürasyonu | `config/thresholds.yaml` |
| Promptfoo runner | `src/app/integrations/promptfoo_runner.py` |
| Uygulama konfigürasyonu | `config/app.yaml` |
| Konfig yükleme | `src/app/config.py` |
| Scorer prompt | `config/prompts/scorer.md` |
| Meta-Judge prompt | `config/prompts/meta_judge.md` |

---

## 2. 8 Boyut (Dimensions)

DQG, her dokümanı 8 bağımsız kalite boyutunda değerlendirir. Her boyut **0.0 ile 10.0** arasında skorlanır. Bu boyutlar, `DimensionScores` Pydantic modelinde tanımlanmıştır (`src/app/schemas.py:87-95`):

```python
class DimensionScores(BaseModel):
    correctness: float = Field(default=0.0, ge=0.0, le=10.0)
    completeness: float = Field(default=0.0, ge=0.0, le=10.0)
    implementability: float = Field(default=0.0, ge=0.0, le=10.0)
    consistency: float = Field(default=0.0, ge=0.0, le=10.0)
    edge_case_coverage: float = Field(default=0.0, ge=0.0, le=10.0)
    testability: float = Field(default=0.0, ge=0.0, le=10.0)
    risk_awareness: float = Field(default=0.0, ge=0.0, le=10.0)
    clarity: float = Field(default=0.0, ge=0.0, le=10.0)
```

### Skor Aralıkları

Aralık | Anlam
-------|------
**0–3** | Ciddi eksiklik, kabul edilemez
**4–5** | Kabul standardının altında
**6–7** | Kabul edilebilir ancak iyileştirme gerekli
**8–9** | İyi kalite
**10** | Mükemmel, önemli bir sorun yok

---

### 2.1 correctness (Doğruluk)

> **Tanım:** Dokümandaki teknik bilgilerin, algoritmaların, API referanslarının ve mantıksal çıkarımların gerçeğe uygunluğu.

**Değerlendirilen Hususlar:**

- Kod tabanındaki mevcut API'ler, modeller ve dependency'ler ile uyumluluk
- Teknik terimlerin ve kavramların doğru kullanımı
- Mantıksal çıkarım zincirlerinde hata olup olmadığı
- Veri tipleri, dönüşümler ve hesaplamaların doğruluğu
- Referans verilen kütüphane/framework versiyonlarının gerçekliği
- Cross-reference aşamasında bulunan tutarsızlıkların çözülüp çözülmediği

**Düşük Skor Örneği:** Dokümanda "Redis cache kullanılıyor" yazıyor ama projede aslında Memcached kullanılıyorsa, correctness skoru ciddi şekilde düşer.

**Yüksek Skor İçin:** Tüm teknik iddialar mevcut kod tabanıyla doğrulanabilir olmalıdır.

---

### 2.2 completeness (Tamlık)

> **Tanım:** Dokümanın, tanımladığı işi baştan sona eksiksiz kapsaması. Adımlar, gereksinimler, bağımlılıklar ve çıktılar arasında boşluk olmaması.

**Değerlendirilen Hususlar:**

- Tüm gereksinimlerin (functional + non-functional) kapsanmış olması
- Eksik adım veya aşama olmaması (örn. migration plan'ında rollback adımının unutulmaması)
- Dependency'lerin ve önkoşulların açıkça belirtilmesi
- Hata senaryoları ve hata işleme (error handling) stratejisinin tanımlanmış olması
- Acceptance criteria'ların tam ve ölçülebilir olması
- Tüm etkilenen sistem/bileşenlerin listelenmiş olması

**Düşük Skor Örneği:** Bir API değişikliği planında "eski versiyonun sunset süreci" atlanmışsa, completeness skoru düşer.

**Yüksek Skor İçin:** Bir geliştirici dokümanı okuduğunda "burada ne yapılması gerektiği net" diyebilmeli, hiçbir şey soru işareti kalmamalıdır.

---

### 2.3 implementability (Uygulanabilirlik)

> **Tanım:** Dokümandaki planın, mevcut teknik altyapı ve takım yetkinlikleriyle fiilen hayata geçirilebilir olması.

**Değerlendirilen Hususlar:**

- Önerilen değişikliklerin mevcut mimariyle uyumluluğu
- Gerekli araç, kütüphane ve altyapının mevcut olması veya temin edilebilirliği
- Adımların yeterli detayda ve sıralı olması
- Performans, ölçeklenebilirlik ve güvenlik gereksinimlerinin pratikte karşılanabilirliği
- Takımın sahip olduğu yetkinliklerle bu planın gerçekleştirilebilmesi
- Tahmini efor/süre ile planın gerçekçiliği

**Düşük Skor Örneği:** "Mikroservisleri Kubernetes'e taşıyacağız" yazılmış ama takımın Kubernetes deneyimi yoksa ve eğitim planı yoksa, implementability skoru düşer.

**Yüksek Skor İçin:** Planı okuyan bir senior developer "evet, bunu yapabiliriz" diyebilmelidir.

---

### 2.4 consistency (Tutarlılık)

> **Tanım:** Dokümanın kendi içinde tutarlı olması. Farklı bölümler arasında çelişki, terminoloji karmaşası veya mantıksal tutarsızlık olmaması.

**Değerlendirilen Hususlar:**

- Terminolojinin doküman boyunca tutarlı kullanımı (aynı kavram için farklı isimler kullanılmaması)
- İsimlendirme kurallarına (API endpoint isimleri, değişken isimleri vb.) tutarlı uyum
- Farklı bölümlerdeki teknik detayların birbiriyle çelişmemesi
- Öncelik ve önem sıralamasının tutarlı olması
- Referanslar arası tutarlılık (bölüm A'da "X yapılacak" denip B'de "X yapılmayacak" denmemesi)
- Doküman formatının ve yapısının baştan sona tutarlı olması

**Düşük Skor Örneği:** Dokümanın bir bölümünde "PostgreSQL kullanılacak" yazıp başka bir bölümünde "MySQL veritabanında bu tablo..." deniyorsa, consistency skoru ciddi düşer.

**Yüksek Skor İçin:** Tüm bölümler birbiriyle uyumlu olmalı, okuyan kişi "burada çelişki var" dememelidir.

---

### 2.5 edge_case_coverage (Kenar Durum Kapsamı)

> **Tanım:** Sıra dışı, aşırı veya beklenmeyen senaryoların dokümanda ele alınmış olması.

**Değerlendirilen Hususlar:**

- Boş veri, null değer, sıfır sonuç gibi boundary durumların ele alınması
- Eşzamanlılık (concurrency) sorunlarının düşünülmesi
- Zaman aşımı (timeout), ağ kesintisi, service down senaryoları
- Sıralama bağımlılıkları (ordering dependencies)
- Ölçek limitlerinin (max veri boyutu, max kullanıcı sayısı vb.) tanımlanması
- Geçersiz veya kötü niyetli girdi (malicious input) senaryoları
- Backward compatibility ve migration sırasında yaşanabilecek uç durumlar

**Düşük Skor Örneği:** Bir ödeme entegrasyon planında "ödeme başarısız olursa ne yapılacak", "çift ödeme nasıl önlenecek" gibi senaryolar yoksa, edge_case_coverage skoru düşer.

**Yüksek Skor İçin:** "Ya şöyle olursa?" sorusuna dokümanın çoğu bölümünde yanıt bulunabilmelidir.

---

### 2.6 testability (Test Edilebilirlik)

> **Tanım:** Dokümandaki planın doğrulanabilir ve test edilebilir olması. Test stratejisi, test senaryoları ve doğrulama kriterlerinin bulunması.

**Değerlendirilen Hususlar:**

- Birim (unit), entegrasyon (integration) ve uçtan uca (E2E) test stratejilerinin tanımlanması
- Test edilebilirlik açısından kod tasarımının uygunluğu (mock'lanabilirlik, izolasyon vb.)
- Her gereksinim için doğrulama kriterlerinin (verification criteria) bulunması
- Test verisi (test data) hazırlama stratejisi
- Performans testi ve yük testi kriterleri
- Regression riski ve regression test kapsamı
- Manual test gereksinimleri (otomatik test ile kapsanamayan alanlar)

**Düşük Skor Örneği:** "Kullanıcı giriş yapacak" deniyor ama giriş başarılı/başarısız senaryoları için test yaklaşımı tanımlanmamışsa, testability skoru düşer.

**Yüksek Skor İçin:** Her fonksiyonel gereksinim için "bu nasıl test edilir?" sorusu yanıtlanmış olmalıdır.

---

### 2.7 risk_awareness (Risk Farkındalığı)

> **Tanım:** Dokümanda potansiyel risklerin tanımlanmış, etkilerinin değerlendirilmiş ve azaltma (mitigation) stratejilerinin belirlenmiş olması.

**Değerlendirilen Hususlar:**

- Teknik risklerin tanımlanması (teknoloji seçimi, karmaşıklık, bağımlılık riskleri)
- Operasyonel risklerin değerlendirilmesi (deployment, monitoring, rollback riskleri)
- Güvenlik riskleri ve bunların azaltılması
- İş (business) risklerinin tanımlanması
- Rollback ve geri alma planının bulunması
- Riskin olasılık ve etki matrisi
- Acil durum (contingency) planları

**Düşük Skor Örneği:** Bir veritabanı migration planında "data kaybı riski", "downtime süresi" ve "rollback planı" ele alınmamışsa, risk_awareness skoru düşer.

**Yüksek Skor İçin:** Planı inceleyen biri "en kötü senaryoda ne olur?" diye sorduğunda net bir yanıt bulabilmelidir.

---

### 2.8 clarity (Netlik)

> **Tanım:** Dokümanın okunabilir, anlaşılır ve açık olması. Gereksiz karmaşıklık, belirsiz ifadeler veya yapısal sorunlar içermemesi.

**Değerlendirilen Hususlar:**

- Net ve anlaşılır dil kullanımı
- İyi yapılandırılmış bölümler, başlıklar ve alt başlıklar
- Gerektiğinde diyagram, tablo ve kod örnekleri ile desteklenmesi
- Belirsiz ifadelerin ("gerekirse", "uygun şekilde", vb.) azaltılması
- Hedef kitleye uygun teknik detay seviyesi
- Özet ve sonuç bölümlerinin bulunması
- Versiyon, tarih ve yazar bilgisinin güncel olması

**Düşük Skor Örneği:** Doküman "bazı durumlarda sistemin güncellenmesi gerekebilir" gibi ifadeler içeriyorsa ve somut adımlar vermiyorsa, clarity skoru düşer.

**Yüksek Skor İçin:** İlk kez okuyan bir geliştirici bile dokümanın ne anlattığını hızla kavrayabilmelidir.

---

## 3. Skor Hesaplama

Genel skor (overall_score), boyut skorlarının **ağırlıklı ortalaması** ile hesaplanır. İşlem `score.py` içindeki `_compute_gate_logic` fonksiyonunda gerçekleştirilir (`src/app/stages/score.py:63-110`).

### 3.1 Ağırlıklı Ortalama Formülü

```
overall_score = Σ (boyut_skoru × boyut_ağırlığı) / Σ boyut_ağırlığı
```

**Kod Karşılığı:**

```python
weighted_sum = 0.0
weight_total = 0.0
for dim, score in scores_dict.items():
    w = weights.get(dim, 1.0)     # threshold konfigürasyonundan gelen ağırlık
    weighted_sum += score * w
    weight_total += w

overall_score = round(weighted_sum / weight_total, 2)
```

### 3.2 Varsayılan Ağırlıklar

Tüm boyutlar varsayılan olarak **1.0** ağırlığına sahiptir. Ancak `config/thresholds.yaml` içinde her doküman türü için farklı ağırlıklar tanımlanabilir. Bkz. [Bölüm 7](#7-threshold-konfigürasyonu).

### 3.3 Hesaplama Örneği

Bir `feature_spec` dokümanı için:

| Boyut | Skor | Ağırlık | Katkı |
|-------|------|---------|-------|
| correctness | 8.5 | 1.5 | 12.75 |
| completeness | 7.8 | 1.5 | 11.70 |
| implementability | 8.0 | 1.3 | 10.40 |
| consistency | 9.0 | 1.0 | 9.00 |
| edge_case_coverage | 7.2 | 1.2 | 8.64 |
| testability | 7.5 | 1.2 | 9.00 |
| risk_awareness | 6.8 | 1.0 | 6.80 |
| clarity | 8.2 | 1.0 | 8.20 |

```
weighted_sum  = 76.49
weight_total  = 9.70
overall_score = 76.49 / 9.70 = 7.89
```

Bu örnek için overall_threshold 8.0 olduğu için doküman **KALIR (FAIL)**.

---

## 4. Multi-Run Scoring

### 4.1 Neden Birden Fazla Çalıştırma?

LLM'ler doğası gereği **stokastik** (rastgele) davranış sergiler. Aynı prompt ve aynı doküman ile aynı modele yapılan iki farklı çağrı farklı skorlar üretebilir. Bu rastgeleliği azaltmak ve skor güvenilirliğini artırmak için DQG, skorlama işlemini **birden fazla kez** (default: 2, maksimum: N) çalıştırır.

### 4.2 Konfigürasyon

`config/app.yaml` içinde:

```yaml
pipeline:
  scorer_runs: 2           # Kaç kez çalıştırılacak (DQG_SCORER_RUNS env)
  scorer_max_workers: 2    # Maksimum paralel thread (DQG_SCORER_MAX_WORKERS env)
```

**Varsayılan Değerler** (`src/app/stages/score.py:30-31`):

```python
DEFAULT_SCORER_RUNS = 3
DEFAULT_SCORER_MAX_WORKERS = 3
```

### 4.3 Paralel Çalıştırma

`run_scorer_multi` fonksiyonu (`src/app/stages/score.py:176-207`), N adet `score_single` çağrısını `ThreadPoolExecutor` ile paralel olarak yürütür:

```python
def run_scorer_multi(client, revised_content, document_type, original_content,
                     n_runs=DEFAULT_SCORER_RUNS, max_workers=DEFAULT_SCORER_MAX_WORKERS):
    runs: list[Optional[dict]] = [None] * n_runs

    def _single_run(run_index: int) -> tuple[int, dict]:
        result = score_single(client, revised_content, document_type,
                              original_content, run_index=run_index)
        return run_index, result

    effective_workers = min(max_workers, n_runs)
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {executor.submit(_single_run, i): i for i in range(n_runs)}
        for future in as_completed(futures):
            run_index, result = future.result()
            runs[run_index] = result

    runs = [r for r in runs if r is not None]
    return runs
```

**Önemli Detaylar:**

- Her run bağımsız bir LLM çağrısıdır; aynı prompt, farklı rastgele sonuç
- `temperature=0.2` ile tutarlılık sağlanır ama sıfır varyans garantilenmez
- Başarısız run'lar filtrelenir (`runs = [r for r in runs if r is not None]`)
- Paralel çalıştırma, toplam süreyi yaklaşık olarak `n_runs / max_workers` katına indirir

### 4.4 Sonuç Toplama (Aggregation)

`aggregate_scores` fonksiyonu (`src/app/stages/score.py:210-271`) tüm run'ların sonuçlarını birleştirir:

**Boyut Skorları → Medyan:**

Her boyut için tüm run'lardan toplanan skorların **medyanı** (ortanca) alınır:

```python
for dim in dim_names:
    values = [getattr(run["dimension_scores"], dim, 0.0) for run in runs]
    median_scores[dim] = round(statistics.median(values), 2)
```

> **Neden ortalama (mean) değil, medyan?** Ortalama, uç değerlere (outlier) duyarlıdır. Bir run'ın anormalement düşük veya yüksek skor vermesi ortalama yanıltırken, medyan daha dayanıklıdır (robust).

**Varyans Hesabı:**

Her boyut için run'lar arası **varyans** hesaplanır. Varyans, skorlamanın güvenilirliğinin bir göstergesidir:

```python
if len(values) > 1:
    per_dim_variance[dim] = round(statistics.variance(values), 4)
else:
    per_dim_variance[dim] = 0.0
```

**Güven (Confidence) Skoru:**

Ortalama varyans üzerinden güven skoru türetilir:

```python
avg_variance = statistics.mean(per_dim_variance.values())
max_possible_variance = 25.0  # (10-0)^2 / 4 = max varyans
confidence = max(0.0, min(1.0, 1.0 - (avg_variance / max_possible_variance)))
```

- **Yüksek varyans → Düşük güven:** Run'lar birbiriyle tutarsız, skor şüpheli
- **Düşük varyans → Yüksek güven:** Run'lar tutarlı, skor güvenilir

**Güçlü Yönler ve Endişeler:**

- Tüm run'lardan toplanan `key_strengths` ve `remaining_concerns` listeleri, **frekans sıralamasına** göre birleştirilir
- En sık tekrar eden 5 madde korunur
- Bu sayede tüm run'ların katıldığı ortak değerlendirmeler öne çıkar

---

## 5. Promptfoo Entegrasyonu

### 5.1 Promptfoo Nedir?

[Promptfoo](https://github.com/promptfoo/promptfoo), LLM çıktılarını rubrik tabanlı değerlendirmeye tabi tutan açık kaynaklı bir test aracıdır. DQG, Promptfoo'yu **ikinci bir bağımsız doğrulama kaynağı** olarak kullanır.

### 5.2 Neden İkinci Bir Doğrulama?

LLM scorer, belirli bir model (örn. `strong_judge`) kullanır. Bu model belirli yanlılıklara sahip olabilir. Promptfoo, **farklı bir model** (örn. `fallback_general`) ile bağımsız bir değerlendirme yaparak:

- Tek model yanlılığını (model bias) azaltır
- Skor tutarlılığını doğrular
- Yanlış pozitif/negatif riskini düşürür

### 5.3 Çalışma Akışı

`PromptfooRunner` sınıfı (`src/app/integrations/promptfoo_runner.py:24-254`) şu adımları izler:

**Adım 1: Rubrik Yükleme**

Doküman türüne özel bir rubrik dosyası yüklenir:

```
config/promptfoo/rubrics/{document_type}.yaml
```

Dosya mevcut değilse, `generic.yaml` rubriği kullanılır. Rubrik, her boyut için değerlendirme kriterlerini tanımlar.

**Adım 2: Geçici Konfigürasyon Oluşturma**

Her çalıştırma için geçici bir promptfoo konfigürasyonu oluşturulur (`_build_eval_config`, satır 182-238):

```yaml
description: "Doc Quality Gate Evaluation"
providers:
  - id: openai:fallback_general
    config:
      basePath: <proxy_base_url>
      apiKey: <proxy_api_key>
prompts:
  - <geçici_prompt_dosyası>
tests:
  - assert:
      - type: llm-rubric
        value: <rubrik_içeriği>
        metric: correctness
        threshold: 0.5
      - type: llm-rubric
        metric: completeness
        threshold: 0.5
      # ... tüm 8 boyut için
```

**Adım 3: Promptfoo Çalıştırma**

```bash
npx promptfoo eval -c <config_file> --output output.json --no-cache
```

- Alt process olarak çalıştırılır
- 300 saniye zaman aşımı
- `returncode=100` → bazı assertion'lar başarısız, sonuçlar yine de parse edilir
- `returncode=0` → tüm assertion'lar başarılı

**Adım 4: Sonuç Parse Etme**

`parse_dimension_scores` fonksiyonu (satır 125-180), promptfoo çıktısını `DimensionScores` nesnesine dönüştürür:

- Assertion sonuçlarındaki `metric` ve `score` alanları eşleştirilir
- 0-1 arası skorlar 0-10 aralığına dönüştürülür (`score * 10.0`)
- Boyut isimleri esnek eşleştirme ile bulunur (örn. "risk awareness" → `risk_awareness`)

```python
dimension_map = {
    "correctness": "correctness",
    "completeness": "completeness",
    "implementability": "implementability",
    "consistency": "consistency",
    "edge_case_coverage": "edge case coverage",
    "edge case": "edge_case_coverage",
    "testability": "testability",
    "risk_awareness": "risk awareness",
    "risk": "risk_awareness",
    "clarity": "clarity",
}
```

### 5.4 LLM ve Promptfoo Skorlarını Birleştirme

`merge_scorer_and_promptfoo` fonksiyonu (`src/app/stages/score.py:274-332`):

**Ağırlıklar:**

```python
llm_weight = 0.6    # LLM scorer
pf_weight = 0.4     # Promptfoo
```

**Boyut Bazlı Birleştirme:**

```python
merged[dim] = round(llm_val * llm_weight + pf_val * pf_weight, 2)
```

**Uyum (Agreement) Kontrolü:**

İki scorer'ın 6.0 eşik üzerinde/altında ne kadar aynı fikirde olduğunu hesaplar:

```python
threshold = 6.0

for dim in dim_names:
    llm_val = getattr(llm_scores, dim, 0.0)
    pf_val  = getattr(promptfoo_scores, dim, 0.0)

    if (llm_val >= threshold) == (pf_val >= threshold):
        agree_dims += 1
```

**Uyum Etiketleri:**

| Oran | Etiket | Anlam |
|------|--------|-------|
| ≥ 7/8 (87.5%) | `agree` | İki scorer büyük ölçüde aynı fikirde |
| ≥ 5/8 (62.5%) | `partial` | Kısmi uyum, bazı boyutlarda farklı görüş |
| < 5/8 | `disagree` | Ciddi uyuşmazlık |

**Güven Ayarlaması:**

| Uyum Durumu | Güven Cezası |
|------------|-------------|
| `agree` | 0.00 (ceza yok) |
| `partial` | 0.08 |
| `disagree` | 0.15 |

Uyuşmazlık durumunda güven skoru düşürülür çünkü skorların güvenilirliği şüphelidir.

---

## 6. Meta Judge

### 6.1 Amaç

Meta Judge, **skorlamayı skorlayan** son kontrol mekanizmasıdır. Bir üst değerlendirici (meta-judge), scorer'ın sonuçlarının adil, aşırı iyimser veya aşırı kötümser olup olmadığını denetler.

**Neden gerekli?**

- LLM scorer belirli doküman türlerine karşı sistematik olarak yüksek/düşük skor verebilir
- Multi-run medyan, her run aynı yöne yanlıysa düzeltmez
- Promptfoo ile uyum yüksek olsa bile, her iki model de aynı hatayı yapıyor olabilir

### 6.2 Ne Zaman Çalışır?

Meta Judge, pipeline'da **score aşamasından sonra** çalışır:

```
... → score → meta_judge → report
```

`run_meta_judge` fonksiyonu (`src/app/stages/meta_judge.py:81-153`) çağrılır.

### 6.3 Girdileri

Meta Judge'e şu bilgiler sunulur:

| Girdi | Kaynak |
|-------|--------|
| Doküman türü | `document_type` |
| Boyut skorları | Scorecard'tan |
| Run sayısı | `scorer_run_count` |
| Skor varyansı | `scorer_score_variance` |
| Güven skoru | `confidence_in_scoring` |
| Promptfoo skorları | `promptfoo_dimension_scores` |
| Uyum etiketi | `promptfoo_agreement` |
| Revize doküman içeriği | İlk 8000 karakter |

### 6.4 Değerlendirme Kriterleri

Meta Judge üç ana kategoriye bakar:

**1. Aşırı İyimserlik (Over-Optimistic):**
- Skorlar 8.0 üzerinde ama dokümanda açık boşluklar var mı?
- Kritik/yüksek önem dereceli issue'lar göz ardı edilmiş mi?
- Güven skoru varyansa göre aşırı yüksek mü?

**2. Aşırı Kötümserlik (Over-Pessimistic):**
- Skorlar 5.0 altında ama doküman yeterli görünüyor mu?
- Küçük issue'lar aşırı ağırlıklandırılmış mı?
- Run'lar arası varyans medyanı yanıltıyor mu?

**3. Adillik (Fairness):**
- Skorlar doküman içeriğiyle tutarlı mı?
- Genel skor, dokümanın kalitesini temsil ediyor mu?

### 6.5 Karar (Verdict)

Meta Judge dört farklı karar döndürebilir:

| Verdict | Anlam |
|---------|-------|
| `fair` | Skorlar adil, düzeltme gerekmez |
| `over_optimistic` | Skorlar aşırı yüksek, düşürülmesi gerekebilir |
| `over_pessimistic` | Skorlar aşırı düşük, yükseltilmesi gerekebilir |
| `needs_adjustment` | Spesifik boyutlarda düzeltme gerekli |

### 6.6 Düzeltmeler (Adjustments)

Meta Judge, boyut skorlarına **±1.5 puana kadar** düzeltme uygulayabilir:

```python
max_adj = 1.5
for dim in dim_names:
    adj = parsed.get("adjustments", {}).get(dim, 0.0)
    adj = max(-max_adj, min(max_adj, float(adj)))
    if adj != 0.0:
        adjustments[dim] = adj
```

**Güven düzeltmesi:** ±0.10 aralığında:

```python
confidence_adj = parsed.get("confidence_adjustment", 0.0)
confidence_adj = max(-0.1, min(0.1, float(confidence_adj)))
```

### 6.7 Düzeltmelerin Uygulanması

`apply_meta_judge_adjustments` fonksiyonu (`src/app/stages/meta_judge.py:156-237`):

1. Her boyutun skoruna düzeltme eklenir, 0.0–10.0 aralığına kırpılır
2. Genel skor ağırlıklı ortalama ile yeniden hesaplanır
3. Blocking reasons yeniden değerlendirilir
4. `NextAction` (önerilen sonraki aksiyon) güncellenir
5. Güven skoru düzeltme ile güncellenir
6. Yeni Scorecard oluşturulur

**Örnek:**

```
# Orijinal skor
correctness: 8.5

# Meta judge düzeltmesi
correctness: -0.8

# Sonuç
correctness: 7.7
```

---

## 7. Threshold Konfigürasyonu

### 7.1 Konfigürasyon Yapısı

Threshold ayarları `config/thresholds.yaml` dosyasında tanımlanır (`src/app/config.py:182-220`):

```yaml
defaults:
  overall_threshold: 8.0
  critical_dimension_threshold: 6.0
  critical_dimensions:
    - correctness
    - completeness
    - implementability

per_type:
  feature_spec:
    overall_threshold: 8.0
    critical_dimension_threshold: 6.0
    dimension_weights:
      correctness: 1.5
      completeness: 1.5
      # ...
```

### 7.2 Parametreler

| Parametre | Tür | Varsayılan | Açıklama |
|-----------|-----|-----------|----------|
| `overall_threshold` | float | 8.0 | Genel skorun geçmesi için minimum değer |
| `critical_dimension_threshold` | float | 6.0 | Kritik boyutların geçmesi için minimum değer |
| `critical_dimensions` | list | [correctness, completeness, implementability] | Ekstra eşik kontrolü yapılan boyutlar |
| `dimension_weights` | dict | tümü 1.0 | Her boyutun genel skor hesabındaki ağırlığı |

### 7.3 Varsayılan Threshold'lar

| Doküman Türü | Overall Threshold | Critical Dim Threshold | Ağırlıklandırma |
|---------------|:-:|:-:|:-:|
| `feature_spec` | 8.0 | 6.0 | correctness 1.5, completeness 1.5, implementability 1.3, edge_case 1.2, testability 1.2 |
| `implementation_plan` | 8.0 | 6.0 | correctness 1.5, completeness 1.5, implementability 1.5, edge_case 1.3, testability 1.3, risk 1.2 |
| `architecture_change` | 8.0 | 6.0 | correctness 1.5, completeness 1.3, implementability 1.3, consistency 1.2, risk 1.5 |
| `refactor_plan` | 7.5 | 6.0 | correctness 1.5, implementability 1.5, risk 1.3 |
| `migration_plan` | 8.0 | 6.0 | correctness 1.5, completeness 1.5, edge_case 1.3, risk 1.5 |
| `incident_action_plan` | 7.5 | 6.0 | correctness 1.5, implementability 1.5, risk 1.5, clarity 1.2 |
| `custom` | 8.0 | 6.0 | Tümü eşit (1.0) |

> **Not:** `refactor_plan` ve `incident_action_plan` türleri için overall_threshold **7.5** olarak belirlenmiştir. Bunun nedeni, bu doküman türlerinde daha iteratif bir yaklaşımın kabul edilebilir olmasıdır.

### 7.4 Kritik Boyutlar (Critical Dimensions)

Varsayılan olarak şu üç boyut **kritik** kabul edilir:

1. **correctness** — Hatalı teknik bilgi her şeyi geçersiz kılar
2. **completeness** — Eksik gereksinimler uygulanamaz bir plan üretir
3. **implementability** — Uygulanamaz bir planın değerli olmaması

Bu boyutlardan herhangi birinin skoru `critical_dimension_threshold` (varsayılan: 6.0) altına düşerse, genel skor threshold'u geçse bile doküman **KALIR**.

### 7.5 Threshold Yükleme Mantığı

`load_threshold_config` fonksiyonu (`src/app/config.py:182-220`) şu sırayla çalışır:

1. `config/thresholds.yaml` dosyasını okur
2. `defaults` bölümünden varsayılan değerleri alır
3. `per_type` bölümünden doküman türüne özel değerleri alır (varsa)
4. Doküman türü bazlı değerler, varsayılanların üzerine yazar
5. `dimension_weights` için: varsayılan ağırlıklar (tümü 1.0) üzerine doküman türüne özel ağırlıklar eklenir

---

## 8. Scorecard Çıktısı

### 8.1 JSON Yapısı

Scorecard, `src/app/schemas.py:105-120` içinde tanımlanan Pydantic modelidir. Pipeline'ın nihai çıktısıdır:

```json
{
  "dimension_scores": {
    "correctness": 8.2,
    "completeness": 7.5,
    "implementability": 8.0,
    "consistency": 9.0,
    "edge_case_coverage": 7.0,
    "testability": 7.8,
    "risk_awareness": 6.5,
    "clarity": 8.5
  },
  "overall_score": 7.85,
  "blocking_reasons": [
    "Overall score 7.85 below threshold 8.0"
  ],
  "unresolved_critical_issues_count": 1,
  "recommended_next_action": "revise_again",
  "passed": false,
  "key_strengths": [
    "Clear API endpoint definitions",
    "Good error handling strategy",
    "Well-structured implementation steps"
  ],
  "remaining_concerns": [
    "Missing rollback plan for database migration",
    "Edge case: concurrent access not addressed"
  ],
  "overall_assessment": "Good quality document with minor gaps in risk coverage",
  "confidence_in_scoring": 0.87,
  "scorer_run_count": 3,
  "scorer_score_variance": 0.45,
  "promptfoo_dimension_scores": {
    "correctness": 8.0,
    "completeness": 7.2,
    "implementability": 7.8,
    "consistency": 8.5,
    "edge_case_coverage": 6.8,
    "testability": 7.5,
    "risk_awareness": 6.2,
    "clarity": 8.0
  },
  "promptfoo_agreement": "agree",
  "meta_judge_result": {
    "verdict": "fair",
    "adjustments": {},
    "reasoning": "Scores align well with document content...",
    "confidence_adjustment": 0.0
  }
}
```

### 8.2 Alan Açıklamaları

| Alan | Tür | Açıklama |
|------|-----|----------|
| `dimension_scores` | DimensionScores | 8 boyutun her biri için skor (0.0–10.0) |
| `overall_score` | float | Ağırlıklı ortalama genel skor (0.0–10.0) |
| `blocking_reasons` | list[str] | Geçmeyi engelleyen nedenlerin listesi |
| `unresolved_critical_issues_count` | int | Çözülmemiş kritik/yüksek issue sayısı |
| `recommended_next_action` | NextAction | Önerilen sonraki aksiyon (implement, revise_again, human_review) |
| `passed` | bool | Doküman geçti mi (true/false) |
| `key_strengths` | list[str] | Dokümanın güçlü yönleri (en fazla 5 madde) |
| `remaining_concerns` | list[str] | Hâlâ mevcut endişeler (en fazla 5 madde) |
| `overall_assessment` | str | Kısa nitel değerlendirme özeti |
| `confidence_in_scoring` | float | Skorlamaya olan güven (0.0–1.0) |
| `scorer_run_count` | int | Kaç kez skorlandığı |
| `scorer_score_variance` | float | Run'lar arası ortalama varyans |
| `promptfoo_dimension_scores` | DimensionScores? | Promptfoo'dan gelen bağımsız boyut skorları (null olabilir) |
| `promptfoo_agreement` | str? | İki scorer arası uyum (agree, partial, disagree) |
| `meta_judge_result` | MetaJudgeResult? | Meta-Judge karar ve düzeltmeleri (null olabilir) |

### 8.3 MetaJudgeResult Alt Yapısı

```json
{
  "verdict": "fair | over_optimistic | over_pessimistic | needs_adjustment",
  "adjustments": {
    "risk_awareness": 0.8,
    "edge_case_coverage": -0.5
  },
  "reasoning": "Açıklama metni",
  "confidence_adjustment": -0.05
}
```

| Alan | Açıklama |
|------|----------|
| `verdict` | Meta-judge kararı |
| `adjustments` | Boyut bazlı düzeltme değerleri (sadece sıfır olmayanlar) |
| `reasoning` | Kararın gerekçesi |
| `confidence_adjustment` | Güven skoruna uygulanacak düzeltme (-0.1 ile +0.1 arası) |

---

## 9. Geçme/Kalma Kriterleri

### 9.1 Üç Koşul

Bir dokümanın **GEÇMESİ (PASS)** için şu üç koşulun **hepsinin** sağlanması gerekir:

#### Koşul 1: Genel Skor Eşiği

```
overall_score >= overall_threshold
```

- Varsayılan: `8.0`
- `refactor_plan` ve `incident_action_plan` için: `7.5`

#### Koşul 2: Kritik Boyut Eşiği

```
her critical_dimension için: dim_score >= critical_dimension_threshold
```

- Kritik boyutlar: `correctness`, `completeness`, `implementability`
- Eşik: `6.0`
- Bu boyutlardan **herhangi biri** 6.0 altındaysa doküman kalır

#### Koşul 3: Çözülmemiş Kritik Issue

```
unresolved_critical_issues_count == 0
```

- Validation aşamasında VALID olarak onaylanmış ve otomatik uygulanmamış (should_auto_apply=false) kritik/yüksek önem dereceli issue kalmamış olmalıdır

### 9.2 Gate Logic

`_compute_gate_logic` fonksiyonu (`src/app/stages/score.py:63-110`) üç koşulu sırayla kontrol eder:

```python
passed = overall_score >= threshold_config.overall_threshold
# VEYA blocking_reasons boşsa
```

**Blocking Reasons Oluşturma Kuralları:**

| Tetikleyici | Blocking Reason Metni |
|-------------|----------------------|
| `overall_score < threshold` | `"Overall score {score} below threshold {threshold}"` |
| `critical_dim < critical_threshold` | `"Critical dimension '{dim}' score {score} below threshold {threshold}"` |
| `unresolved_critical > 0` | `"{count} unresolved critical/high issues remain"` |

`passed` değişkeni **sadece** `overall_score >= overall_threshold` kontrolüne bağlıdır. Ancak `blocking_reasons` listesi tüm ihlalleri raporlar.

### 9.3 Önerilen Sonraki Aksiyon (NextAction)

Skorun eşiğe olan uzaklığına göre üç farklı aksiyon önerilir:

| Aksiyon | Koşul | Açıklama |
|---------|-------|----------|
| `IMPLEMENT` | `overall_score >= threshold` | Doküman geçti, uygulamaya geçilebilir |
| `REVISE_AGAIN` | `threshold - 2.0 <= overall_score < threshold` (eşik yakını) | Skor eşiğe yakın, küçük düzeltmelerle geçebilir |
| `HUMAN_REVIEW` | `overall_score < threshold - 2.0` | Skor çok düşük, insan incelemesi gerekli |

**Örnek (threshold = 8.0):**

| Skor | Aksiyon |
|------|---------|
| 8.5 | `IMPLEMENT` |
| 8.0 | `IMPLEMENT` |
| 7.8 | `REVISE_AGAIN` |
| 6.5 | `REVISE_AGAIN` |
| 5.9 | `HUMAN_REVIEW` |
| 3.0 | `HUMAN_REVIEW` |

### 9.4 Tam Karar Akışı

```
                    ┌─────────────────────────┐
                    │   Scorecard Hazır mı?    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  Meta-Judge Uygulandı mı?│
                    └────┬───────────┬────────┘
                    Evet │           │ Hayır
                         │           │
                         ▼           ▼
              ┌──────────────┐  ┌───────────────────┐
              │ Final Score  │  │ Meta-Judge'ı      │
              │ Hazır        │  │ Çalıştır          │
              └──────┬───────┘  └───────────────────┘
                     │
                     ▼
         ┌────────────────────────┐
         │ overall_score >= 8.0?  │
         └─────┬──────────┬───────┘
           Evet│          │Hayır
               │          │
               ▼          ▼
     ┌──────────────┐  ┌──────────────────────────┐
     │ Kritik boyut │  │ overall_score >= 6.0?     │
     │ kontrolü     │  └─────┬──────────┬──────────┘
     └──┬───────┬───┘    Evet│          │Hayır
    Geçti│       │Kaldı      │          │
        │       │           ▼          ▼
        │       │    ┌───────────┐ ┌────────────┐
        │       │    │REVISE_AGAIN│ │HUMAN_REVIEW│
        │       │    └───────────┘ └────────────┘
        ▼       ▼
  ┌─────────┐ ┌────────────┐
  │ IMPLEMENT│ │ FAIL+Reason│
  └─────────┘ └────────────┘
```

### 9.5 Başarılı Bir Sonuç Örneği

```json
{
  "passed": true,
  "overall_score": 8.4,
  "blocking_reasons": [],
  "recommended_next_action": "implement",
  "confidence_in_scoring": 0.92,
  "scorer_run_count": 3,
  "scorer_score_variance": 0.15,
  "promptfoo_agreement": "agree",
  "meta_judge_result": {
    "verdict": "fair"
  }
}
```

### 9.6 Başarısız Bir Sonuç Örneği

```json
{
  "passed": false,
  "overall_score": 7.2,
  "blocking_reasons": [
    "Overall score 7.2 below threshold 8.0",
    "Critical dimension 'completeness' score 5.8 below threshold 6.0",
    "2 unresolved critical/high issues remain"
  ],
  "recommended_next_action": "revise_again",
  "confidence_in_scoring": 0.71,
  "scorer_run_count": 3,
  "scorer_score_variance": 0.85,
  "promptfoo_agreement": "partial",
  "meta_judge_result": {
    "verdict": "over_optimistic",
    "adjustments": {
      "completeness": -0.8,
      "edge_case_coverage": -0.5
    },
    "reasoning": "Document lacks rollback plan and error handling details. Scores were inflated for completeness.",
    "confidence_adjustment": -0.08
  }
}
```

---

## Ek: Model Atamaları

Skorlama aşamasında kullanılan model alias'ları `config/app.yaml` içinde tanımlanır:

| Aşama | Model Alias | Açıklama |
|-------|------------|----------|
| `scorer` | `strong_judge` | Ana skorlama modeli |
| `scorer_promptfoo` | `fallback_general` | Promptfoo bağımsız değerlendirme modeli |
| `meta_judge` | `strong_judge` | Meta-Judge değerlendirme modeli |

Bu alias'lar, LiteLLM proxy'sindeki model gruplarına karşılık gelir ve `model_routing.yaml` ile fiziksel model isimlerine çözülür.

---

## Ek: Scorer Prompt Şablonu

Skorlama için kullanılan prompt şablonu `config/prompts/scorer.md` dosyasındadır. Şablon şu placeholder'ları kullanır:

| Placeholder | Değer |
|-------------|-------|
| `{{document_type}}` | Doküman türü (örn. `feature_spec`) |
| `{{document_content}}` | Revize edilmiş doküman içeriği |
| `{{original_content}}` | Orijinal doküman içeriği |
| `{% if original_content %}...{% endif %}` | Orijinal doküman varsa göster |
| `{% if issues_addressed %}...{% endif %}` | Ele alınan issue'lar varsa göster |

Scorer'dan beklenen JSON çıktı formatı:

```json
{
  "dimension_scores": {
    "correctness": 0,
    "completeness": 0,
    "implementability": 0,
    "consistency": 0,
    "edge_case_coverage": 0,
    "testability": 0,
    "risk_awareness": 0,
    "clarity": 0
  },
  "overall_assessment": "Kısa değerlendirme özeti",
  "key_strengths": ["Güçlü yön 1", "Güçlü yön 2"],
  "remaining_concerns": ["Endişe 1", "Endişe 2"],
  "confidence_in_scoring": 0.0
}
```
