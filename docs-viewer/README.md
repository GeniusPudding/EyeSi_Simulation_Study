# docs-viewer

A standalone, project-agnostic **Markdown / HTML / PDF documentation browser** with
**live reload**. Point it at any project directory and read the whole docs tree in
your browser — no build step, no dependencies beyond Python's standard library.

It is self-contained: `docs_viewer.py` + `viewer.html`. Copy this folder into any
repo, or keep it in one place and run it against other projects.

## Quick start

```bash
python docs_viewer.py                 # browse the current directory
python docs_viewer.py C:\path\to\repo # browse another project
python docs_viewer.py . --port 9000   # pick a port
python docs_viewer.py . --no-browser  # don't auto-open a browser
```

Opens `http://127.0.0.1:8777/` by default. Stop with `Ctrl+C`.

The first run downloads PDF.js (~1.4 MB) once into `~/.docs_viewer/` and reuses it
for every project afterwards.

## Features

| Feature | Notes |
|---|---|
| **Folder tree** | Collapsible, follows the project's real subfolders. Markdown reads inline; PDFs, HTML reports/demos, and images render inline too. |
| **Live reload** | Saving a file on disk updates the open document and the tree automatically — no manual refresh. Unsaved edits in the built-in editor are protected (a conflict banner lets you choose). Toggle with the **刷新 / Live** button. |
| **Inline PDF** | Rendered with PDF.js on a canvas, independent of the browser's "download vs open PDF" setting. |
| **HTML reports** | `*.html` files open embedded; relative links inside them (to other reports or `.md`) navigate seamlessly inside the viewer, and the tree highlight stays in sync. |
| **Markdown render** | GFM tables, fenced code, blockquotes, lists, images, and Unicode math notation. |
| **Full-text search** | `Ctrl+K`. Searches filenames + contents across all Markdown and HTML (HTML is tag-stripped). Click a hit to jump and highlight. |
| **Edit & save** | `Ctrl+E` toggles a split editor with live preview; `Ctrl+S` writes back to disk (Markdown only). |
| **Light / dark** | Follows the OS; `◐` toggles manually. |

## Keyboard shortcuts

- `Ctrl+K` focus search · `Esc` clear search
- `Ctrl+E` toggle edit/read · `Ctrl+S` save

## How it works

`docs_viewer.py` is a tiny `http.server` that walks the target directory and exposes
a small JSON API (`/api/tree`, `/api/state`, `/api/file`, `/api/raw`, `/file/…`,
`/api/save`, `/vendor/pdfjs/…`). `viewer.html` is a single-page front end with a
hand-written Markdown renderer — no external runtime dependencies. Live reload is a
1 Hz poll of `/api/state` (a per-file `mtime-size` fingerprint) that the page diffs
to refresh only what changed.

Saving is restricted to Markdown files inside the browsed root; path traversal is
rejected.

## Security note

Serves on `127.0.0.1` (localhost) only by default. It exposes read access to every
file under the target directory over HTTP and write access to Markdown files — run it
only on directories you trust, and do not bind it to a public interface (`--host`).
