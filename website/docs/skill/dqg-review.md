---
sidebar_position: 6
title: "Faz 3: DQG Review"
---

# Faz 3: REVIEW_DOC (DQG)

Implementasyon dokumanini DQG pipeline ile review eder. DQG, dokumaninizi kod tabaniniza karsi dogrular, multi-critic review yapar ve 8 boyutta skorlar.

## Genel Bakis

DQG review su sureci calistirir:

```
critic_a + critic_b [PARALEL] → judge → deduplicate →
cross-reference → validate → revise → score → meta_judge → report
```

Detayli pipeline stage aciklamalari icin:
- [Pipeline Stages](/dqg/pipeline-stages) — her stage ne yapar
- [Multi-Critic Approach](/dqg/multi-critic-approach) — critic mekanizmasi
- [Scoring System](/dqg/scoring-system) — 8 boyutlu skorlama
- [Cross-Reference](/dqg/cross-reference) — kod tabani dogrulama

## Calistirma

Pipeline DQG'yi otomatik tetikler:

```bash
python scripts/dqg_run.py launch ".pipeline/{TASK_KEY}-impl-doc.md" --project "{project_path}" --cp "{context_path}"
```

**Kritik kurallar:**
- `--project` parametresi **zorunludur** — hedef projenizin yolu olmali, DQG'nin kurulum dizini degil
- `--project` verilmezse wrapper otomatik olarak CWD'yi kullanir
- Wrapper, `--project` DQG'nin dizinine mi isaret ediyor diye dogrular
- `launch` komutu proxy + web server'i otomatik baslatir
- Tarayicida `http://localhost:8080` acilir — review ilerlemesini izleyebilirsiniz
- `auto-review` KULLANILMAZ — bloklanir ve zaman asimina ugrar

## Polling

Review basladiktan sonra sonuclar icin polling yapilir:

```bash
# Her 30-60 saniyede bir poll et
python scripts/dqg_run.py poll {review_id} --max-attempts 3
```

- Review 5-15 dakika surer
- AI kullaniciyi bilgilendirir: "Hala calisiyor... son durum: `status`"
- REVIEW_COMPLETE veya REVIEW_FAILED gelene kadar devam eder

## Sonuclar

Review tamamlandiginda su dosyalar olusur:

| Dosya | Icerik |
|-------|--------|
| `scorecard.json` | Genel skor, boyut skorlari, gecti/kaldi |
| `revised.md` | DQG'nin duzeltilmis dokumani |
| `report.md` | Tam review raporu |
| `issues.json` | Tespit edilen tum sorunlar |

## 8 Boyutlu Skorlama

Her boyut 0-10 arasi skorlanir:

| Boyut | Aciklama |
|-------|----------|
| correctness | Dokuman teknik olarak dogru mu |
| completeness | Tum gereksinimler kapsaniyor mu |
| implementability | Uygulanabilir mi |
| consistency | Tutarsizlik var mi |
| edge_case_coverage | Sinir durumlar kapsaniyor mu |
| testability | Test edilebilir mi |
| risk_awareness | Riskler tanimlanmis mi |
| clarity | Acik ve anlasilir mi |

Detayli skorlama mekanizmasi icin [Scoring System](/dqg/scoring-system) dokumanina bakin.

## Gecme Kriteri

- **Skor >= 8.0** → GECTI, bir sonraki faza gec
- **Skor `<=` 8.0** → KALDI, iteratif duzeltme

## Iteratif Duzeltme (Score `<=` 8.0)

DQG zaten `revised.md` dosyasinda duzeltmeleri uygular. Tekrar calistirmak icin `rescore` kullanilir:

```bash
# rescore: sadece score + meta_judge calisir (~2dk vs ~10dk tam pipeline)
python scripts/dqg_run.py rescore {review_id}
```

- `rescore` critic'leri, cross-reference ve validation'i atlar — 5 kat daha hizli
- Kullanici manuel duzeltme yaptiysa: `--revised path/to/edited.md`
- Maksimum `max_review_iterations` (varsayilan: 2) kez tekrarlanir

