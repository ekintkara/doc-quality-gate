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

```powershell
# Launch (hemen doner, review arka planda calisir)
& "{dqg_path}\.venv\Scripts\python.exe" "{dqg_path}\scripts\dqg_run.py" launch ".pipeline/{TASK_KEY}-impl-doc.md" --project "{project_path}" --cp "{context_path}"
```

**Onemli:**
- `launch` komutu proxy + web server'i otomatik baslatir
- Tarayicida `http://localhost:8080` acilir — review ilerlemesini izleyebilirsiniz
- `auto-review` KULLANILMAZ — bloklanir ve zaman asimina ugrar

## Polling

Review basladiktan sonra sonuclar icin polling yapilir:

```powershell
# Her 30-60 saniyede bir poll et
& "{dqg_path}\.venv\Scripts\python.exe" "{dqg_path}\scripts\dqg_run.py" poll {review_id} --max-attempts 3
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

```powershell
# rescore: sadece score + meta_judge calisir (~2dk vs ~10dk tam pipeline)
& "{dqg_path}\.venv\Scripts\python.exe" "{dqg_path}\scripts\dqg_run.py" rescore {review_id}
```

- `rescore` critic'leri, cross-reference ve validation'i atlar — 5 kat daha hizli
- Kullanici manuel duzeltme yaptiysa: `--revised path/to/edited.md`
- Maksimum `max_review_iterations` (varsayilan: 2) kez tekrarlanir

Detaylar icin [Rescore Mode](/dqg/rescore-mode) dokumanina bakin.

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
