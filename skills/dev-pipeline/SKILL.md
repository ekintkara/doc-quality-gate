---
name: dev-pipeline
description: "Human-in-the-loop development pipeline. Supports any project, any task source (Jira, Azure DevOps, GitHub Issues, files, free text). Uses DQG for implementation document review, multi-agent TODO review, and test planning. Every phase requires user approval. Auto-generates context and auto-installs DQG. Use when: implement TASK-123, /dev-pipeline TASK-123, continue pipeline. Do NOT use for: general coding questions, single-file edits, git operations, code explanations, or tasks that don't need a structured implementation pipeline."
license: MIT
metadata:
  author: ekintkara
  version: 0.4.0
  category: development
  tags: [pipeline, code-review, testing, dqg, implementation-document, multi-agent]
  documentation: https://ekintkara.github.io/doc-quality-gate/
compatibility: "Requires Python 3.11+, Node.js 18+, and Git. Works with Claude Code, OpenCode, Cursor, and Claude.ai."
---

# Dev Pipeline

Human-in-the-loop pipeline. Reads task → generates implementation doc → DQG review → TODO → implement → test. Every phase waits for user approval.

## Critical Rules

1. **Never push/commit** unless user explicitly says "push" or "commit"
2. **Never skip phases** — present summary and wait for approval at each `[USER]` checkpoint
3. **Adapt to user changes** — if user modifies anything, incorporate and continue
4. **ALWAYS pass `--project` to DQG** — target project path (CWD), never DQG's own directory. DQG cross-references against this project. Missing `--project` = wrong codebase review
5. **Validate DQG cross-reference results** — after REVIEW_DOC, pick 3-5 "missing" items from DQG report and grep the codebase. Mark false positives. Never present DQG results without verification

## When to Use

### Use when
- `implement TASK-123` / `implement AB#456` / `implement owner/repo#42`
- `/dev-pipeline {task-reference-or-free-text}`
- `continue pipeline` / `resume pipeline`

### Do NOT use when
- General coding questions or explanations
- Single-file quick edits
- Git operations (`commit`, `push`, `merge`)
- Bug fixes without structured implementation
- Code review without full pipeline

## Examples

### Example 1: Jira task
```
User: "implement PROJ-123"
→ Pipeline reads Jira task → generates impl doc → DQG review → TODO → implement → test
```

### Example 2: Azure DevOps
```
User: "implement AB#456"
→ Pipeline reads Azure work item → full pipeline cycle
```

### Example 3: Free text
```
User: "/dev-pipeline Add dark mode toggle to settings page"
→ Pipeline creates impl doc from description → full review cycle
```

### Example 4: Resume
```
User: "continue pipeline"
→ Reads .pipeline/{KEY}-state.json → resumes from last checkpoint
```

## Configuration

Read from project's `AGENTS.md` or `CLAUDE.md` under `## Pipeline Config`. Defaults:

```markdown
## Pipeline Config
task_source: jira                # jira | azure-devops | github | manual
jira_tool: auto                  # auto | mcp | acli | api
dqg_repo: https://github.com/ekintkara/doc-quality-gate.git
dqg_path: ~/doc-quality-gate
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

Each phase has detailed instructions in `references/` files. Read the relevant file when starting a phase.

| Phase | Goal | Instructions |
|---|---|---|
| 0: DQG_ENSURE | Install, configure, start DQG | See `references/dqg-ensure.md` |
| 1: TASK_INTAKE | Read task from source | See `references/task-intake.md` |
| 1.5: CONTEXT_CHECK | Ensure/generate project context | See `references/context-generator.md` |
| 2: IMPL_DOC | Generate implementation document | Generate from task + codebase analysis, save to `.pipeline/{KEY}-impl-doc.md`. See `assets/impl-doc-template.md` for structure |
| 3: REVIEW_DOC | DQG multi-agent review + scoring | Run via `scripts/dqg_run.py launch`, poll until complete. Score < 8.0 → iterate with `rescore` |
| 3.1: VALIDATE_XREF | Verify DQG cross-reference results | Grep codebase for "missing" items, mark false positives, present only confirmed issues to user |
| 4: PLAN | Generate TODO list | See `references/todo-generator.md` |
| 5: REVIEW_TODO | 3x parallel review + judge | See `references/todo-reviewer.md`, `references/todo-judge.md` |
| 6: IMPLEMENT | Execute TODOs | See `references/implementer.md` |
| 7: REVIEW_IMPL | 3x parallel code review + judge | See `references/doc-reviewer.md`, `references/doc-judge.md` |
| 8: TEST_PLAN | Create test plan | See `references/test-planner.md` |
| 9: TEST | Execute tests | Run via bash, collect results |
| 10: DONE | Summary | Present outputs, never auto-push |

### Phase 3: DQG Review (critical notes)

- **MANDATORY:** Always pass `--project` pointing to the TARGET project (the user's CWD). Never omit it. Without it, DQG cross-references its own Python codebase instead of the user's project.
- Use `launch` + `poll` pattern — NOT `auto-review`
- `launch` auto-starts proxy + web server, returns `REVIEW_STARTED review_id=XXXXX`
- Poll in loop: `scripts/dqg_run.py poll {review_id} --max-attempts 3` until COMPLETE/FAILED
- Score < 8.0: use `rescore` (5x faster) up to `max_review_iterations`
- Results: `{run_dir}/scorecard.json`, `revised.md`, `report.md`, `issues.json`

Example:
```bash
python scripts/dqg_run.py launch .pipeline/PROJ-123-impl-doc.md --project /path/to/target/project --cp .context/
```

### Phase 3.1: Post-Review Validation (mandatory)

After DQG returns cross-reference issues, validate before presenting to user:
1. Read `issues.json` from results directory
2. For each HIGH/CRITICAL issue claiming "X not found in codebase":
   - Run `grep -r "X" --include="*.cs" --include="*.py" --include="*.ts"` in the target project
   - Run `grep -r "class X" --include="*.cs" --include="*.py" --include="*.ts"` for class-level claims
   - Run `grep -r "interface IX" --include="*.cs"` for interface claims
3. If found → mark as **FALSE POSITIVE**, note actual file path
4. If genuinely missing → mark as **CONFIRMED**
5. Present only CONFIRMED issues + FALSE POSITIVE summary to user

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

## Troubleshooting

### DQG won't start
- **Cause:** Python 3.11+ or .venv missing
- **Solution:** Run Phase 0 again, verify Python version. Check `.env` has required keys.

### Jira authentication failed
- **Cause:** Missing or expired credentials
- **Solution:** Check `.env` file for `DQG_JIRA_*` vars, or run `acli jira auth login`

### Pipeline stuck on REVIEW_DOC
- **Cause:** DQG review takes 5-15 minutes per iteration
- **Solution:** Check `http://localhost:8080` dashboard, poll again

### Context generation fails
- **Cause:** Large codebase or missing language server
- **Solution:** Provide `.context/` directory manually, or specify `context_path` in Pipeline Config

## Composability

This skill works alongside other skills. It manages the pipeline workflow (task → doc → review → implement → test). Individual phases may benefit from other skills (e.g., sonar-analyze for code quality, frontend-design for UI work).

## Error Handling

- DQG error → self-heal via `references/dqg-ensure.md`, retry once
- Agent error → retry once, report to user
- Lint/typecheck error → fix (max 3 attempts), ask user if still failing

