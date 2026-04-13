# krabb

Web access analytics and control for Claude Code.

Requires Python 3.10+.

## Install

```bash
pip install krabb
krabb init
```

That's it. Every Claude Code tool call (WebFetch, WebSearch, Bash, Read, Write, Edit) is now logged locally.

## What it does

- **Logs every tool call** to a local SQLite database at `~/.krabb/krabb.db`
- **Domain blocklist** — block specific domains from being accessed
- **Command blocking** — block specific Bash commands or entire tools
- **File protection** — prevent writes to sensitive files
- **Local dashboard** at `localhost:4242` to browse events and manage rules

## Dashboard

```bash
krabb dashboard
```

## CLI reference

```
krabb init                              Install hook + start daemon
krabb status                            Show daemon status and stats
krabb logs [--limit N] [--tool T]       Show recent events
krabb dashboard                         Open dashboard in browser
krabb blocklist list|add|remove         Manage domain blocklist
krabb commands list|add|remove          Manage blocked commands
krabb hook                              Run hook server (foreground)
krabb uninstall                         Remove hook from Claude settings
```

## Domain blocklist

```bash
krabb blocklist add example.com
krabb blocklist add "*.example.com"
krabb blocklist add "/tracking\.js$/"
```

| Pattern             | Matches                                    |
|---------------------|--------------------------------------------|
| `example.com`       | example.com and all subdomains             |
| `*.example.com`     | Subdomains only (not example.com itself)   |
| `/regex/`           | Python regex matched against the full URL  |

When the blocklist is empty (default), all domains are allowed. Add a domain to block it — everything else remains allowed.

## Blocked commands

```bash
krabb commands add "rm -rf *"
krabb commands add "git push --force*"
krabb commands add "tool:WebSearch"
krabb commands add "/sudo/"
```

| Pattern              | Type   | Matches                                     |
|----------------------|--------|---------------------------------------------|
| `tool:WebFetch`      | tool   | Blocks the entire tool                      |
| `/regex/`            | regex  | Python regex matched against the command    |
| `rm -rf *`           | glob   | Glob pattern (supports `*` and `?`)         |
| `git push --force`   | prefix | Any command starting with this string       |

Command blocking is checked before all other rules. A `tool:` pattern blocks the tool regardless of input.

## File protection

Prevent Claude Code from writing to specific files. Managed via the dashboard or the API.

| Pattern              | Matches                                     |
|----------------------|---------------------------------------------|
| `/path/to/file.txt`  | Exact path                                  |
| `*.env`              | Glob against filename                       |
| `src/config/`        | Anything under that directory               |
| `package-lock.json`  | Matches that filename anywhere              |

## Config

Configuration is stored in `~/.krabb/krabb.db` in the `config` table. Default values:

| Key                | Default  | Description                          |
|--------------------|----------|--------------------------------------|
| `default_decision` | `allow`  | Default action for unmatched tools   |
| `hook_port`        | `4243`   | Port for the hook HTTP server        |
| `dashboard_port`   | `4242`   | Port for the dashboard               |
| `log_bash`         | `true`   | Log Bash tool calls                  |
| `log_reads`        | `true`   | Log Read/Write tool calls            |

## How it works

krabb registers a [PreToolUse hook](https://docs.anthropic.com/en/docs/claude-code/hooks) in `~/.claude/settings.json`. The hook pipes Claude Code's tool-use payload to a local HTTP server via `curl`. The server:

1. Checks the command against blocked commands
2. For web tools: checks the URL against the domain blocklist
3. For writes: checks the file path against protected files
4. Logs the event to SQLite
5. Returns `allow` or `deny` to Claude Code

Everything runs locally. No data leaves your machine.

## Contributing

1. Clone the repo
2. `pip install -e ".[dev]"`
3. `pytest tests/ -v`
4. `ruff check krabb/`

PRs welcome. Please include tests for new functionality.

## License

MIT — see [LICENSE](LICENSE).