Detaylar icin [Rescore Mode](/dqg/rescore-mode) dokumanina bakin.

## Faz 3.1: Cross-Reference Dogrulama

DQG review tamamlandiktan sonra, cross-reference sonuclari **dogrulanmadan** kullaniciya sunulmaz. Bu adim false positive'leri filtreler.

### Neden Gerekli?

DQG kod tabaninizi tararken bazi ogeleri bulamayabilir (ornegin C# projelerinde yeni dil destegi eklenene kadar). Bu durumda DQG "X mevcut degil" diye raporlar, ancak X gercekte kod tabaninda vardir.

### Dogrulama Adimlari

1. `issues.json` dosyasini oku
2. Her HIGH/CRITICAL "bulunamadi" iddiasi icin kod tabaninda grep calistir:
   - Sinif: `grep -r "class UserNotification" --include="*.cs"`
   - Interface: `grep -r "interface IEmailService" --include="*.cs"`
   - Endpoint: `grep -r "api/notifications" --include="*.cs" --include="*.ts"`
3. Bulunursa → **FALSE POSITIVE** olarak isaretle, dosya yolunu not et
4. Gerekten yoksa → **CONFIRMED** olarak isaretle
5. Kullaniciya sadece CONFIRMED sorunlar + FALSE POSITIVE ozeti sunulur

### Desteklenen Diller

DQG cross-reference su dilleri destekler:

| Dil | Dosya Uzantisi | API Route Algilama | Entity Algılama | Dependency Algılama |
|-----|----------------|--------------------|-----------------|--------------------|
| Python | `.py` | FastAPI, Flask | SQLAlchemy, Pydantic | `requirements.txt`, `pyproject.toml` |
| JavaScript/TypeScript | `.js`, `.ts`, `.tsx` | Express, Fastify | Prisma, TS interfaces | `package.json` |
| Java | `.java` | Spring `@XMapping` | JPA Models | `pom.xml`, `build.gradle` |
| C#/.NET | `.cs` | ASP.NET `[HttpX]`, `MapX` | Entity properties | `.csproj` |
| Go | `.go` | `net/http` handlers | GORM structs | `go.mod` |
| Ruby | `.rb` | Rails routes | ActiveRecord | `Gemfile` |
| PHP | `.php` | Laravel routes | Eloquent models | `composer.json` |

## Kullaniciya Sunulan Format

```
🔍 DQG REVIEW SONUCLARI

Skor: 8.5/10 | Sonuc: GECTI

Boyut skorlari:
- correctness: 9/10
- completeness: 8/10
- implementability: 9/10
- consistency: 8/10
- edge_case_coverage: 7/10
- testability: 9/10
- risk_awareness: 8/10
- clarity: 9/10

Bulunan sorunlar: 12 toplam, 2 kritik, 4 yuksek

En onemli bulgular:
- API endpoint tanimi eksik
- Hata durumu yonetimi tanimlanmamis
- Test stratejisi yuzeysel

Guncel dokuman: .pipeline/PDB-12345-impl-doc-reviewed.md

Yantla: "Onayliyorum" → TODO listesine gecerim
         "Sunu degistir: ..." → degisikligi uygularim
         "Tekrar review et" → DQG'yi tekrar calistiririm
```

## DQG Web Dashboard

Review sirasinda ilerlemeyi `http://localhost:8080` adresinden izleyebilirsiniz. Dashboard SSE (Server-Sent Events) ile anlik guncelleme saglar.

Detaylar icin [Web Dashboard](/dqg/web-dashboard) dokumanina bakin.

## Pipeline Profilleri

DQG farkli hiz/kalite profilleri destekler:

| Profil | Surme | Kullanim |
|--------|-------|----------|
| fast_track | ~2-3dk | Kucuk degisiklikler |
| standard | ~10dk | Genel kullanim (varsayilan) |
| deep | ~20-30dk | Kritik degisiklikler |

Detaylar icin [Pipeline Optimization](/dqg/pipeline-optimization) dokumanina bakin.
