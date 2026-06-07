#!/usr/bin/env python3
"""DQG runner wrapper for the dev-pipeline skill.

Thin wrapper that locates the DQG installation and delegates
to the real dqg_run.py in the DQG repo. Adds safety checks:

- For 'launch' command: if --project is missing, defaults to CWD
- Validates that --project does NOT point to DQG's own directory

Usage:
    python scripts/dqg_run.py launch path/to/doc.md --project /path/to/project
    python scripts/dqg_run.py poll <review_id>
    python scripts/dqg_run.py rescore <review_id>
    python scripts/dqg_run.py from-jira PROJ-123 --cp /path/to/context

Resolves DQG path from:
    1. DQG_PATH env var
    2. Pipeline Config in AGENTS.md / CLAUDE.md (dqg_path)
    3. ~/doc-quality-gate
    4. ~/Desktop/doc-quality-gate
"""

import os
import subprocess
import sys
from pathlib import Path

_DEFAULT_DQG_PATHS = [
    Path.home() / "doc-quality-gate",
    Path.home() / "Desktop" / "doc-quality-gate",
    Path.home() / "doc-quailty-gate",
    Path.home() / "Desktop" / "doc-quailty-gate",
]


def _find_dqg_root():
    env_path = os.environ.get("DQG_PATH")
    if env_path:
        p = Path(env_path)
        if (p / "scripts" / "dqg_run.py").exists():
            return p

    for p in _DEFAULT_DQG_PATHS:
        if (p / "scripts" / "dqg_run.py").exists():
            return p

    print("ERROR: DQG installation not found.")
    print("Set DQG_PATH env var or run Phase 0 (DQG_ENSURE) first.")
    sys.exit(1)


def _inject_default_project(args, dqg_root):
    if len(args) == 0 or args[0] not in ("launch", "auto-review", "start", "review"):
        return args

    has_project = False
    for i, a in enumerate(args):
        if a in ("--project", "-p") and i + 1 < len(args):
            has_project = True
            project_path = Path(args[i + 1]).resolve()
            dqg_resolved = dqg_root.resolve()
            if project_path == dqg_resolved or dqg_resolved in project_path.parents:
                print(f"ERROR: --project points to DQG's own directory: {project_path}")
                print(f"DQG is at: {dqg_resolved}")
                print("The --project must point to the TARGET project, not DQG.")
                sys.exit(1)
            break

    if not has_project:
        cwd = str(Path.cwd().resolve())
        args = args[:1] + ["--project", cwd] + args[1:]
        print(f"AUTO: --project not provided, using CWD: {cwd}")

    return args


def main():
    dqg_root = _find_dqg_root()
    real_script = dqg_root / "scripts" / "dqg_run.py"
    args = sys.argv[1:]
    args = _inject_default_project(args, dqg_root)
    result = subprocess.run(
        [sys.executable, str(real_script)] + args,
        cwd=str(dqg_root),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
