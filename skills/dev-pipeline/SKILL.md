---
name: dev-pipeline
description: "Generic human-in-the-loop development pipeline. Supports any project, any task source (Jira, Azure DevOps, GitHub Issues, files, free text). Task analysis, implementation document, DQG review, TODO list, multi-agent review, implementation, code review, test planning, testing. Every phase requires user approval. Auto-generates context from codebase if none provided. Auto-installs DQG if missing."
---

# Dev Pipeline Skill

Generic, human-in-the-loop development pipeline.
Supports any project, any task source (Jira, Azure DevOps, GitHub Issues, files, free text).
Uses Doc Quality Gate (DQG) for implementation document review.
The AI NEVER acts independently. Every phase transition requires explicit user approval.

## GOLDEN RULES

1. **NEVER push code** without explicit user request
2. **NEVER skip to next phase** without user approval
3. **NEVER commit** unless user explicitly says "commit" or "push"
4. **ALWAYS summarize** completed work before asking for approval
5. **ALWAYS ask** "Devam edeyim mi?" or "Onaylıyor musun?" before moving forward
6. **ALWAYS adapt** if user makes changes - incorporate and continue
7. **NEVER be autonomous** - the user is the decision maker, AI is the executor

## When to Use

When the user says any of:
- "implement PDB-XXXX" / "implement AB#XXXX" / "implement owner/repo#XXX"
- "pipeline {task-reference}"
- "/dev-pipeline {task-reference}"
- "bu taskı implement et"
- "continue pipeline" / "resume pipeline"

## Configuration

The pipeline reads config from the project's `AGENTS.md` (or `CLAUDE.md`) file.
Look for a `## Pipeline Config` section. If not found, use defaults and ask user.

**Config format (in AGENTS.md):**
```markdown
## Pipeline Config
task_source: jira                # jira | azure-devops | github | manual
jira_tool: auto                  # auto | mcp | acli | api
dqg_repo: https://github.com/ekintkara/doc-quailty-gate.git
dqg_path: C:\repos\doc-quailty-gate
# azure_devops_org: myorg
# azure_devops_project: MyProject
# github_repo: owner/repo
context_path: .context/
review_agents: 3
max_review_iterations: 2
```

**Defaults if config not found:**
- `dqg_repo`: `https://github.com/ekintkara/doc-quailty-gate.git`
- `dqg_path`: `C:\repos\doc-quailty-gate` (Windows) or `~/doc-quality-gate` (Linux/macOS)
- `review_agents`: 3
- `max_review_iterations`: 2

## Pipeline Overview

```
DQG_ENSURE → TASK_INTAKE → [USER] → CONTEXT_CHECK → (GENERATE_CONTEXT → [USER]) →
IMPL_DOC → [USER] → REVIEW_DOC(DQG) → [USER] → PLAN → [USER] → REVIEW_TODO → [USER] →
IMPLEMENT → REVIEW_IMPL → [USER] → TEST_PLAN → [USER] → TEST → [USER] → DONE
```

Every `[USER]` = AI stops, presents summary, waits for approval or modifications.

## Pipeline State File

**Location:** `.pipeline/{TASK_KEY}-state.json`

```json
{
  "task_key": "PDB-12345",
  "task_source": "jira",
  "current_phase": "TASK_INTAKE",
  "phases_completed": [],
  "project_path": "",
  "config": {
    "dqg_path": "",
    "context_path": "",
    "review_agents": 3,
    "max_review_iterations": 2
  },
  "artifacts": {
    "impl_doc": "",
    "doc_reviews": [],
    "doc_judge": "",
    "todo_list": "",
    "todo_reviews": [],
    "todo_judge": "",
    "impl_reviews": [],
    "impl_judge": "",
    "test_plan": "",
    "test_results": ""
  },
  "created_at": "",
  "updated_at": ""
}
```

---

## PHASE 0: DQG_ENSURE

**Goal:** Ensure DQG is installed, configured, and running. Auto-fix problems.

This phase runs BEFORE anything else. Follow `prompts/dqg-ensure.md` instructions.

