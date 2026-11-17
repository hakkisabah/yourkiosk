# Gemini CLI extension for a local MCP server

Verified against Gemini CLI 0.66.0 on Linux. The extension is a directory with a
manifest; the CLI registers the MCP server and, optionally, slash commands and a
context file.

## Layout

```
my-extension/
├── gemini-extension.json
├── GEMINI.md                 # context loaded every session (when to call the tool)
├── commands/<group>/<cmd>.toml
└── <name>-mcp.sh             # wrapper that resolves the interpreter
```

## Manifest

```json
{
  "name": "trick",
  "version": "0.4.0",
  "description": "...",
  "contextFileName": "GEMINI.md",
  "settings": [
    { "name": "Trick Python",
      "description": "Absolute path to the interpreter that can import the package",
      "envVar": "TRICK_PYTHON" }
  ],
  "mcpServers": {
    "trick": { "command": "/bin/sh", "args": ["${extensionPath}/trick-mcp.sh"] }
  }
}
```

- `${extensionPath}` is substituted with the absolute extension directory.
- **`"command"` must not be a bare binary name.** The CLI spawns MCP servers with
a sanitised environment, so `"command": "trick"` fails with
`[MCP error] ... spawn trick ENOENT` even when the binary is on the user's PATH.
Absolute path + wrapper is the portable form.
- `settings[].envVar` is the only way to get an environment variable into the
server process: sensitive host env vars are filtered out by default, so a
manifest that expects an inherited variable silently gets an empty one.

## Wrapper script

```sh
#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
if [ -n "${MY_PYTHON:-}" ] && [ -x "${MY_PYTHON}" ]; then python=${MY_PYTHON}
elif [ -x "$repo/.venv/bin/python" ]; then python="$repo/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then python=$(command -v python3)
else python=/usr/bin/python3
fi
PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec "$python" -m mypkg mcp "$@"
```

Resolution order: declared override -> repo venv -> `python3` -> `/usr/bin/python3`.
With `PYTHONPATH` pointing at the source tree there is no install step, so a
linked clone works immediately. Commit the executable bit; a non-executable
wrapper fails with permission denied, not with a helpful message.

## Slash commands

`commands/<group>/<name>.toml` becomes `/<group>:<name>`:

```toml
description = "Rank sources for a question"
prompt = """
Use the `my_search` tool with exactly this query: {{args}}
Answer with the returned rows only. Do not invent sources.
"""
```

Keep the prompt a constraint list, not a personality: "do not invent sources or
versions" is the line that stops the model from padding an empty result.

## Verification recipe

```sh
export PATH=<npm-prefix>/node_modules/.bin:$PATH
export GEMINI_CLI_HOME=$HOME/.gemini-<name>-test   # never touch the real config
mkdir -p "$GEMINI_CLI_HOME"
gemini --version
gemini extensions link . --consent                 # or: extensions install <git url>
gemini extensions list                             # shows MCP servers + context files
gemini -p "search for X" --debug 2>&1 | grep -iE 'mcp|server .*has tools|spawn'
```

Success looks like `Loading extension: <name>`, then
`server '<name>' has tools` in the debug log. `spawn <cmd> ENOENT` means the
command is not resolvable in the sanitised environment.

**The limit of this check:** it proves registration and the MCP handshake only.
Having the model actually call the tool needs a real API key; with a dummy key
the CLI exits non-zero after the handshake. Report it exactly that way - transport
proven, model invocation unproven - rather than claiming the integration works.

## Install-manifest gate checks

Cheap asserts that catch the two failures above before a user does:

- manifest parses; `mcpServers.<name>.command` starts with `/` and is not a bare
  binary name;
- the wrapper file exists **and** has an executable bit;
- every `commands/**/*.toml` starts with `description =` and contains `prompt =`;
- no literal credential appears in the extension directory.
