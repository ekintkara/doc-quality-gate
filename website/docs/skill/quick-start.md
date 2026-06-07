---
sidebar_position: 2
title: Hizli Baslangic
---

# Hizli Baslangic

3 adimda ilk pipeline run'inizi yapin.

## On Kosullar

- Git yuklu
- Python 3.11+ yuklu
- Node.js 18+ yuklu
- Bir AI coding asistani (opencode, Claude Code, Cursor, vb.) kurulu

## Adim 1: Skill'i Kurun

AI coding asistaniniza dev-pipeline skill'ini kurun:

```bash
npx skills add ekintkara/doc-quality-gate --skill dev-pipeline -g
```

Bu komut skill dosyalarini asistaninizin skills dizinine kopyalar. DQG engine otomatik olarak ilk pipeline calistirmasinda kurulur — ayri bir kurulum gerekmez.

**Manuel kurulum** isterseniz, repo'dan skill dosyalarini kopyalayabilirsiniz:

```bash
git clone https://github.com/ekintkara/doc-quality-gate.git
# Skill dosyalari: skills/dev-pipeline/ dizininde
```

## Adim 2: Pipeline Config (Opsiyonel)

Projenizin `AGENTS.md` dosyasina config ekleyebilirsiniz. Eklemezseniz varsayilan degerler kullanilir:

```markdown
## Pipeline Config

task_source: jira
dqg_repo: https://github.com/ekintkara/doc-quality-gate.git
dqg_path: C:\repos\doc-quailty-gate
context_path: .context/
review_agents: 3
max_review_iterations: 2
```

Config detaylari icin [Yapilandirma](./configuration) sayfasina bakin.

## Adim 3: Pipeline Baslatin

AI asistaniniza soyleyin:

```
implement PDB-12345
```

Pipeline baslar. **Ilk calistirmada** PHASE 0 (DQG_ENSURE) otomatik olarak:

1. DQG dizinini kontrol eder → yoksa `git clone` yapar
2. Virtual environment olusturur → `pip install` yapar
3. `.env` dosyasi olusturur → API key ister
4. LiteLLM proxy baslatir
5. Web dashboard baslatir (opsiyonel)

```
[PHASE 0] DQG kuruluyor...
  ✓ DQG dizini klonlandi
  ✓ Virtual environment olusturuldu
  ✓ Bagimliliklar kuruldu
  ? Z.AI API key girin: ********
  ✓ LiteLLM proxy baslatildi
  ✓ DQG hazir

[PHASE 1] Task okunuyor...
  ✓ PDB-12345 Jira'dan okundu

📋 TASK OZETI
Key: PDB-12345 | Tip: Story | Oncelik: High

Ne yapilmasi gerekiyor:
- Kullanici profil sayfasina avatar yukleme ozelligi eklenmeli

Yantla: "Onayliyorum" → implementasyon dokumanina gecerim
```

**"Onayliyorum"** dedikten sonra pipeline bir sonraki faza gecer.

## Sonraki Calistirmalar

Ikinci ve sonraki calistirmalarda PHASE 0 atlanir (DQG zaten hazir). Pipeline direkt TASK_INTAKE'ten baslar.

## Pipeline Ciktilari

Tamamlanan pipeline `.pipeline/` dizininde su dosyalari olusturur:

```
.pipeline/
├── PDB-12345-state.json
├── PDB-12345-impl-doc.md
├── PDB-12345-impl-doc-reviewed.md
├── PDB-12345-todo.md
├── PDB-12345-todo-review-{1,2,3}.md
├── PDB-12345-todo-judge.md
├── PDB-12345-impl-review-{1,2,3}.md
├── PDB-12345-impl-judge.md
├── PDB-12345-test-plan.md
├── PDB-12345-test-results.md
└── PDB-12345-errors.log
```

## Onemli Notlar

- **Kod pushlanmaz** — pipeline bittiginde kod yerel dizinde kalir
- **Her fazda onay istenir** — "Onayliyorum", "Sunu degistir...", veya "Durdur"
- **Pipeline durdurulabilir** — "continue pipeline" ile kaldiginiz yerden devam eder
- **DQG review 5-15 dakika surer** — dashboard'dan izleyebilirsiniz

## Sonraki Adimlar

- [Pipeline Fazlari](./phases) — her fazin detayli aciklamasi
- [Yapilandirma](./configuration) — tum config secenekleri
- [DQG Review](./dqg-review) — review motoru nasil calisir
