# krabb

Web access analytics and control for Claude Code.

Requires Python 3.10+.

## Install

```bash
pip install krabb
krabb init
```

That's it. Every Claude Code tool call (WebFetch, WebSearch, Bash, Read, Write) is now logged locally.

## What it does

- **Logs every tool call** to a local SQLite database at `~/.krabb/krabb.db`
- **Enforces a domain blocklist** — block specific domains from being accessed by Claude Code
- **Exposes a local dashboard** at `localhost:4242` to browse events and manage the blocklist

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
krabb blocklist list                    List blocklist patterns
krabb blocklist add <pattern>           Add a pattern
krabb blocklist remove <pattern>        Remove a pattern
krabb hook                              Run hook server (foreground)
krabb uninstall                         Remove hook from Claude settings
```

## Config

Configuration is stored in `~/.krabb/krabb.db` in the `config` table. Default values:

| Key                | Default  | Description                          |
|--------------------|----------|--------------------------------------|
| `default_decision` | `allow`  | Default action for unmatched tools   |
| `hook_port`        | `4243`   | Port for the hook HTTP server        |
| `dashboard_port`   | `4242`   | Port for the dashboard               |
| `log_bash`         | `true`   | Log Bash tool calls                  |
| `log_reads`        | `true`   | Log Read/Write tool calls            |

## Blocklist patterns

| Pattern             | Matches                                    |
|---------------------|--------------------------------------------|
| `example.com`       | example.com and all subdomains             |
| `*.example.com`     | Subdomains only (not example.com itself)   |
| `/regex/`           | Python regex matched against the full URL  |

When the blocklist is empty (default), all domains are allowed. Add a domain to block it — everything else remains allowed. You can also paste full URLs; krabb extracts the domain automatically.

## How it works

krabb registers a [PreToolUse hook](https://docs.anthropic.com/en/docs/claude-code/hooks) in `~/.claude/settings.json`. The hook is a shell command that pipes Claude Code's tool-use payload to a local HTTP server via `curl`. The server:

1. Logs the event to SQLite
2. For web tools (WebFetch/WebSearch): checks the URL against the blocklist
3. Returns `allow` or `deny` to Claude Code

Everything runs locally. No data leaves your machine.

## Contributing

1. Clone the repo
2. `pip install -e ".[dev]"`
3. `pytest tests/ -v`
4. `ruff check krabb/`

PRs welcome. Please include tests for new functionality.

## License

MIT — see [LICENSE](LICENSE).
