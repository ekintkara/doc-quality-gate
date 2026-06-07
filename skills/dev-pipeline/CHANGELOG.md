# Changelog

All notable changes to the dev-pipeline skill are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**This file MUST be updated with every change.** Before merging any PR, verify the changelog entry exists.

## [Unreleased]

## [0.5.0] - 2026-06-08

### Fixed
- **Critical:** DQG cross-reference false positives for C#/.NET projects
  - Root cause: `codebase_context.py` had no C# pattern support — could not detect ASP.NET controllers, endpoints, entities, or interfaces
  - Added C# ASP.NET route patterns: `[HttpGet]`, `[HttpPost]`, `[Route]`, `MapGet`/`MapPost`
  - Added C# entity/model detection: `class`, `record` with property extraction
  - Added `_extract_csharp_properties()` helper for C# auto-properties
  - Added `.csproj` dependency extraction (`<PackageReference>` parsing)
  - Added `.cs` to scanned file extensions in `_extract_api_routes()` and `_extract_db_models()`
- **Critical:** DQG review results presented without verification
  - Added Critical Rule #5: validate DQG cross-reference results before presenting to user
  - Added Phase 3.1 (VALIDATE_XREF): grep codebase for "missing" items, mark false positives
  - Only confirmed issues are presented to user

## [0.4.0] - 2026-06-08

### Changed
- **BREAKING:** `prompts/` directory renamed to `references/` (Anthropic skill standard)
- `## Rules` renamed to `## Critical Rules` (guide recommendation for critical instructions)
- SKILL.md references updated from `prompts/` to `references/`
- Description expanded with negative triggers (Do NOT use for: ...)

### Fixed
- **Critical:** DQG review cross-referenced wrong codebase (its own Python code instead of target project)
  - Root cause: `--project` parameter was not passed to `launch` command
  - Fix: Critical Rule #4 added — ALWAYS pass `--project` to DQG
  - Fix: `scripts/dqg_run.py` now auto-injects `--project=CWD` if missing
  - Fix: `scripts/dqg_run.py` now validates `--project` does NOT point to DQG's own directory
  - Fix: Phase 3 description now includes explicit `--project` warning and example command

### Added
- YAML frontmatter: `license`, `metadata` (author, version, category, tags, documentation), `compatibility`
- `## Examples` section with 4 usage scenarios (Jira, Azure, Free text, Resume)
- `## When to Use` split into "Use when" and "Do NOT use when" subsections
- `## Troubleshooting` section (DQG start, Jira auth, stuck review, context generation)
- `## Composability` note for multi-skill usage
- `scripts/` directory with `dqg_run.py` thin wrapper (locates DQG install + delegates)
- `assets/` directory with `impl-doc-template.md` (standard implementation document structure)
- DQG path search now includes `~/Desktop/doc-quailty-gate` (common macOS location)
- Analysis document at `docs/skill-audit-complete-guide.md`

### Removed
- `## Version` section from SKILL.md (developer-only note, not user-facing)

## [0.3.0] - 2026-06-08

### Changed
- **BREAKING:** SKILL.md refactored from 686 to 116 lines — phase details moved to `prompts/` files (progressive disclosure)
- Golden Rules reduced from 7 to 3 concise rules
- Verbose user presentation templates removed (Claude decides format)
- Added TOC to prompt files over 100 lines: `context-generator.md`, `dqg-ensure.md`, `task-intake.md`
- All Windows backslash paths converted to forward slashes (cross-platform)

### Added
- Atlassian CLI (`acli`) support as Jira reading fallback (MCP → `acli` → REST API)
- `jira_tool` config option: `auto | mcp | acli | api`
- All task source usage examples to quick-start, overview, and task-intake docs

### Removed
- All obilet-specific references from codebase (hardcoded URLs, paths, project keys, emails)
- Hardcoded Jira defaults (`obilet.atlassian.net`, `PDB`) — now require env vars or config

## [0.2.0] - 2026-06-07

### Added
- GitHub Pages deployment workflow (`.github/workflows/deploy-website.yml`)
- GitHub Pages enabled with GitHub Actions as build source
- Fixed Docusaurus `baseUrl` from `/doc-quality-gate/` to `/doc-quailty-gate/`
- Fixed all `doc-quality-gate` references to match actual repo name `doc-quailty-gate`

## [0.1.0] - 2026-06-07

### Added
- Initial skill release with 10-phase human-in-the-loop pipeline
- Task sources: Jira (MCP), Azure DevOps (`az`), GitHub Issues (`gh`), File, Free text
- DQG engine integration for multi-agent document review
- Context auto-generation from codebase
- Multi-agent TODO review (completeness, order, practicality + judge)
- Multi-agent implementation review (compliance, quality, pattern + judge)
- Test planning and execution phases
- Pipeline state file for resume support
- 11 prompt files in `prompts/` directory