**Steps:**
1. Read `dqg_path` from AGENTS.md config
2. Check if DQG directory exists → if not, clone from `dqg_repo`
3. Check if `.venv` exists → if not, create and install
4. Check if `.env` exists with `ZAI_API_KEY` → if not, ask user
5. Check if LiteLLM proxy is running → if not, start it
6. Run smoke test → if fails, troubleshoot
7. If all checks pass → proceed to TASK_INTAKE

**Self-healing:**
- Clone fails → check git, check network, report to user
- pip install fails → try `--no-cache`, upgrade pip, report
- Proxy won't start → `litellm.exe` may be broken on Windows; DQG's `_start_proxy()` uses Python wrapper: `python -c "from litellm.proxy.proxy_cli import run_server; run_server(args=[...])"`. If DQG's own fix doesn't work, manually start: `python -c "from litellm.proxy.proxy_cli import run_server; run_server(args=['--config', '{dqg_path}/config/litellm/config.yaml', '--port', '4000'])"`
- Port 4000 in use → kill existing process: `Get-NetTCPConnection -LocalPort 4000 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }`
- Wrong API key → update `.env` with correct `ZAI_API_KEY`
- Any unfixable error → tell user exactly what's wrong and how to fix
- **Self-healing mindset:** When something breaks, diagnose root cause and fix immediately. Don't just report - solve.

---

## PHASE 1: TASK_INTAKE

**Goal:** Read the task from whatever source the user specified.

Follow `prompts/task-intake.md` instructions for source-specific reading.

**Detection Rules:**

| Input Pattern | Source | Tool (priority order) |
|---|---|---|
| `[A-Z]+-\d+` (e.g. `PDB-12345`) | Jira | `jira_jira_get_issue` MCP → `acli jira workitem view` → REST API |
| `AB#\d+` or `#\d+` (with azure config) | Azure DevOps | `az boards work-item show` via bash |
| `owner/repo#\d+` | GitHub Issue | `gh issue view` via bash |
| Path ending in `.md`, `.txt`, `.json` | File | `read` tool |
| Anything else | Free text | Use as-is |

**Steps:**
1. Parse input to detect source
2. Read task from source
3. Read project context (auto-discovery order):
   - AGENTS.md → CLAUDE.md → .context/ → README.md
   - If none found, use `augmentcode_codebase-retrieval` to understand project
4. Investigate current codebase state using `augmentcode_codebase-retrieval`

**Present to user:**
```
📋 TASK ÖZETİ
Kaynak: {source} | Key: {key} | Tip: {type} | Öncelik: {priority}

Ne yapılması gerekiyor:
- {1-2 cümlelik özet}

Teknik durum:
- {mevcut durum}

Riskler:
- {varsa}

Yanıtla: "Onaylıyorum" → implementasyon dökümanına geçerim
         "Şunu değiştir: ..." → değişikliği uygularım
         "Durdur" → pipeline'ı durdururum
```

**WAIT for user response.**

---

## PHASE 1.5: CONTEXT_CHECK / GENERATE_CONTEXT

**Goal:** Ensure context is available for DQG and implementation.

**Ask the user:**
```
📁 Context dizininiz var mı?
(Bu dizin proje mimarisi, domain, convention gibi bilgiler içerir.
 Örn: .context/, docs/context/, C:\proje\context)

Yol yapıştırın → o dizini kullanırım
Enter → kod tabanını analiz edip context oluştururum
```

**If user provides a path:**
1. Verify the path exists
2. Set `context_path = {user_path}`
3. Continue to PHASE 2

**If user presses Enter (no context):**
1. Run PHASE 1.5: GENERATE_CONTEXT
2. Follow `prompts/context-generator.md` instructions
3. Use `augmentcode_codebase-retrieval` to analyze the codebase
4. Read any available: AGENTS.md, CLAUDE.md, README.md
5. Generate context files in `.pipeline/context/`:
   ```
   .pipeline/context/
   ├── architecture.md    # System architecture, modules, data flow
   ├── conventions.md     # Coding conventions, patterns, style
   ├── domain.md          # Domain model, entities, business rules
   └── patterns.md        # Framework patterns, common approaches
   ```
