# Changelog

All notable changes to the dev-pipeline skill are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**This file MUST be updated with every change.** Before merging any PR, verify the changelog entry exists.

## [Unreleased]

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
