"""Configuration for clr-docs-mcp."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for clr-docs-mcp.

    Attributes:
        docs_repo_path: Local clone of the clearminds/docs repo. Must contain
            both ``public/search.json`` (the Zensical search index built by CI)
            and the source ``docs/`` markdown tree.
        docs_site_url: Public URL of the deployed docs site. Used to construct
            shareable links in search results. No trailing slash.
        docs_max_snippet: Max chars returned per search snippet.
    """

    docs_repo_path: Path = Path("/opt/docs-mcp/repo")
    docs_site_url: str = "https://docs.clearminds.se"
    docs_max_snippet: int = 280

    model_config = {"env_prefix": ""}