6. Set `context_path = .pipeline/context/`
7. Present to user:
   ```
   📁 Context oluşturuldu: .pipeline/context/
   
   Dosyalar:
   - architecture.md ({N} satır) - {1 cümle özet}
   - conventions.md ({N} satır) - {1 cümle özet}
   - domain.md ({N} satır) - {1 cümle özet}
   - patterns.md ({N} satır) - {1 cümle özet}
   
   İncelemek ister misin? Değişiklik yapabilirsin.
   
   Yanıtla: "Onaylıyorum" → implementasyon dökümanına geçerim
            "Şunu değiştir: ..." → context'i güncellerim
            "Context'i okumak istiyorum" → tamamını gösteririm
   ```
8. **WAIT for user response.**
9. After approval, pass `context_path` to DQG via `--cp {context_path}`

---

## PHASE 2: IMPL_DOC

**Goal:** Create the implementation document.

**Steps:**
1. Generate implementation document using task analysis + user feedback + codebase investigation
2. Save to `.pipeline/{TASK_KEY}-impl-doc.md`

**Implementation Document Template:**
```markdown
# Implementation Document: {TASK_KEY}

## 1. Task Summary
- **Key:** {key}
- **Title:** {title}
- **Type:** {type}
- **Priority:** {priority}
- **Source:** {jira/azure-devops/github/manual}

## 2. Requirements Analysis
### 2.1 Functional Requirements
### 2.2 Non-Functional Requirements
### 2.3 Acceptance Criteria

## 3. Technical Analysis
### 3.1 Current State
{from codebase-retrieval investigation}
### 3.2 Proposed Changes
### 3.3 Affected Components
### 3.4 Database Changes (if applicable)
### 3.5 API Changes (if applicable)

## 4. Implementation Plan
### 4.1 Phase 1: {name}
### 4.2 Phase 2: {name}

## 5. Risk Assessment
## 6. Dependencies
## 7. Testing Strategy
```

**Present to user:**
```
📝 IMPLEMENTASYON DÖKÜMANI HAZIR

Özet:
- {2-3 cümlelik genel özet}
- Toplam {N} faz, {M} değişiklik

Kritik noktalar:
- {en önemli 3-5 madde}

Etkilenen dosyalar: {file list}

Tam döküman: .pipeline/{TASK_KEY}-impl-doc.md

Yanıtla: "Onaylıyorum" → DQG review'a gönderirim
         "Şunu değiştir: ..." → değişikliği uygularım
         "Dökümanı okumak istiyorum" → tamamını gösteririm
```

**WAIT for user response.**

---

## PHASE 3: REVIEW_DOC (DQG)

**Goal:** Run DQG pipeline for multi-agent document review.

DQG pipeline:
```
critic_a (N runs) + critic_b (N runs) [PARALEL]
→ critic_judge (each group)
→ deduplicate
→ cross-reference (against codebase)
→ validate
→ revise
→ score (8 dimensions, 0-10)
→ meta_judge
→ report
```

**Steps:**

**IMPORTANT DQG NOTES:**
- `launch` command auto-starts proxy + web server if not running, AND opens browser to http://localhost:8080
- DO NOT use `auto-review` — it blocks and times out. Use `launch` + `poll` instead.
- DO NOT use `start-proxy` or `start` commands. They do not exist.
- DQG review takes 5-15 minutes. Poll repeatedly with short intervals.

1. Launch DQG review (auto-starts proxy + web + opens browser):
    ```powershell
    # Windows - use full paths
    & "{dqg_path}\.venv\Scripts\python.exe" "{dqg_path}\scripts\dqg_run.py" launch ".pipeline/{TASK_KEY}-impl-doc.md" --project "{project_path}" --cp "{context_path}"
    ```
    **Use timeout=120000 when running this command.** It returns immediately with `REVIEW_STARTED review_id=XXXXX`.

