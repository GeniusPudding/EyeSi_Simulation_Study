#!/usr/bin/env python3
"""docs-viewer -- a standalone, project-agnostic Markdown/HTML/PDF browser.

Point it at any project directory and it serves a single-page web viewer that
lets you browse the folder tree, read/edit Markdown, view PDFs (rendered inline
via PDF.js, independent of browser settings), open HTML reports/demos, and
full-text search -- all with **live reload**: saving a file on disk updates the
open document and the tree automatically, no manual refresh.

It is fully self-contained: pure Python standard library, no build step. The
only runtime asset (PDF.js) is downloaded once into a per-user cache and reused
across every project.

Usage:
    python docs_viewer.py [ROOT] [--port 8777] [--host 127.0.0.1] [--no-browser]

    ROOT   directory to browse (default: current working directory)

Drop this folder (docs_viewer.py + viewer.html) into any repo, or keep it in one
place and run it against other projects with `python .../docs_viewer.py ROOT`.

API:
    GET  /                       -> viewer.html (next to this script)
    GET  /api/tree               -> {"root", "files":[{path,type}]}
    GET  /api/state              -> {"files":{path: "mtime-size"}}  (live-reload fingerprint)
    GET  /api/file?path=REL      -> raw text of a file
    GET  /api/raw?path=REL       -> raw bytes of an asset (inline)
    GET  /file/<relpath>         -> raw bytes via a path-style URL (relative links resolve)
    GET  /vendor/pdfjs/<f>       -> vendored PDF.js (per-user cache)
    POST /api/save {path,content}-> write a .md file back to disk
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
VIEWER = SCRIPT_DIR / "viewer.html"

# Set at startup from the CLI (the project directory being browsed).
ROOT = Path.cwd()

# .mjs/.js are not in every platform's mime registry; force JS so <script> works.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".idea", ".vscode", "vendor", ".docs_viewer"}
MD_EXT = {".md", ".markdown"}
ASSET_EXT = {".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

# PDF.js is cached once per user (shared across every project this tool serves).
PDFJS_CACHE = Path.home() / ".docs_viewer" / "pdfjs"
PDFJS_VERSION = "3.11.174"
PDFJS_FILES = {
    "pdf.min.js": f"https://cdn.jsdelivr.net/npm/pdfjs-dist@{PDFJS_VERSION}/build/pdf.min.js",
    "pdf.worker.min.js": f"https://cdn.jsdelivr.net/npm/pdfjs-dist@{PDFJS_VERSION}/build/pdf.worker.min.js",
}


def ensure_pdfjs() -> None:
    PDFJS_CACHE.mkdir(parents=True, exist_ok=True)
    for name, url in PDFJS_FILES.items():
        dest = PDFJS_CACHE / name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        try:
            print(f"  downloading PDF.js {name} ...", flush=True)
            with urllib.request.urlopen(url, timeout=30) as resp:
                dest.write_bytes(resp.read())
        except Exception as exc:  # noqa: BLE001 -- best-effort; viewer degrades gracefully
            print(f"  [!] could not fetch {name}: {exc}", file=sys.stderr)


def safe_resolve(rel: str) -> Path | None:
    if not rel:
        return None
    candidate = (ROOT / rel).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _classify(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in MD_EXT:
        return "md"
    if ext in ASSET_EXT:
        return "asset"
    return None


def _walk_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            ftype = _classify(name)
            if ftype is None:
                continue
            abs_path = Path(dirpath) / name
            if abs_path.resolve() == VIEWER.resolve():
                continue  # never list the viewer itself
            yield abs_path, ftype


def build_tree() -> dict:
    files = [{"path": p.relative_to(ROOT).as_posix(), "type": t} for p, t in _walk_files()]
    files.sort(key=lambda f: f["path"].lower())
    return {"root": ROOT.name, "files": files}


def build_state() -> dict:
    out = {}
    for p, _ in _walk_files():
        try:
            st = p.stat()
        except OSError:
            continue
        out[p.relative_to(ROOT).as_posix()] = f"{st.st_mtime_ns}-{st.st_size}"
    return {"files": out}


class Handler(BaseHTTPRequestHandler):
    server_version = "DocsViewer/2.0"

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, code, msg):
        self._json({"error": msg}, code)

    def log_message(self, *a):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        route, qs = parsed.path, parse_qs(parsed.query)
        if route in ("/", "/index.html", "/viewer.html"):
            return self._serve_viewer()
        if route == "/api/tree":
            return self._json(build_tree())
        if route == "/api/state":
            return self._json(build_state())
        if route == "/api/file":
            return self._serve_text(qs.get("path", [""])[0])
        if route == "/api/raw":
            return self._serve_inline(qs.get("path", [""])[0])
        if route.startswith("/file/"):
            return self._serve_inline(unquote(route[len("/file/"):]))
        if route.startswith("/vendor/pdfjs/"):
            return self._serve_vendor(route[len("/vendor/pdfjs/"):])
        return self._error(404, "not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/save":
            return self._error(404, "not found")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return self._error(400, "bad json")
        target = safe_resolve(payload.get("path", ""))
        if target is None:
            return self._error(400, "path escapes root")
        if target.suffix.lower() not in MD_EXT:
            return self._error(400, "only markdown files may be saved")
        try:
            target.write_text(payload.get("content", ""), encoding="utf-8", newline="\n")
        except OSError as exc:
            return self._error(500, f"write failed: {exc}")
        return self._json({"ok": True, "path": payload.get("path"),
                           "bytes": len(payload.get("content", "").encode("utf-8"))})

    def _serve_viewer(self):
        if not VIEWER.exists():
            return self._error(500, "viewer.html missing next to docs_viewer.py")
        self._send(200, VIEWER.read_bytes(), "text/html; charset=utf-8")

    def _serve_text(self, rel):
        target = safe_resolve(rel)
        if target is None or not target.is_file():
            return self._error(404, "no such file")
        self._send(200, target.read_bytes(), "text/plain; charset=utf-8")

    def _serve_inline(self, rel):
        target = safe_resolve(rel)
        if target is None or not target.is_file():
            return self._error(404, "no such file")
        ctype, _ = mimetypes.guess_type(str(target))
        ascii_name = target.name.encode("ascii", "ignore").decode("ascii") or "file"
        disp = f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(target.name)}"
        self._send(200, target.read_bytes(), ctype or "application/octet-stream",
                   extra={"Content-Disposition": disp})

    def _serve_vendor(self, rel):
        target = (PDFJS_CACHE / rel).resolve()
        try:
            target.relative_to(PDFJS_CACHE.resolve())
        except ValueError:
            return self._error(400, "bad vendor path")
        if not target.is_file():
            return self._error(404, "vendor asset missing")
        ctype, _ = mimetypes.guess_type(str(target))
        self._send(200, target.read_bytes(), ctype or "application/octet-stream")


def main() -> int:
    global ROOT
    ap = argparse.ArgumentParser(description="Standalone Markdown/HTML/PDF docs viewer with live reload.")
    ap.add_argument("root", nargs="?", default=".", help="directory to browse (default: current dir)")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    ROOT = Path(args.root).resolve()
    if not ROOT.is_dir():
        print(f"[!] not a directory: {ROOT}", file=sys.stderr)
        return 1
    if not VIEWER.exists():
        print(f"[!] viewer.html not found next to {Path(__file__).name}", file=sys.stderr)
        return 1

    print("Preparing PDF.js (first run downloads ~1.4 MB into ~/.docs_viewer) ...")
    ensure_pdfjs()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"docs-viewer  ->  browsing: {ROOT}")
    print(f"             ->  open: {url}   (live reload on; Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
