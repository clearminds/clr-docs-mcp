"""Load + query the Zensical search.json index.

Zensical's index format (as of 2026-05):

    {
      "config": {"separator": "..."},
      "items": [
        {
          "location": "arista/docs/MLAG.html#peer-link",  # may be ""
          "level": 2,                                      # heading depth
          "title": "Peer-link",
          "text": "<p>...html-stripped-ish body...</p>",
          "path": ["Arista EOS", "MLAG Configuration"],    # nav crumbs
          "tags": []
        },
        ...
      ]
    }

We do simple substring + token scoring. 1500-ish items, fits comfortably in
memory and Python list scans are plenty fast at this scale — no need for
tantivy / whoosh / FTS5.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    """Drop HTML tags + collapse whitespace.

    Zensical's ``text`` field is HTML-ish; we want plain text for snippets
    and matching.

    Args:
        text: HTML or HTML-ish string.

    Returns:
        Plain text with whitespace collapsed.
    """
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def _tokenize(s: str) -> list[str]:
    """Lowercase, split on non-alphanumerics."""
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


class DocsIndex:
    """In-memory wrapper around Zensical's search.json."""

    def __init__(self, items: list[dict[str, Any]]):
        self._items = items
        # Pre-compute lowercase title/text for fast scanning.
        self._lc_titles = [it.get("title", "").lower() for it in items]
        self._plain_texts = [_strip_html(it.get("text", "")) for it in items]
        self._lc_texts = [t.lower() for t in self._plain_texts]

    @classmethod
    def load(cls, repo_path: Path) -> DocsIndex:
        """Load the index from ``<repo_path>/public/search.json``.

        Args:
            repo_path: Local docs repo root.

        Returns:
            A ready-to-query DocsIndex.

        Raises:
            FileNotFoundError: search.json doesn't exist yet (CI hasn't run,
                or the repo clone is incomplete).
        """
        search_json = repo_path / "public" / "search.json"
        data = json.loads(search_json.read_text())
        return cls(data.get("items", []))

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the top ``limit`` matches for ``query``.

        Scoring: title hits weight 3x text hits. Per-token matches sum.
        Plenty good for 1500 items; if/when we need real ranking, swap
        this for BM25.

        Args:
            query: Free-text query.
            limit: Max results.

        Returns:
            List of result dicts with title, path, location, score, snippet.
        """
        tokens = _tokenize(query)
        if not tokens:
            return []

        scored: list[tuple[int, int]] = []  # (score, item_index)
        for i, _ in enumerate(self._items):
            title = self._lc_titles[i]
            text = self._lc_texts[i]
            score = 0
            for tok in tokens:
                score += title.count(tok) * 3
                score += text.count(tok)
            if score > 0:
                scored.append((score, i))

        scored.sort(key=lambda x: -x[0])

        results: list[dict[str, Any]] = []
        for score, i in scored[:limit]:
            it = self._items[i]
            results.append(
                {
                    "title": it.get("title", ""),
                    "path": " > ".join(it.get("path", [])),
                    "location": it.get("location", ""),
                    "score": score,
                    "snippet": self._snippet(self._plain_texts[i], tokens),
                }
            )
        return results

    def _snippet(self, plain_text: str, tokens: list[str], max_len: int = 280) -> str:
        """Return a short window around the first matching token.

        Args:
            plain_text: HTML-stripped body text.
            tokens: Lowercased query tokens.
            max_len: Max snippet length.

        Returns:
            A snippet of at most ``max_len`` chars, centered on first match.
        """
        if not plain_text:
            return ""
        lc = plain_text.lower()
        pos = -1
        for tok in tokens:
            p = lc.find(tok)
            if p != -1 and (pos == -1 or p < pos):
                pos = p
        if pos == -1:
            return plain_text[:max_len]
        start = max(0, pos - max_len // 3)
        end = min(len(plain_text), start + max_len)
        snippet = plain_text[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(plain_text):
            snippet = snippet + "…"
        return snippet

    def list_paths(self, prefix: str | None = None) -> list[str]:
        """List unique top-level locations, optionally filtered by prefix.

        Useful as a navigation helper — what categories exist, what pages
        live under ``arista/``, etc.

        Args:
            prefix: Optional prefix to filter by (e.g. ``"arista/"``).

        Returns:
            Sorted list of unique location strings.
        """
        # Strip the heading anchor (#peer-link) so we get distinct *pages*,
        # not every heading inside every page.
        seen: set[str] = set()
        for it in self._items:
            loc = it.get("location", "")
            page = loc.split("#", 1)[0]
            if not page:
                continue
            if prefix and not page.startswith(prefix):
                continue
            seen.add(page)
        return sorted(seen)