2. Parse `review_id` from output. Tell user:
    ```
    🔍 DQG review başladı. Tarayıcıda http://localhost:8080 açıldı.
    Review ID: {review_id}
    Polling...
    ```

3. Poll for results in a LOOP (repeat until COMPLETE or FAILED):
    ```powershell
    & "{dqg_path}\.venv\Scripts\python.exe" "{dqg_path}\scripts\dqg_run.py" poll {review_id} --max-attempts 3
    ```
    - Use timeout=60000 per poll call
    - If STATUS shows progress (e.g. `STATUS: running`), poll again
    - If POLL_INCOMPLETE, poll again
    - Repeat until REVIEW_COMPLETE or REVIEW_FAILED
    - Keep user informed: "Hala çalışıyor... son durum: {status}"

4. Read DQG results:
    - Find latest run: `outputs/runs/` directory, sort by modified time
    - `read` → `{run_dir}/scorecard.json` → overall score, dimension scores, pass/fail
    - `read` → `{run_dir}/revised.md` → DQG's revised document
    - `read` → `{run_dir}/report.md` → full review report
    - `read` → `{run_dir}/issues.json` → all issues found
    - `read` → `{run_dir}/validations.json` → validation results

5. If score < 8.0:
    - DQG already produced revised.md with fixes applied
    - **Use `rescore` for re-runs** (5x faster — skips critics, cross-ref, validation):
      ```powershell
      & "{dqg_path}\.venv\Scripts\python.exe" "{dqg_path}\scripts\dqg_run.py" rescore {review_id}
      ```
    - Parse new `RESCORE_STARTED review_id=XXXXX` → poll as in step 3
    - If user made manual edits to revised doc, pass `--revised path/to/edited.md`
    - Repeat up to `max_review_iterations`
    - If still < 8.0 after max iterations, present to user

6. Copy revised document to `.pipeline/{TASK_KEY}-impl-doc-reviewed.md`

**Present to user:**
```
🔍 DQG REVIEW SONUÇLARI

Skor: {score}/10 | Sonuç: {PASS/FAIL}

Boyut skorları:
- correctness: {score}/10
- completeness: {score}/10
- implementability: {score}/10
- consistency: {score}/10
- edge_case_coverage: {score}/10
- testability: {score}/10
- risk_awareness: {score}/10
- clarity: {score}/10

Bulunan sorunlar: {total} toplam, {critical} kritik, {high} yüksek

En önemli bulgular:
- {1}
- {2}
- {3}

DQG dökümanı düzeltti{(score < 8.0) ? " (iteratif düzeltme yapıldı)" : ""}.

Güncel döküman: .pipeline/{TASK_KEY}-impl-doc-reviewed.md

Yanıtla: "Onaylıyorum" → TODO listesine geçerim
         "Şunu değiştir: ..." → değişikliği uygularım
         "Tekrar review et" → DQG'yi tekrar çalıştırırım
```

**WAIT for user response.**

---

## PHASE 4: PLAN

**Goal:** Generate structured TODO list from approved implementation document.

**Steps:**
1. Read the approved implementation document (original or DQG-reviewed)
2. Dispatch TODO Generator agent using `task` tool (`subagent_type: "general"`):
   - Prompt: `prompts/todo-generator.md`
   - Input: Implementation document
3. Save to `.pipeline/{TASK_KEY}-todo.md`

**TODO List Format:**
```markdown
# TODO List: {TASK_KEY}

## Phase 1: {Phase Name}
**Goal:** {phase goal}

### TODO 1.1: {title}
- **Why:** {reason}
- **How:** {step-by-step}
- **Acceptance Criteria:**
  - [ ] {criterion}
- **Files:** {files}
- **Risk:** {low/medium/high}
```

**Present to user:**
```
📋 TODO LİSTESİ HAZIR

Toplam: {N} faz, {M} TODO

Faz özetleri:
1. {Faz 1} - {TODO sayısı} madde
2. {Faz 2} - {TODO sayısı} madde

Tam liste: .pipeline/{TASK_KEY}-todo.md

Yanıtla: "Onaylıyorum" → review'a gönderirim
         "Şunu değiştir: ..." → değişikliği uygularım
         "Listeyi görmek istiyorum" → tamamını gösteririm
```

