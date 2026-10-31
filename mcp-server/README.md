# Sky Score for Claude (local MCP server)

A small [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude Desktop or Claude Code
call the live Sky Score API as tools. It runs on your own machine over stdio, only while Claude has it open.
Nothing is hosted and nothing is public.

Every figure Claude gives comes from the API's own response, and each response carries its `sources`, which
Claude is told to cite (`INSTRUCTIONS` in `sky_score_mcp.py` holds the product's wording rules).

## Tools

| Tool | API | Key |
|---|---|---|
| `score_area` | `/v1/score` for a postcode, New York ZIP or borough, under a persona | yes |
| `compare_areas` | `/v1/score` for two to five places, one call each | yes |
| `list_regions` | `/v1/regions`: the cities and boroughs covered | no |
| `score_changes` | `/v1/changes`: London's quarter-on-quarter movement | no |
| `environment_at` | `/v1/environment`: DEFRA's modelled air quality and road and aircraft noise at a coordinate (no flood value) | no |

All five are read-only. A place Sky Score does not cover is said to be NOT COVERED YET, never scored.

## Setup

1. Python 3.11 and the MCP SDK: `pip install mcp==1.23.3`.
2. The server's **own** free-tier key in the repo's `.env` as `SKY_SCORE_MCP_KEY` (see `.env.example`). Never
   the CI key or the free-tier test key: their allowances belong to the preflight gates.
3. Register it with Claude, with `<repo>` as the path of your clone.

**Claude Code** (every project):

```
claude mcp add sky-score --scope user -- python <repo>/mcp-server/sky_score_mcp.py
```

**Claude Desktop**: add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows), using Python's full path,
since the app may not see your shell's PATH, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "sky-score": {
      "command": "<full path to python.exe>",
      "args": ["<repo>\\mcp-server\\sky_score_mcp.py"]
    }
  }
}
```

Then ask, for example: "What is Sky Score's view of TW9 3PZ for a family, and why?"

## Tests

`python -m pytest tests/test_mcp_server.py` runs offline (the network is stubbed): read-only tools, the key only
in its header and never in an error, bad input refused before any request, uncovered places, compare.

## The public connector (not this)

A remote server anyone can add to Claude is the long-term aim. It is held by the rename, verified signups
(per-user keys need SES production access, which waits on DMARC), the ICO fee and a privacy section for
assistant traffic, terms covering answers given through an assistant (legal batch 2), and NATS's written OK on
the UK AIP routes for any paid use. See ROADMAP.md.
