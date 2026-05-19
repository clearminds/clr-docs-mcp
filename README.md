# clr-docs-mcp

Read-only MCP for the clearminds Zensical docs site (`clearminds/docs`).

Surfaces three tools to any MCP client:

| Tool | Purpose |
|---|---|
| `docs_search(query, limit=10)` | Full-text search the Zensical index. Title weighs 3× body. Returns title + URL + snippet. |
| `docs_read(path)` | Return the raw markdown for a page. Accepts `arista/docs/MLAG.html` or `arista/docs/MLAG.md`. |
| `docs_list(prefix="")` | List unique page paths, optionally filtered by prefix. E.g. `docs_list("sessions/clearthink/")`. |

Data source is a **local clone** of `clearminds/docs` — the MCP reads
`<repo>/public/search.json` (built by CI on every push to `main`) and the
source markdown under `<repo>/docs/`. A separate cron should `git pull`
the clone every 10 min or so to keep the index fresh.

## Config (env vars)

| Var | Default | Notes |
|---|---|---|
| `DOCS_REPO_PATH` | `/opt/docs-mcp/repo` | Local clone of the docs repo |
| `DOCS_SITE_URL` | `https://docs.clearminds.se` | Public URL, used to build shareable links |
| `DOCS_MAX_SNIPPET` | `280` | Char cap on returned snippets |

## Local dev

```bash
uv sync
DOCS_REPO_PATH=~/Documents/source/clearminds/docs \
  uv run clr-docs-mcp --transport stdio
```

Then point any MCP client at the stdio transport.

## Why this exists

Operational docs (Arista bootstrap, MikroTik recipes, session notes,
troubleshooting playbooks) all live in `clearminds/docs`. Without this
MCP an agent has to grep the local clone or fetch URLs by hand. With it,
"what did we do about the Hanwha sysName issue?" becomes a single
`docs_search` call.