**WAIT for user response.**

---

## PHASE 5: REVIEW_TODO

**Goal:** Multi-agent parallel review of TODO list.

**Steps:**
1. Read TODO list from `.pipeline/{TASK_KEY}-todo.md`
2. Dispatch 3 parallel review agents using `task` tool:

   **Agent 1 - Completeness:** `prompts/todo-reviewer.md` with `perspective: "completeness"`
   **Agent 2 - Order:** `prompts/todo-reviewer.md` with `perspective: "order"`
   **Agent 3 - Practicality:** `prompts/todo-reviewer.md` with `perspective: "practicality"`

   **Send ALL 3 `task` calls in a SINGLE message to run concurrently.**

3. Collect results → save to `.pipeline/{TASK_KEY}-todo-review-{1,2,3}.md`
4. Dispatch Judge Agent: `prompts/todo-judge.md`
5. Save judge result → `.pipeline/{TASK_KEY}-todo-judge.md`
6. Apply judge's edits to TODO list

**Present to user:**
```
🔍 TODO REVIEW SONUÇLARI

Judge Kararı: {APPROVED/MINOR_REVISION/MAJOR_REVISION}

Değişiklikler:
- {list}

Güncel TODO: .pipeline/{TASK_KEY}-todo.md

Yanıtla: "Onaylıyorum" → implementasyona geçerim
         "Şunu değiştir: ..." → değişikliği uygularım
```

**WAIT for user response.**

---

## PHASE 6: IMPLEMENT

**Goal:** Execute TODO items phase by phase.

Follow `prompts/implementer.md` instructions.

**Steps:**
1. Read approved TODO list
2. Create `todowrite` entries for all TODOs
3. For each phase, in order:
   - Briefly tell user which phase starting
   - For each TODO: implement → verify acceptance criteria → mark completed
   - After each phase: run lint/typecheck → fix if needed
4. NEVER commit

**After ALL phases complete:**
```
✅ IMPLEMENTASYON TAMAMLANDI

Yapılanlar:
- Faz 1: {özet}
- Faz 2: {özet}

Değişen dosyalar: {list}
Lint/Typecheck: {sonuç}

Yanıtla: "Devam" → implementation review'a geçerim
         "Şunu düzelt: ..." → düzeltme yaparım
```

**WAIT for user response.**

---

## PHASE 7: REVIEW_IMPL

**Goal:** Multiple agents review the actual code against the implementation document.

**Steps:**
1. Collect changed files (`git diff --name-only` or tracked list)
2. Read approved implementation document
3. Dispatch 3 parallel review agents using `task` tool:

   **Agent 1 - Compliance:** Does the code implement everything the document specifies?
   **Agent 2 - Quality:** Bugs, security, performance, code smells
   **Agent 3 - Pattern:** Does new code follow existing project patterns?

4. Collect → save to `.pipeline/{TASK_KEY}-impl-review-{1,2,3}.md`
5. Dispatch Judge Agent → `.pipeline/{TASK_KEY}-impl-judge.md`

**Present to user:**
```
🔍 IMPLEMENTASYON REVIEW

Compliance: {X/10 requirement met}
Quality: {issue count}
Pattern: {mismatch count}

Judge özeti:
- {bulgular}
- {düzeltilecekler}

Yanıtla: "Düzeltmeleri uygula" → judge'in önerdiklerini yaparım
         "Onaylıyorum, devam" → test planına geçerim
         "Şunu düzelt: ..." → sadece onu yaparım
```

**WAIT for user response.**

---

## PHASE 8: TEST_PLAN

**Goal:** Create test documentation.

**Steps:**
1. Read TODO list + implementation changes
2. Dispatch Test Planner agent: `prompts/test-planner.md`
3. Save to `.pipeline/{TASK_KEY}-test-plan.md`

