#!/usr/bin/env python3
"""Backward-compatible launcher for the docs viewer.

The viewer is now a standalone, project-agnostic tool living in ../docs-viewer/.
This shim just points it at the repo root so the historical command

    python scripts/serve_docs.py

keeps working -- now with live reload. All flags (--port, --host, --no-browser)
are forwarded. To browse a *different* project, run the tool directly:

    python docs-viewer/docs_viewer.py <some-other-dir>
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "docs-viewer" / "docs_viewer.py"

if not TOOL.exists():
    sys.exit(f"[!] docs-viewer tool not found at {TOOL}")

raise SystemExit(subprocess.call([sys.executable, str(TOOL), str(REPO), *sys.argv[1:]]))
