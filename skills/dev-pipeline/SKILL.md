---
name: dev-pipeline
description: "Human-in-the-loop development pipeline. Supports any project, any task source (Jira, Azure DevOps, GitHub Issues, files, free text). Uses DQG for implementation document review, multi-agent TODO review, and test planning. Every phase requires user approval. Auto-generates context and auto-installs DQG. Use when: implement TASK-123, /dev-pipeline TASK-123, continue pipeline."
---

# Dev Pipeline

Human-in-the-loop pipeline. Reads task → generates implementation doc → DQG review → TODO → implement → test. Every phase waits for user approval.

## Rules

1. **Never push/commit** unless user explicitly says "push" or "commit"
2. **Never skip phases** — present summary and wait for approval at each `[USER]` checkpoint
3. **Adapt to user changes** — if user modifies anything, incorporate and continue

## When to Use

- `implement TASK-123` / `implement AB#456` / `implement owner/repo#42`
- `/dev-pipeline {task-reference-or-free-text}`
- `continue pipeline` / `resume pipeline`

## Configuration

Read from project's `AGENTS.md` or `CLAUDE.md` under `## Pipeline Config`. Defaults:

```markdown
## Pipeline Config
task_source: jira                # jira | azure-devops | github | manual
jira_tool: auto                  # auto | mcp | acli | api
dqg_repo: https://github.com/ekintkara/doc-quailty-gate.git
dqg_path: ~/doc-quailty-gate
# azure_devops_org: myorg
# azure_devops_project: MyProject
# github_repo: owner/repo
context_path: .context/
review_agents: 3
max_review_iterations: 2
```

## Pipeline Flow

```
DQG_ENSURE → TASK_INTAKE → [USER] → CONTEXT_CHECK → [USER] →
IMPL_DOC → [USER] → REVIEW_DOC(DQG) → [USER] → PLAN → [USER] →
REVIEW_TODO → [USER] → IMPLEMENT → REVIEW_IMPL → [USER] →
TEST_PLAN → [USER] → TEST → [USER] → DONE
```

## Task Source Detection

| Input Pattern | Source | Tool |
|---|---|---|
| `[A-Z]+-\d+` | Jira | MCP → `acli` → REST API |
| `AB#\d+` or `#\d+` | Azure DevOps | `az boards work-item show` |
| `owner/repo#\d+` | GitHub Issue | `gh issue view` |
| `.md`/`.txt`/`.json` path | File | `read` tool |
| Anything else | Free text | Use as-is |

## Phase Details

Each phase has detailed instructions in `prompts/` files. Read the relevant file when starting a phase.

| Phase | Goal | Instructions |
|---|---|---|
| 0: DQG_ENSURE | Install, configure, start DQG | See `prompts/dqg-ensure.md` |
| 1: TASK_INTAKE | Read task from source | See `prompts/task-intake.md` |
| 1.5: CONTEXT_CHECK | Ensure/generate project context | See `prompts/context-generator.md` |
| 2: IMPL_DOC | Generate implementation document | Generate from task + codebase analysis, save to `.pipeline/{KEY}-impl-doc.md` |
| 3: REVIEW_DOC | DQG multi-agent review + scoring | Launch via `dqg_run.py launch`, poll until complete. Score < 8.0 → iterate with `rescore` |
| 4: PLAN | Generate TODO list | See `prompts/todo-generator.md` |
| 5: REVIEW_TODO | 3x parallel review + judge | See `prompts/todo-reviewer.md`, `prompts/todo-judge.md` |
| 6: IMPLEMENT | Execute TODOs | See `prompts/implementer.md` |
| 7: REVIEW_IMPL | 3x parallel code review + judge | Review against implementation doc |
| 8: TEST_PLAN | Create test plan | See `prompts/test-planner.md` |
| 9: TEST | Execute tests | Run via bash, collect results |
| 10: DONE | Summary | Present outputs, never auto-push |

### Phase 3: DQG Review (critical notes)

- Use `launch` + `poll` pattern — NOT `auto-review`
- `launch` auto-starts proxy + web server, returns `REVIEW_STARTED review_id=XXXXX`
- Poll in loop: `dqg_run.py poll {review_id} --max-attempts 3` until COMPLETE/FAILED
- Score < 8.0: use `rescore` (5x faster) up to `max_review_iterations`
- Results: `{run_dir}/scorecard.json`, `revised.md`, `report.md`, `issues.json`

## State File

`.pipeline/{TASK_KEY}-state.json` tracks current phase and artifacts. Used for resume support.

## Context Auto-Discovery

AGENTS.md → CLAUDE.md → .context/ → GEMINI.md → README.md → codebase-retrieval → ask user

## Output Directory

```
.pipeline/
├── {TASK_KEY}-state.json
├── context/                    # Auto-generated if none provided
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

## Error Handling

- DQG error → self-heal via `prompts/dqg-ensure.md`, retry once
- Agent error → retry once, report to user
- Lint/typecheck error → fix (max 3 attempts), ask user if still failing

## Version

See [CHANGELOG.md](CHANGELOG.md) for version history. **Every change MUST have a changelog entry.**