**Present to user:**
```
🧪 TEST PLANI HAZIR

Otomatik: {X} unit, {Y} integration, {Z} Playwright
Manuel: {X} happy path, {Y} edge, {Z} error

Yanıtla: "Onaylıyorum" → testleri çalıştırırım
         "Şunu değiştir: ..." → uygularım
         "Testleri atla" → kaydeder, devam
```

**WAIT for user response.**

---

## PHASE 9: TEST

**Goal:** Execute tests.

**Steps:**
1. Run unit/integration tests via bash
2. Run Playwright MCP tests (if applicable)
3. Collect results → `.pipeline/{TASK_KEY}-test-results.md`

**Present to user:**
```
🧪 TEST SONUÇLARI

Otomatik: {X geçti, Y başarısız}
Manuel test adımları:
1. {adım}
2. {adım}
...

Yanıtla: "Manuel testler tamamlandı" → pipeline tamamlanır
         "Şu test başarısız, düzelt" → düzeltirim
         "Devam" → pipeline tamamlanır
```

**WAIT for user response.**

---

## PHASE 10: DONE

```
✅ PIPELINE TAMAMLANDI: {TASK_KEY}

Çıktılar: .pipeline/ dizininde
NOT: Kod pushlanmadı. Pushlamak istersen söyle.
```

**NEVER push unless user explicitly requests.**

---

## Resume Support

User says "continue pipeline" or "resume pipeline":
1. Find `.pipeline/{TASK_KEY}-state.json`
2. Read `current_phase`
3. Tell user: "Pipeline {phase} aşamasında kaldı. Devam edeyim mi?"
4. Resume after user confirms

## Context Auto-Discovery

When project context is needed, check in this order:
1. `AGENTS.md` in project root
2. `CLAUDE.md` in project root
3. `.context/` directory
4. `GEMINI.md` in project root
5. `README.md` in project root
6. `augmentcode_codebase-retrieval` for technical understanding
7. If none found → ask user

## Error Handling

- DQG error → run `prompts/dqg-ensure.md` self-healing, retry once
- Agent error → retry once, report to user
- Lint/typecheck error → fix (max 3 attempts), ask user if still failing
- All errors → `.pipeline/{TASK_KEY}-errors.log`

## File Structure

```
.pipeline/
├── {TASK_KEY}-state.json
├── context/                         # Generated context (if no context provided)
│   ├── architecture.md
│   ├── conventions.md
│   ├── domain.md
│   └── patterns.md
├── {TASK_KEY}-impl-doc.md
├── {TASK_KEY}-impl-doc-reviewed.md
├── {TASK_KEY}-todo.md
├── {TASK_KEY}-todo-review-{1,2,3}.md
├── {TASK_KEY}-todo-judge.md
├── {TASK_KEY}-impl-review-{1,2,3}.md
├── {TASK_KEY}-impl-judge.md
├── {TASK_KEY}-test-plan.md
├── {TASK_KEY}-test-results.md
└── {TASK_KEY}-errors.log
```

## Checklist

- [ ] PHASE 0: DQG_ENSURE - Auto-install + health check
- [ ] PHASE 1: TASK_INTAKE - Read task from source → **USER APPROVAL**
- [ ] PHASE 1.5: CONTEXT_CHECK - Ask for context, or GENERATE_CONTEXT → **USER APPROVAL**
- [ ] PHASE 2: IMPL_DOC - Generate implementation document → **USER APPROVAL**
- [ ] PHASE 3: REVIEW_DOC - DQG multi-agent review + scoring → **USER APPROVAL**
- [ ] PHASE 4: PLAN - Generate TODO list → **USER APPROVAL**
- [ ] PHASE 5: REVIEW_TODO - 3x agent + judge → **USER APPROVAL**
- [ ] PHASE 6: IMPLEMENT - Execute TODOs
- [ ] PHASE 7: REVIEW_IMPL - 3x agent + judge → **USER APPROVAL**
- [ ] PHASE 8: TEST_PLAN - Create test plan → **USER APPROVAL**
- [ ] PHASE 9: TEST - Execute tests → **USER APPROVAL**
- [ ] PHASE 10: DONE - Summary (NO auto-push)
