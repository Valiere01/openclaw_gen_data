---
name: fetch-openclaw-tools
description: Fetch the complete list of OpenClaw agent tools with full JSON Schema (name, description, parameters). Use this at the start of a data generation session to get accurate tool definitions for mid_format training data. Run scripts/dump_tools.mjs to extract all tool schemas directly from the OpenClaw bundle without network calls or API requests.
---

# fetch-openclaw-tools

Extract all OpenClaw tool definitions (name + description + parameters) from the installed bundle.

## When to use

Run this once at the start of a generation session to populate `output/openclaw_all_tools.json`.

## Usage

```bash
node /Users/luosiyuan/openclaw_proj/openclaw_gen_data/claude_files/skill_fetch_tools/scripts/dump_tools.mjs \
  2>/dev/null \
  > /Users/luosiyuan/openclaw_proj/openclaw_gen_data/output/openclaw_all_tools.json
```

Output: JSON array of OpenAI-format tool definitions, one per tool.

## What it extracts

17 tools from 3 sources:

| Source | Tools |
|--------|-------|
| `@mariozechner/pi-coding-agent` | read, write, edit |
| `pi-embedded-*.js` | exec, process, sessions_*, subagents, session_status, cron |
| `reply-*.js` | memory_search, memory_get, web_fetch, web_search, image |

## Output format

```json
[
  {
    "type": "function",
    "function": {
      "name": "exec",
      "description": "Execute shell commands...",
      "parameters": {
        "type": "object",
        "properties": { "command": { "type": "string", ... }, ... },
        "required": ["command"]
      }
    }
  },
  ...
]
```

## Notes

- Reads TypeBox schema definitions directly from bundled JS, then compiles to JSON Schema at runtime
- No network calls, no agent interaction needed
- Re-run after OpenClaw upgrades to refresh schemas
