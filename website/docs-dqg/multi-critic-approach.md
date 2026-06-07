---
sidebar_position: 4
title: Multi-Critic Yaklasimi
---

# Çoklu Critic Yaklaşımı (Multi-Critic Approach)

Doc Quality Gate (DQG), belge kalite analizinde tek bir incelemeci yerine **birden fazla bağımsız critic** kullanır. Bu sayede yanlılık azaltılır, kapsama oranı artar ve hatalı pozitifler filtrelenir.

---

## İçindekiler

1. [Neden Birden Fazla Critic?](#1-neden-birden-fazla-critic)
2. [Critic A vs Critic B](#2-critic-a-vs-critic-b)
3. [Multi-Run Mekanizması](#3-multi-run-mekanizması)
4. [Critic Judge](#4-critic-judge)
5. [Bakış Açıları (Perspectives)](#5-bakış-açıları-perspectives)
6. [Model Dağılımı](#6-model-dağılımı)
7. [Paralel Çalışma](#7-paralel-çalışma)
8. [Sonuç Kalitesi](#8-sonuç-kalitesi)
9. [Örnek Çıktı](#9-örnek-çıktı)

---

## 1. Neden Birden Fazla Critic?

### Tek İncelemeci Problemi

Tek bir LLM incelemecisine dayalı sistemler şu sorunlara sahiptir:

- **Tek bakış açısı yanıltması**: Bir model belirli hata kategorilerine karşı "kör" kalabilir. Örneğin, teknik doğrulukta mükemmel olan bir model operasyonel riskleri gözden kaçırabilir.
- **Rastgelelik (Stochastic variation)**: Aynı prompt ile aynı modele iki farklı çağrı yapıldığında farklı sorunlar bulunabilir. Tek çalıştırma ile bazı sorunlar kaçınılmaz olarak gözden kaçar.
- **Yanılık (Bias)**: Tek bir incelemeci, belgeyi kendi eğilimlerine göre değerlendirir. Örneğin, her zaman "daha fazla test coverage" önerebilir ya da her zaman mimari sorunları öne çıkarabilir.
- **Düşük kesinlik (Precision)**: Tek çalıştırmada üretilen sorunlar arasında gereksiz (nitpick), aşırı şişirilmiş (exaggerated) veya yanlış pozitif (false positive) sayısı yüksek olabilir.

### Çoklu İncelemeci Avantajı

DQG bu sorunları iki temel mekanizmayla çözer:

| Mekanizma | Açıklama |
|-----------|----------|
| **İki farklı critic profili** | Critic A ve Critic B, farklı uzmanlık alanlarına ve bakış açılarına sahip incelemecilerdir. |
| **Çoklu çalıştırma (multi-run)** | Her critic, aynı belgeyi birden fazla kez inceler (`n_runs` parametresi). |

Bu iki mekanizmanın birleşimi şu sonuçları doğurur:

- **Yanlılık azaltımı**: Farklı bakış açıları birbirini tamamlar ve dengeler.
- **Kapsama artışı**: Her çalıştırma ve her critic farklı sorunlar yakalayabilir; toplam kapsama oranı artar.
- **Filtreleme doğruluğu**: Birden fazla çalıştırmada tekrar eden sorunlar yüksek olasılıkla gerçek sorunlardır. Tek seferde görülen sorunlar şüpheyle karşılanır.
- **Tutarlılık**: Consensus (oy birliği) skorları ile güvenilir sorunları güvenilmezlerden ayırmak mümkündür.

---

## 2. Critic A vs Critic B

### Critic A — Kıdemli Staff Mühendis

Critic A, **teknik kusurlar** arayan bir "senior staff engineer" rolündedir. Odak noktası belgenin içsel tutarlılığı ve teknik doğruluğudur.

**Prompt kişiliği** (`config/prompts/critic_a.md`):

> *"You are Critic A — a senior staff engineer reviewing a software implementation document for technical defects. Your job is to find problems. Be thorough, specific, and unforgiving."*

**Odak kategorileri:**

| Kategori | Açıklama |
|----------|----------|
| `contradiction` | Belgenin bir bölümünde söylenen şeyin başka bir bölümünde çelişmesi |
| `incorrect_assumption` | Yanlış veya doğrulanmamış teknik varsayımlar |
| `missing_requirement` | Problem tarafından ima edilen ancak belirtilmeyen gereksinimler |
| `incomplete_logic` | Boşlukları veya eksik adımları olan mantık zincirleri |
| `sequencing_gap` | Sırası yanlış veya önkoşulları eksik adımlar |
| `dependency_gap` | Gerekli ancak belirtilmemiş dış bağımlılıklar |

**Önem (Severity) tanımları:**

| Seviye | Critic A için anlamı |
|--------|---------------------|
| `critical` | Uygulama başarısızlığına veya veri kaybına yol açacak sorunlar |
| `high` | Önemli yeniden çalışma gerektirecek sorunlar |
| `medium` | Risk veya kafa karışıklığı ekleyen sorunlar |
| `low` | Küçük kalite iyileştirmeleri |

### Critic B — Kıdemli Mühendislik Yöneticisi

Critic B, **pratik uygulanabilirlik ve operasyonel güvenlik** arayan bir "senior engineering manager" rolündedir. Odak noktası belgenin gerçek dünyada çalışıp çalışmayacağıdır.

**Prompt kişiliği** (`config/prompts/critic_b.md`):

> *"You are Critic B — a senior engineering manager reviewing a software implementation document for practical implementability and operational safety. Your job is to find problems that would surface during implementation, testing, deployment, or production operation. Be pragmatic and production-focused."*

**Odak kategorileri:**

| Kategori | Açıklama |
|----------|----------|
| `implementability` | Bir geliştirici bu belgeden yalnızca başına bunu gerçekten inşa edebilir mi? |
| `testability` | Uygulama, açıklananlara dayanarak düzgün şekilde test edilebilir mi? |
| `rollout_safety` | Dağıtım/rollout stratejisi güvenli mi? |
| `observability` | İzleme, loglama ve uyarı değerlendirmeleri var mı? |
| `edge_case` | Sınır koşulları, hata yolları ve olağandışı girdiler ele alınmış mı? |
| `migration_risk` | Veri geçiş riskleri ve geri alma planları yeterli mi? |
| `operational_risk` | Bu üretimde işletilebilir olacak mı? Runbook gerekli mi? |
| `maintainability` | Bu uzun vadede sürdürülebilir olacak mı? |

**Önem (Severity) tanımları:**

| Seviye | Critic B için anlamı |
|--------|---------------------|
| `critical` | Üretim olaylarına veya veri kaybına yol açacak sorunlar |
| `high` | Önemli operasyonel sorunlara yol açacak sorunlar |
| `medium` | Operasyonel risk ekleyen sorunlar |
| `low` | Küçük kalite iyileştirmeleri |

### Karşılaştırma Tablosu

| Özellik | Critic A | Critic B |
|---------|----------|----------|
| **Rol** | Senior Staff Engineer | Senior Engineering Manager |
| **Perspektif** | Teknik doğruluk | Operasyonel uygulanabilirlik |
| **Baktığı yer** | Belgenin içi (tutarlılık, mantık) | Belgenin dışı (deploy, test, prod) |
| **Hedef** | Kusur bulmak | Gerçek dünya riski bulmak |
| **Kişilik** | Thorough, specific, unforgiving | Pragmatic, production-focused |
| **Kategori sayısı** | 6 | 8 |
| **Model alias** | `cheap_large_context` | `cheap_large_context_alt` |
| **Kaynak etiketi** | `critic_a` | `critic_b` |
| **ID ön eki** | `A-` | `B-` |

---

## 3. Multi-Run Mekanizması

### `n_runs` Parametresi

Her critic, aynı belgeyi **birden fazla kez** çalıştırır. Bu, `n_runs` parametresi ile kontrol edilir.

**Yapılandırma** (`config/app.yaml`):

```yaml
pipeline:
  critic_runs: ${DQG_CRITIC_RUNS:2}
```

- **Varsayılan değer**: `2` (ortam değişkeni `DQG_CRITIC_RUNS` ile geçersiz kılınabilir)
- **Kod içi varsayılan**: `DEFAULT_NUM_RUNS = 3` (`critic.py` dosyasında tanımlı)

### Neden Birden Fazla Çalıştırma?

LLM'ler doğası gereği **stokastiktir**. Aynı prompt ve aynı girdi ile bile farklı çıktılar üretebilirler. Bu özellik bir hata değil, çoklu çalıştırma yaklaşımında bir avantajdır:

1. **Farklı sorunlar yakalanır**: Her çalıştırmada model farklı "dikkat noktalarına" odaklanabilir. Çalıştırma 1'de kaçırılan bir sorun, çalıştırma 2'de bulunabilir.
2. **Güvenilirlik ölçülür**: Birden fazla çalıştırmada tekrar eden sorunlar gerçek sorunlardır. Tek seferde görülen sorunlar düşük güvenilirliğe sahiptir.
3. **Yanlış pozitifler filtrelenir**: Rastgele üretilen aşırı şişirilmiş veya gereksiz sorunlar genellikle sadece bir çalıştırmada görünür.

### Sonuçların Toplanması

Her çalıştırma bağımsız olarak sonuç üretir. `run_critic_multi` fonksiyonu her çalıştırmanın sonucunu sıralı bir listede saklar:

```python
# critic.py — run_critic_multi fonksiyonu
runs: list[list[Issue]] = [None] * n_runs
```

Dönüş değeri `list[list[Issue]]` biçimindedir. Örneğin `n_runs=3` için:

```
runs = [
    [Issue(...), Issue(...), ...],  # Run 0 — 5 issue bulundu
    [Issue(...), Issue(...), ...],  # Run 1 — 4 issue bulundu
    [Issue(...), Issue(...), ...],  # Run 2 — 6 issue bulundu
]
```

### Issue ID Şeması

Her çalıştırmada üretilen issue'lar, çalıştırma indeksini içeren bir ID şemasına sahiptir:

```
{prefix}-{run_index}-{sıra_numarası}
```

Örnekler:

| Critic | Run | Issue | ID |
|--------|-----|-------|----|
| Critic A | Run 0 | 1. issue | `A-0-001` |
| Critic A | Run 0 | 2. issue | `A-0-002` |
| Critic A | Run 1 | 1. issue | `A-1-001` |
| Critic B | Run 0 | 1. issue | `B-0-001` |

Bu şema, Critic Judge'ın hangi issue'nun hangi çalıştırmadan geldiğini takip etmesini sağlar.

### Gecikme Mekanizması

Çalıştırmalar arası gecikme, API rate limitlerine uyum sağlamak için kullanılır:

```yaml
# config/app.yaml
pipeline:
  critic_delay_seconds: ${DQG_CRITIC_DELAY:2}
```

- **Varsayılan**: 2 saniye
- Her çalıştırma (ilk hariç) başlamadan önce `delay_seconds` kadar bekler
- Paralel çalıştırmalarda bile her thread kendi gecikmesini uygular

```python
# critic.py — _single_run fonksiyonu
if run_index > 0 and delay_seconds > 0:
    time.sleep(delay_seconds)
```

---

## 4. Critic Judge

### Genel Bakış

Critic Judge, **birden fazla bağımsız inceleme çalıştırmasının sonuçlarını tek bir yüksek kaliteli, yinelenenlerden arındırılmış issue listesine dönüştüren** bir "senior principal engineer" rolündedir.

**Prompt kişiliği** (`config/prompts/critic_judge.md`):

> *"You are a Critic Judge — a senior principal engineer tasked with consolidating multiple independent review runs of the same document."*

### Sorumlulukları

Critic Judge beş temel sorumluluğa sahiptir:

#### 4.1 Benzer Issue'ları Gruplama

Tüm çalıştırmalar arasında, aynı temel sorunu farklı kelimelerle açıklayan issue'lar tek bir grup altında birleştirilir. Örneğin:

- Run 0: *"API endpoint tanımlanmamış"*
- Run 1: *"REST API spesifikasyonu eksik"*
- Run 2: *"Endpoint route'ları belgede yok"*

→ Bunlar tek bir issue olarak gruplandırılır.

#### 4.2 Consensus (Uzlaşı) Değerlendirmesi

Her grubun kaç çalıştırma tarafından tanındığını sayarak güvenilirlik ölçer:

| Consensus | Güvenilirlik | Eylem |
|-----------|--------------|-------|
| `n/n` (Tam uzlaşı) | Neredeyse kesinlikle gerçek bir sorun | Koru |
| `2/n` (Çoğunluk) | Çok büyük olasılıkla gerçek bir sorun | Koru |
| `1/n` (Azınlık) | Kritik değerlendirme gerekli | Dikkatli değerlendir |

Azınlık durumunda Judge şunları sorar:
- Diğerlerinin kaçırdığı gerçek bir benzersiz görüş mü? → **Koru**
- Aşırı şişirilmiş, önemsiz veya yanlış pozitif mi? → **Reddet**
- Kanıt'ın desteklemediği kadar yüksek bir severity mi? → **Severity'yi düşür**

#### 4.3 Aşırı Şişirilmiş / Gereksiz / Fazla Issue'ları Tespit Etme

Judge şu issue türlerini filtreler:

| Tür | Açıklama | Örnek |
|-----|----------|-------|
| **Exaggerated** | Severity şişirilmiş | Küçük bir stil sorunu için "critical" denmesi |
| **Unnecessary** | Nitpick veya gerçek sorun olmayan | "Belgede daha fazla emoji olabilir" |
| **Excessive / Over-splitting** | Bir sorun 5 ayrı issue'ya bölünmüş | Ayrıca ayrı issue'lar olarak sayaç artırma |
| **Redundant** | Aynı grupta biraz farklı kelimelerle tekrar | Aynı endişenin hafifçe farklı ifadesi |

#### 4.4 Eksik Sorunları Tespit Etme

İki veya daha fazla çalıştırma toplu olarak bir sorun alanını ima ediyorsa ama hiçbiri açıkça belirtmiyorsa, Judge bunu yeni bir issue olarak işaretler:

- `run_origins`: `["inferred"]`
- `judge_decision`: `"inferred"`
- Severity: Judge'ın mühendislik yorumuna göre belirlenir

#### 4.5 Severity Ayarlama

| Consensus | Severity kuralı |
|-----------|----------------|
| Tam uzlaşı | Orijinal severity korunur (birden fazla run daha yüksek severity işaretlediyse yükseltilebilir) |
| Çoğunluk | En yaygın severity kullanılır |
| Azınlık (korunan) | "medium" severity'yi geçemez (kanıtlar bunu zorlamıyorsa) |

### Girdi/Çıktı Akışı

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Critic A    │     │  Critic B    │     │              │
│  n_runs=3    │     │  n_runs=3    │     │              │
│              │     │              │     │              │
│  Run 0 ─────┼────►│              │     │              │
│  Run 1 ─────┼────►│              │     │              │
│  Run 2 ─────┼────►│              │     │              │
└─────────────┘     │              │     │              │
                    │  Run 0 ─────┼────►│              │
                    │  Run 1 ─────┼────►│              │
                    │  Run 2 ─────┼────►│              │
                    └─────────────┘     │              │
                                        │              │
                    ┌─────────────┐     │  Final       │
                    │ Critic Judge│     │  Issues      │
                    │ (Critic A   │     │  List        │
                    │  runs)──────┼────►│              │
                    └─────────────┘     │              │
                                        │              │
                    ┌─────────────┐     │              │
                    │ Critic Judge│     │              │
                    │ (Critic B   │     │              │
                    │  runs)──────┼────►│              │
                    └─────────────┘     └──────────────┘
```

Her critic için **ayrı bir Judge çağrısı** yapılır. Yani Critic A'nın 3 çalıştırması kendi Judge'ına, Critic B'nin 3 çalıştırması kendi Judge'ına gider.

### Judge Çıktı Şeması

Judge'ın ürettiği her issue şu alanları içerir:

```json
{
  "title": "Kısa açıklayıcı başlık",
  "severity": "critical|high|medium|low",
  "category": "<orijinal kategori>",
  "rationale": "Birleştirilmiş gerekçe",
  "evidence_quote": "En iyi kanıt alıntısı (herhangi bir çalıştırmadan)",
  "affected_section": "Bölüm veya konum",
  "proposed_fix": "Özel düzeltme önerisi",
  "consensus_score": 0.67,
  "run_origins": ["run_0", "run_2"],
  "judge_decision": "keep"
}
```

**Özel alanlar:**

| Alan | Açıklama |
|------|----------|
| `consensus_score` | Sorunu tanıyan çalıştırma oranı (örn. 3 run'da 2'si → 0.67, 3/3 → 1.0, 1/3 → 0.33) |
| `run_origins` | Hangi çalıştırmalar bu sorunu buldu (örn. `["run_0", "run_2"]`). Inferred issue'lar için `["inferred"]` |
| `judge_decision` | Sorunun nihai kararı |

**Judge kararları:**

| Karar | Anlamı |
|-------|--------|
| `keep` | Gerçekten anlamlı bir sorun, nihai listeye dahil edilir |
| `rejected_exaggerated` | Aşırı şişirildiği için çıkarıldı |
| `rejected_unnecessary` | Nitpick veya gerçek sorun olmadığı için çıkarıldı |
| `rejected_redundant` | Grup içindeki tekrar olduğu için çıkarıldı |
| `inferred` | Çalıştırma sonuçlarından çıkarılan yeni bir sorun |

> **Önemli**: Judge, hem korunan hem de reddedilen tüm issue'ları çıktı olarak verir. Bu, aşağı akış tüketicilerin neyin filtrelendiğini ve nedenini görmesini sağlar. Nihai listede yalnızca `judge_decision: "keep"` ve `judge_decision: "inferred"` olanlar kullanılır.

### Model ve Parametreler

Judge, critic'lerden **farklı bir model** ve **daha düşük sıcaklık** kullanır:

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| Model alias | `critic_judge` → `cheap_large_context | Judge'ın kendi model alias'ı |
| Temperature | `0.2` | Critic'lerden daha düşük (0.3), daha deterministik çıktı |
| Max tokens | `16384` | Critic'lerden daha yüksek (8192), çünkü tüm çalıştırma sonuçlarını işlemeli |
| Stage etiketi | `critic_{critic_name}_judge` | Loglama için |

---

## 5. Bakış Açıları (Perspectives)

### Nasıl Tamamlarlar?

Critic A ve Critic B, belgeyi birbirini tamamlayan iki farklı ışık açısından inceler:

```
                    ┌───────────────────────┐
                    │    Uygulama Belgesi    │
                    └───────────┬───────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
        ┌───────▼───────┐       │       ┌───────▼───────┐
        │   Critic A    │       │       │   Critic B    │
        │               │       │       │               │
        │  "Bu belge    │       │       │  "Bu belge    │
        │   kendisiyle  │       │       │   gerçek      │
        │   tutarlı mı?"│       │       │   dünyada     │
        │               │       │       │   çalışır mı?"│
        └───────┬───────┘       │       └───────┬───────┘
                │               │               │
                ▼               │               ▼
        İçsel kusurlar         │        Dışsal riskler
        • Çelişkiler           │        • Uygulanabilirlik
        • Mantık boşlukları    │        • Test edilebilirlik
        • Eksik gereksinimler  │        • Deploy güvenliği
        • Yanlış varsayımlar   │        • Operasyonel risk
                │               │               │
                └───────────────┼───────────────┘
                                │
                        ┌───────▼───────┐
                        │  Kapsamlı     │
                        │  Sorun Listesi│
                        └───────────────┘
```

### Kategori Kesişim Matrisi

| | Contradiction | Inc. Assumption | Missing Req. | Inc. Logic | Seq. Gap | Dep. Gap |
|---|---|---|---|---|---|---|
| **Implementability** | ◐ | ◐ | ● | ● | ◐ | ● |
| **Testability** | | | ● | ● | | ● |
| **Rollout Safety** | | ◐ | | | ● | ● |
| **Observability** | | | ● | | | ● |
| **Edge Case** | | ● | ● | ● | | |
| **Migration Risk** | | ● | ● | | ◐ | ● |
| **Operational Risk** | | ● | ● | | | ● |
| **Maintainability** | ◐ | | ● | ● | | |

- ● = Doğrudan kesişim (her iki critic de yakalayabilir)
- ◐ = Dolaylı kesişim (bir critic yakalayıp diğerini tetikleyebilir)
- Boş = Bağımsız kategoriler

Bu matris, iki critic'in kategorilerinin birbirini nasıl tamamladığını gösterir. Critic A'nın bulduğu bir `missing_requirement` genellikle Critic B'nin `implementability` veya `testability` kategorilerini de etkiler.

---

## 6. Model Dağılımı

### Model Alias Yapılandırması

`config/app.yaml` dosyasındaki model alias tanımları:

```yaml
model_aliases:
  critic_a: cheap_large_context
  critic_b: cheap_large_context_alt
  critic_judge: cheap_large_context
```

### Model Seçim Mantığı

| Bileşen | Alias | Açıklama |
|---------|-------|----------|
| **Critic A** | `cheap_large_context` | Maliyet etkin, büyük bağlam penceresi olan model |
| **Critic B** | `cheap_large_context_alt` | Farklı bir sağlayıcı/model ailesi, azaltılmış sağlayıcı yanılbilirliği |
| **Critic Judge** | `cheap_large_context` | Critic A ile aynı model ailesi, ancak daha düşük sıcaklıkla |

### Neden Farklı Modeller?

Critic A ve Critic B'nin **farklı model alias'ları** kullanmasının nedenleri:

1. **Sağlayıcı çeşitliliği (Provider diversity)**: `cheap_large_context` ve `cheap_large_context_alt` muhtemelen farklı LLM sağlayıcılarına işaret eder. Farklı sağlayıcılar farklı eğitim verileri ve farklı güçlü/zayıf yönleri vardır.
2. **Yanılılık azaltımı**: Aynı model ailesinin her iki critic için kullanılması, modele özgü sistemik yanılgıların her iki incelemeyi de etkilemesine yol açabilir.
3. **Kapsama artışı**: Farklı modeller, farklı hata türlerini farklı oranlarda yakalayabilir.

### Model Parametre Karşılaştırması

| Parametre | Critic A / B | Critic Judge |
|-----------|-------------|-------------|
| Temperature | 0.3 | 0.2 |
| Max tokens | 8192 | 16384 |
| System prompt | "You are a technical document reviewer..." | "You are a Critic Judge..." |
| Girdi | Belge içeriği + critic prompt şablonu | Tüm çalıştırma sonuçları + belge + judge prompt şablonu |

Judge'ın daha düşük sıcaklık (0.2) kullanmasının nedeni, birleştirme ve filtreleme kararlarının daha tutarlı ve deterministik olması gerektiğidir. Critic'ler ise biraz daha yüksek sıcaklıkla (0.3) çalışarak her çalıştırmada farklı açılardan yaklaşabilirler.

### LiteLLM Proxy Entegrasyonu

Tüm model çağrıları `LiteLLMClient` üzerinden yapılır:

```python
# critic.py
model = client.resolve_model(model_stage)
response = client.chat_completion(
    model=model,
    messages=messages,
    temperature=0.3,
    max_tokens=8192,
    stage=f"critic_{pass_name}_run{run_index}",
)
```

```python
# critic_judge.py
model = client.resolve_model("critic_judge")
response = client.chat_completion(
    model=model,
    messages=messages,
    temperature=0.2,
    max_tokens=16384,
    stage=f"critic_{critic_name}_judge",
)
```

`client.resolve_model()` çağrısı, stage adını (`critic_a`, `critic_b`, `critic_judge`) gerçek model adına çevirir. Bu, LiteLLM proxy yapılandırmasında tanımlıdır.

---

## 7. Paralel Çalışma

### ThreadPoolExecutor Kullanımı

DQG, critic'lerin çoklu çalıştırmalarını paralel olarak yürütmek için `concurrent.futures.ThreadPoolExecutor` kullanır.

```python
# critic.py — run_critic_multi fonksiyonu
effective_workers = min(max_workers, n_runs)
with ThreadPoolExecutor(max_workers=effective_workers) as executor:
    futures = {executor.submit(_single_run, i): i for i in range(n_runs)}
    for future in as_completed(futures):
        run_index, issues = future.result()
        runs[run_index] = issues
```

### Yapılandırma

```yaml
# config/app.yaml
pipeline:
  critic_max_workers: ${DQG_CRITIC_WORKERS:3}
```

- **Varsayılan**: 3 çalışan thread
- `effective_workers = min(max_workers, n_runs)` — gereksiz thread oluşturmaz

### Paralel Çalışma Akışı

```
n_runs = 3, max_workers = 3, delay_seconds = 2

Zaman Çizelgesi:
─────────────────────────────────────────────────────

Thread 1:  │██ Run 0 ██│████ Run 1 (delay+exec) ████│
Thread 2:  │           │  ██ Run 2 (delay+exec) ██   │
Thread 3:  │           │    ██ Run 3 (delay+exec) ██ │
           │           │                              │
─────────────────────────────────────────────────────
           t=0        t=2                             t=end
```

- Run 0 hemen başlar (`run_index == 0`, gecikme yok)
- Run 1 ve sonraki her run, `delay_seconds` kadar bekler sonra başlar
- Tüm çalıştırmalar tamamlandığında sonuçlar sıralı listede toplanır

### Thread Güvenliği

- Her thread kendi LLM çağrısını bağımsız olarak yapar
- `runs` listesi, thread-safe şekilde indeksle yazılır (`runs[run_index] = issues`)
- `as_completed` ile sonuçlar sırasız gelirse bile doğru indekse yazılır

### Performans Karakteristikleri

| Senaryo | n_runs | max_workers | Toplam süre (tahmini) |
|---------|--------|-------------|----------------------|
| Seri | 3 | 1 | ~3 × single_run_time |
| Paralel (2 worker) | 3 | 2 | ~2 × single_run_time |
| Tam paralel | 3 | 3 | ~1 × single_run_time + delays |

---

## 8. Sonuç Kalitesi

### Consensus Score Mekanizması

Judge'ın ürettiği her issue bir `consensus_score` taşır:

```
consensus_score = sorunu bulan çalıştırma sayısı / toplam çalıştırma sayısı
```

| Consensus | Score (3 run) | Güvenilirlik |
|-----------|---------------|-------------|
| Tam uzlaşı | 1.0 (3/3) | Çok yüksek |
| Çoğunluk | 0.67 (2/3) | Yüksek |
| Azınlık | 0.33 (1/3) | Düşük (ancak Judge onaylamış olmalı) |

### Kalite Metrikleri

Çoklu critic yaklaşımının ölçülebilir etkileri:

| Metrik | Tek Critic, Tek Run | Çift Critic, Çoklu Run |
|--------|---------------------|------------------------|
| **Hata kapsama oranı** | Düşük-Orta | Yüksek |
| **Yanlış pozitif oranı** | Orta-Yüksek | Düşük (Judge filtreler) |
| **Tutarlılık** | Düşük (stokastik) | Yüksek (consensus bazlı) |
| **Severity doğruluğu** | Düşük (tek görüş) | Yüksek (çoklu görüş + Judge ayarı) |
| **Kategori kapsama** | Sınırlı (tek perspektif) | Geniş (iki perspektif) |

### Judge İstatistikleri

Judge her çalıştırmada şu metrikleri loglar:

```python
logger.info(
    "critic_judge_done",
    critic=critic_name,        # "critic_a" veya "critic_b"
    input_issues=total_input,  # Judge'a giren toplam issue sayısı
    kept=len(kept_issues),     # Korunan issue sayısı
    rejected=rejected_count,   # Reddedilen issue sayısı
    inferred=inferred_count,   # Çıkarılan yeni issue sayısı
)
```

Bu metrikler, Judge'ın filtreleme performansını izlemek için kullanılabilir.

### Sorun Yaşam Döngüsü

```
Orijinal Belge
       │
       ▼
┌──────────────────────┐
│ Critic A (n runs)    │──► Örn: 3 run × 5 issue = 15 issue
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│ Judge (Critic A)     │──► 15 issue → 4 kept + 8 rejected + 1 inferred
└──────────────────────┘     (filtreleme oranı: ~%73)
       │
       ▼
┌──────────────────────┐
│ Critic B (n runs)    │──► Örn: 3 run × 4 issue = 12 issue
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│ Judge (Critic B)     │──► 12 issue → 3 kept + 7 rejected + 0 inferred
└──────────────────────┘
       │
       ▼
Final Sorun Listesi: 4 + 1 + 3 = 8 yüksek kaliteli issue
```

---

## 9. Örnek Çıktı

### Critic A Örnek Issue'lar

**Örnek 1 — Contradiction (Tam uzlaşı):**

```json
{
  "id": "A-001",
  "title": "Cache TTL değeri çelişkili",
  "severity": "high",
  "category": "contradiction",
  "rationale": "Belgenin 3. bölümünde cache TTL'nin 5 dakika olduğu belirtilirken, 7. bölümdeki rollout planında 30 dakika olarak geçmektedir. Bu çelişki canlıya çıkışta stale data sorununa yol açabilir.",
  "evidence_quote": "\"Cache TTL değeri 5 dakika olarak konfigüre edilecektir\" (Bölüm 3) vs \"cache TTL: 30 dakika\" (Bölüm 7, Tablo 2)",
  "affected_section": "Bölüm 3 — Veri Katmanı / Bölüm 7 — Rollout Planı",
  "proposed_fix": "Her iki bölümde cache TTL değerini tutarlı hale getirin. Canlıya çıkış için 5 dakika TTL önerilir, rollout planındaki 30 dakikalık değeri düzeltin.",
  "source_pass": "critic_a",
  "consensus_score": 1.0,
  "run_origins": ["run_0", "run_1"]
}
```

**Örnek 2 — Missing Requirement (Çoğunluk):**

```json
{
  "id": "A-002",
  "title": "Hata durumlarında retry mekanizması tanımlanmamış",
  "severity": "medium",
  "category": "missing_requirement",
  "rationale": "Belge yeni önbellek katmanının başarısız olma senaryosunu tartışmıyor. Cache down olduğunda sistemin nasıl davranacağı (fallback, retry, circuit breaker) belirtilmemiş.",
  "evidence_quote": "\"Tüm okuma istekleri cache üzerinden karşılanacaktır\" (Bölüm 3.2)",
  "affected_section": "Bölüm 3.2 — Okuma Yolu",
  "proposed_fix": "Cache miss ve cache unavailable senaryoları için fallback stratejisi tanımlayın. Circuit breaker pattern'i eklemeyi düşünün.",
  "source_pass": "critic_a",
  "consensus_score": 0.67,
  "run_origins": ["run_0", "run_2"]
}
```

**Örnek 3 — Dependency Gap (Azınlık, Judge tarafından korunmuş):**

```json
{
  "id": "A-003",
  "title": "Redis cluster versiyon gereksinimi eksik",
  "severity": "low",
  "category": "dependency_gap",
  "rationale": "Redis streams kullanımı planlanıyor ancak minimum Redis versiyonu belirtilmemiş. Redis Streams 5.0+'da mevcuttur ve bu bilgi altyapı ekibi için kritiktir.",
  "evidence_quote": "\"Redis Streams kullanarak event publishing yapılacaktır\" (Bölüm 4.1)",
  "affected_section": "Bölüm 4.1 — Event Publishing",
  "proposed_fix": "Minimum Redis 5.0 gereksinimini bağımlılıklar bölümüne ekleyin.",
  "source_pass": "critic_a",
  "consensus_score": 0.33,
  "run_origins": ["run_1"]
}
```

### Critic B Örnek Issue'lar

**Örnek 1 — Rollout Safety (Tam uzlaşı):**

```json
{
  "id": "B-001",
  "title": "Canary deployment için rollback kriterleri tanımlı değil",
  "severity": "critical",
  "category": "rollout_safety",
  "rationale": "Canary deployment planlanıyor ancak ne zaman rollback yapılacağına dair açık kriterler yok. Hata oranı eşikleri, latency SLO ihlalleri veya belirli hata kodları için tetikleme kuralları tanımlanmamış.",
  "evidence_quote": "\"Canary deployment ile %10 trafik ile başlanacak ve kademeli olarak artırılacaktır\" (Bölüm 7.1)",
  "affected_section": "Bölüm 7.1 — Deployment Stratejisi",
  "proposed_fix": "Açık rollback kriterleri tanımlayın: hata oranı >%1, p99 latency >500ms, veya 5xx hata kodları >%0.5 gibi sayısal eşikler belirleyin.",
  "source_pass": "critic_b",
  "consensus_score": 1.0,
  "run_origins": ["run_0", "run_1"]
}
```

**Örnek 2 — Observability (Çoğunluk):**

```json
{
  "id": "B-002",
  "title": "Yeni servise ait dashboard ve alarm tanımları eksik",
  "severity": "high",
  "category": "observability",
  "rationale": "Belge yeni mikroservisin izleme gereksinimlerini içermiyor. Mevcut Grafana dashboard'larına hangi metriklerin eklenmesi gerektiği, hangi alarmların oluşturulacağı ve PagerDuty entegrasyonu belirtilmemiş.",
  "evidence_quote": "\"Servis health check endpoint'i /health üzerinden sunulacaktır\" (Bölüm 5)",
  "affected_section": "Bölüm 5 — Servis Arayüzleri",
  "proposed_fix": "Bir izleme planı bölümü ekleyin: Grafana dashboard şablonu, kritik metrikler (request rate, error rate, latency percentiles), alarm eşikleri ve PagerDuty routing kuralları.",
  "source_pass": "critic_b",
  "consensus_score": 0.67,
  "run_origins": ["run_0", "run_2"]
}
```

**Örnek 3 — Edge Case (Azınlık, Judge tarafından korunmuş):**

```json
{
  "id": "B-003",
  "title": "Concurrent güncelleme senaryosu ele alınmamış",
  "severity": "medium",
  "category": "edge_case",
  "rationale": "Aynı kaynak üzerinde eşzamanlı güncelleme yapıldığında optimistic locking veya pessimistic locking mekanizması belirtilmemiş. Race condition veri tutarsızlığına yol açabilir.",
  "evidence_quote": "\"Kullanıcılar aynı anda güncelleme yapabilir\" (Bölüm 2.3)",
  "affected_section": "Bölüm 2.3 — Eşzamanlılık Gereksinimleri",
  "proposed_fix": "Optimistic locking ile version-based conflict detection ekleyin veya distributed lock mekanizması (Redis-based) tanımlayın.",
  "source_pass": "critic_b",
  "consensus_score": 0.33,
  "run_origins": ["run_1"]
}
```

### Judge Reddedilmiş Örnek Issue

```json
{
  "id": "B-004",
  "title": "Belgede daha fazla örnek kod parçası olabilir",
  "severity": "low",
  "category": "implementability",
  "rationale": "Belgede daha fazla kod örneği olabilir",
  "evidence_quote": "\"API endpoint'leri REST standartlarına uygun olacaktır\" (Bölüm 5)",
  "affected_section": "Bölüm 5",
  "proposed_fix": "Her endpoint için örnek request/response ekleyin",
  "consensus_score": 0.33,
  "run_origins": ["run_2"],
  "judge_decision": "rejected_unnecessary"
}
```

### Judge Tarafından Çıkarılan (Inferred) Örnek Issue

```json
{
  "id": "B-005",
  "title": "Veri tutarlılık kontrolü (data integrity check) mekanizması eksik",
  "severity": "high",
  "category": "migration_risk",
  "rationale": "Run 0 migration adımlarını listeler, Run 1 data transformation doğruluğundan bahseder, ancak hiçbir run migration sonrası veri bütünlüğünün nasıl doğrulanacağını söylemez. Büyük veri setlerinde sessiz veri kaybı riski vardır.",
  "evidence_quote": "Run 0: \"Migration 3 aşamada gerçekleşecektir\" + Run 1: \"Her aşamada data transform uygulanacaktır\"",
  "affected_section": "Bölüm 6 — Veri Geçişi",
  "proposed_fix": "Her migration aşaması sonrası data integrity check adımı ekleyin: kayıt sayısı karşılaştırması, checksum doğrulama, örneklem bazlı manuel kontrol.",
  "consensus_score": 0.0,
  "run_origins": ["inferred"],
  "judge_decision": "inferred"
}
```

---

## Yapılandırma Özeti

Tam multi-critic yapılandırması için `config/app.yaml`:

```yaml
pipeline:
  critic_max_workers: 3          # Paralel thread sayısı
  critic_delay_seconds: 2        # Çalıştırmalar arası gecikme (saniye)
  critic_runs: 2                 # Her critic için çalıştırma sayısı

model_aliases:
  critic_a: cheap_large_context       # Critic A modeli
  critic_b: cheap_large_context_alt   # Critic B modeli (farklı sağlayıcı)
  critic_judge: cheap_large_context   # Judge modeli
```

Ortam değişkenleri ile geçersiz kılma:

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `DQG_CRITIC_WORKERS` | `3` | Paralel çalıştırma için thread sayısı |
| `DQG_CRITIC_DELAY` | `2` | Çalıştırmalar arası gecikme (saniye) |
| `DQG_CRITIC_RUNS` | `2` | Her critic için çalıştırma sayısı |

---

## Kaynak Dosyalar

| Dosya | Açıklama |
|-------|----------|
| `src/app/stages/critic.py` | Critic A ve B çalıştırma mantığı, multi-run mekanizması, paralel çalışma |
| `src/app/stages/critic_judge.py` | Judge birleştirme mantığı, consensus hesaplama, filtreleme |
| `config/prompts/critic_a.md` | Critic A prompt şablonu (staff engineer perspektifi) |
| `config/prompts/critic_b.md` | Critic B prompt şablonu (engineering manager perspektifi) |
| `config/prompts/critic_judge.md` | Judge prompt şablonu (principal engineer perspektifi) |
| `config/app.yaml` | Model alias'ları, pipeline parametreleri |
| `src/app/schemas.py` | `Issue`, `Severity`, `SourcePass`, `CriticACategory`, `CriticBCategory` şemaları |
