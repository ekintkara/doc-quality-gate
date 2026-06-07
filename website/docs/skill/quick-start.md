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
dqg_path: ~/doc-quality-gate
context_path: .context/
review_agents: 3
max_review_iterations: 2
```

Config detaylari icin [Yapilandirma](./configuration) sayfasina bakin.

## Adim 3: Pipeline Baslatin

Task kaynaginiza gore AI asistaniniza asagidaki komutlardan birini soyleyin:

### Jira Task

```
implement PDB-12345
```

veya

```
/dev-pipeline PDB-12345
```

Jira task'ini otomatik olarak okur (ADF aciklamasi, yorumlar, label'lar, oncelik). On kosul: `.env` dosyasinda [Jira credentials](/dqg/jira-integration) tanimli olmali.

### Azure DevOps Task

```
implement AB#456
```

veya (`azure_devops_org` ve `azure_devops_project` config'i varsa `#` ile de calisir):

```
implement #456
```

Azure DevOps work item'ini `az boards work-item show` ile okur. On kosul: [Azure CLI kurulu ve authenticate](./configuration#azure-devops) olmali.

### GitHub Issue

```
implement ekintkara/my-repo#42
```

GitHub issue'yu `gh issue view` ile okur. On kosul: [gh CLI authenticate](./configuration#github-issues) olmali.

### Dosya

```
/dev-pipeline docs/my-task.md
```

Dosya icerigini dogrudan task aciklamasi olarak kullanir.

### Serbest Metin

```
/dev-pipeline Login sayfasina remember-me checkbox ekle
```

Metni dogrudan task olarak kullanir. Herhangi bir entegrasyon kurulumu gerektirmez.

### Pipeline Devam Ettirme

Durdurulan bir pipeline'i kaldiginiz yerden devam ettirmek icin:

```
continue pipeline
```

veya

```
resume pipeline
```

---

### Ilk Calistirma

**Ilk calistirmada** PHASE 0 (DQG_ENSURE) otomatik olarak:

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
Kaynak: Jira | Key: PDB-12345 | Tip: Story | Oncelik: High

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
