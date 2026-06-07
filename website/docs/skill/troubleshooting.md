---
sidebar_position: 11
title: Sorun Giderme
---

# Sorun Giderme

## Yaygin Hatalar

| Hata | Neden | Cozum |
|------|-------|-------|
| DQG dizini bulunamadi | DQG kurulu degil | Pipeline otomatik kurar (git clone + pip install) |
| `.venv` bulunamadi | Virtual env olusturulmamis | Pipeline otomatik olusturur |
| `ZAI_API_KEY` bos | API anahtari tanimlanmamis | `.env` dosyasina ekleyin |
| LiteLLM proxy baslamadi | `litellm.exe` bozuk (Windows) | Pipeline Python wrapper kullanir |
| Port 4000 kullanmda | Eski proxy calisiyor | Otomatik kill + restart |
| DQG review timeout | `auto-review` kullanildi | `launch` + `poll` kullanin |
| Skor 8.0 altinda | Dokuman kalitesi yetersiz | `rescore` ile iteratif duzeltme |
| Lint/typecheck hatasi | Kod kalite sorunu | Pipeline 3 kez duzeltmeye calisir |
| Agent hatasi | LLM API sorunu | Pipeline 1 kez tekrar dener |
| DQG yanlis kod tabanini review ediyor | `--project` eksik veya yanlis | Wrapper otomatik CWD kullanir, DQG dizini engellenir |
| DQG false positive uretiyor | Cross-reference indexing eksik | Faz 3.1 otomatik dogrulama yapar |

## Self-Healing

Pipeline sorunlari otomatik tespit eder ve cozumer:

- **Clone hatasi** → git ve network kontrolu, hatayi raporlar
- **pip install hatasi** → `--no-cache` ile tekrar dener, pip upgrade yapar
- **Proxy baslamadi** → `litellm.exe` yerine Python modulu kullanir
- **Port cakismasi** → Eski sureci kill eder, tekrar baslatir
- **API anahtari gecersiz** → Hatayi raporlar, dogru anahtari ister
- **Lint hatasi** → 3 denemeye kadar otomatik duzeltir

Detayli self-healing mekanizmasi icin [Self-Healing](/dqg/self-healing) dokumanina bakin.

## Pipeline Resume

Pipeline herhangi bir noktada durdurulabilir. Kaldiginiz yerden devam etmek icin:

```
continue pipeline PDB-12345
```

veya

```
resume pipeline
```

Pipeline su adimlari izler:

1. `.pipeline/{TASK_KEY}-state.json` okunur
2. `current_phase` belirlenir
3. Kullaniciya bildirilir: "Pipeline Faz 6'da kaldi. Devam edeyim mi?"
4. Onay sonrasi kaldigi fazdan devam eder

## DQG CLI Komutlari

Ileri kullanicilar icin DQG'yi dogrudan CLI'dan calistirabilirsiniz:

```bash
cd ~/doc-quality-gate
source .venv/bin/activate  # Linux/macOS
# veya: .venv\Scripts\Activate.ps1  # Windows

# Review baslat (--project zorunlu)
python scripts/dqg_run.py launch "path/to/doc.md" --project "/path/to/target-project" --cp "/path/to/context"

# Sonuc poll et
python scripts/dqg_run.py poll {review_id}

# Hizli tekrar
python scripts/dqg_run.py rescore {review_id}

# Jira'dan dokuman uret
python scripts/dqg_run.py from-jira PROJ-123 --cp "/path/to/context"
```

Tum CLI komutlari icin [CLI Reference](/dqg/cli-reference) dokumanuna bakin.

## Hata Guncesi

Tum pipeline hatalari `.pipeline/{TASK_KEY}-errors.log` dosyasina kaydedilir. Hata durumunda bu dosyayi inceleyin.

## Debug Ipuclari

1. **DQG dashboard** → `http://localhost:8080` adresinden review ilerlemesini izleyin
2. **Pipeline state** → `.pipeline/{TASK_KEY}-state.json` ile mevcut fazi gorun
3. **DQG loglari** → `outputs/runs/` dizininde her review'un detayli loglari
4. **Lint hatasi** → `max 3 attempts` icinde cozulmezse, kullaniciya bildirilir
