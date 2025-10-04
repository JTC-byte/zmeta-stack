from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from markdown import markdown

DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs"

router = APIRouter(prefix="/docs/local", tags=["docs"])


def _doc_files() -> Iterable[Path]:
    return sorted(p for p in DOCS_ROOT.glob('*.md') if p.is_file())


def _doc_slug(path: Path) -> str:
    return path.stem


def _doc_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            return stripped.lstrip('#').strip() or path.stem
    return path.stem.replace('_', ' ').title()


def _render_markdown(source: Path) -> str:
    if not source.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    text = source.read_text(encoding="utf-8")
    html_body = markdown(text, extensions=["fenced_code", "tables"])
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>ZMeta Documentation</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 960px; line-height: 1.6; color: #1a1c1f; }}
    pre {{ background: #f4f6fb; padding: 1rem; overflow-x: auto; border-radius: 4px; }}
    code {{ background: #f4f6fb; padding: 0.2rem 0.4rem; border-radius: 4px; }}
    h1, h2, h3 {{ color: #0f1419; }}
    a {{ color: #0077cc; text-decoration: none; }}
    ul {{ margin-left: 1.2rem; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>
"""


def _render_index(entries: Iterable[Tuple[str, str]]) -> str:
    items = '\n'.join(f'<li><a href="{slug}">{title}</a></li>' for slug, title in entries)
    body = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>ZMeta Documentation</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem auto; max-width: 960px; line-height: 1.6; color: #1a1c1f; }}
    h1 {{ color: #0f1419; }}
    a {{ color: #0077cc; text-decoration: none; }}
    ul {{ margin-left: 1.2rem; }}
  </style>
</head>
<body>
  <h1>ZMeta Documentation</h1>
  <p>Select a document:</p>
  <ul>
    {items}
  </ul>
</body>
</html>
"""
    return body


@router.get("", response_class=HTMLResponse)
async def docs_index() -> HTMLResponse:
    entries = [(f"/docs/local/{_doc_slug(path)}", _doc_title(path)) for path in _doc_files()]
    html = _render_index(entries)
    return HTMLResponse(content=html)


@router.get("/{slug}", response_class=HTMLResponse)
async def doc_by_slug(slug: str) -> HTMLResponse:
    slug = slug.lower()
    target = next((p for p in _doc_files() if _doc_slug(p).lower() == slug), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return HTMLResponse(content=_render_markdown(target))


async def pipeline_docs() -> HTMLResponse:
    target = next((p for p in _doc_files() if p.stem in {"pipeline", "ingest_pipeline"}), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Pipeline documentation not found")
    return HTMLResponse(content=_render_markdown(target))


router.add_api_route("/pipeline", pipeline_docs, methods=["GET"], response_class=HTMLResponse)


__all__ = ["router", "pipeline_docs"]
