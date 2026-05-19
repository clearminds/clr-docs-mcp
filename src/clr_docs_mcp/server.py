"""clr-docs-mcp — FastMCP server for the clearminds Zensical docs site."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from clr_docs_mcp.config import Settings
from clr_docs_mcp.index import DocsIndex

mcp = FastMCP("clearminds Docs")
_settings: Settings | None = None
_index: DocsIndex | None = None


def _site_url(location: str) -> str:
    """Build a full URL from a search-index location.

    Args:
        location: ``arista/docs/MLAG.html#peer-link``-style relative path.

    Returns:
        The full URL (no trailing slash on the base).
    """
    if not _settings:
        return location
    base = _settings.docs_site_url.rstrip("/")
    if not location:
        return base + "/"
    return f"{base}/{location.lstrip('/')}"


def _resolve_markdown(page_path: str) -> Path | None:
    """Map a published page path to the source markdown file.

    Zensical maps ``docs/<rest>.md`` → ``<rest>.html`` (or ``index.html``
    for ``README.md``). Reverse that:

    - ``arista/docs/MLAG.html`` → ``docs/arista/docs/MLAG.md``
    - ``arista/README.html``    → ``docs/arista/README.md``
    - ``arista/``               → ``docs/arista/index.md`` or ``README.md``

    Args:
        page_path: Path relative to the docs site root, with or without
            an ``.html`` suffix. Heading fragments are stripped.

    Returns:
        Path to the source markdown, or None if no match found.
    """
    if not _settings:
        return None
    repo = _settings.docs_repo_path
    page = page_path.split("#", 1)[0].lstrip("/")

    # Try a few common rewrites in order.
    candidates: list[Path] = []
    if page.endswith(".html"):
        candidates.append(repo / "docs" / page.replace(".html", ".md"))
    if page.endswith("/"):
        candidates.append(repo / "docs" / (page + "index.md"))
        candidates.append(repo / "docs" / (page + "README.md"))
    if not page.endswith((".md", ".html", "/")):
        # Bare path, try as both a page and a directory.
        candidates.append(repo / "docs" / f"{page}.md")
        candidates.append(repo / "docs" / page / "index.md")
        candidates.append(repo / "docs" / page / "README.md")
    # Always try the literal path too — caller may have given a .md path.
    if page.endswith(".md"):
        candidates.append(repo / "docs" / page)

    for c in candidates:
        if c.is_file():
            return c
    return None


@mcp.tool
def docs_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the clearminds docs site.

    Searches every heading and body across all categories (arista, mikrotik,
    sentry, monitoring, proxmox, devices, sessions, etc.). Title matches
    weigh 3x text matches. Returns the top ``limit`` results.

    Args:
        query: Free-text query. Multi-token; matches are summed.
        limit: Maximum results (default 10).

    Returns:
        List of result dicts:

            {
              "title":    heading title,
              "path":     nav breadcrumbs (e.g. "Arista EOS > MLAG"),
              "url":      full URL to the heading,
              "snippet":  text excerpt centered on the first match,
              "score":    raw scoring weight (higher = better match)
            }
    """
    if not _index:
        return []
    results = _index.search(query, limit=limit)
    for r in results:
        r["url"] = _site_url(r.pop("location"))
    return results


@mcp.tool
def docs_read(path: str) -> dict[str, Any]:
    """Read the full markdown source of a docs page.

    Accepts published paths (``arista/docs/MLAG.html``), source paths
    (``arista/docs/MLAG.md``), or directory-like paths (``arista/``).
    Heading fragments are stripped.

    Args:
        path: Page path. See examples above.

    Returns:
        Dict with ``path``, ``markdown``, ``url``. If not found, ``markdown``
        is empty and ``error`` is populated.
    """
    md_path = _resolve_markdown(path)
    if not md_path:
        return {
            "path": path,
            "markdown": "",
            "url": _site_url(path),
            "error": f"No markdown source found for {path!r}",
        }
    return {
        "path": str(md_path.relative_to(_settings.docs_repo_path)) if _settings else str(md_path),
        "markdown": md_path.read_text(),
        "url": _site_url(path),
    }


@mcp.tool
def docs_list(prefix: str = "") -> list[str]:
    """List unique page paths in the docs site, optionally filtered by prefix.

    Useful for discovery: ``docs_list("sessions/")`` returns every session
    note, ``docs_list("arista/")`` returns every Arista page, etc.

    Args:
        prefix: Optional prefix filter (e.g. ``"sessions/clearthink/"``).
            Pass an empty string for the full list.

    Returns:
        Sorted list of page paths.
    """
    if not _index:
        return []
    return _index.list_paths(prefix or None)


def main() -> None:
    """Entry point for the MCP server."""
    global _settings, _index

    parser = argparse.ArgumentParser(description="clr-docs-mcp")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http", "streamable-http", "sse"],
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("clr-docs-mcp")

    _settings = Settings()
    try:
        _index = DocsIndex.load(_settings.docs_repo_path)
    except FileNotFoundError as e:
        log.error(
            "search.json not found at %s — make sure the docs repo is cloned "
            "and CI has produced public/search.json: %s",
            _settings.docs_repo_path,
            e,
        )
        sys.exit(1)

    log.info(
        "Loaded %d index items from %s",
        len(_index._items),
        _settings.docs_repo_path,
    )

    # When running HTTP for container deployment, FastMCP defaults to
    # 127.0.0.1:8000 which is unreachable from outside the container.
    # Honour HOST/PORT env vars for the streamable-http / sse transports.
    if args.transport in {"http", "streamable-http", "sse"}:
        mcp.settings.host = os.getenv("HOST", "0.0.0.0")
        mcp.settings.port = int(os.getenv("PORT", "8000"))
        log.info("HTTP transport: listening on %s:%s/mcp", mcp.settings.host, mcp.settings.port)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
