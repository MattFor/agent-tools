# Agent Tools

[![CI](https://github.com/MattFor/agent-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/MattFor/agent-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Shortcut CLIs for coding agents, built from what agents kept re-writing in 110,000 real tool calls.

## Features

Plain commands with plain-text output and exit codes, so Claude Code, Codex, Copilot CLI, Cursor or a
person can use them alike.

| Tool         | Replaces                                                                                                                                               |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `subst`      | Python `read / assert count == 1 / replace / write` heredocs: SEARCH/REPLACE blocks on stdin, several files per call, all-or-nothing, usable over ssh. |
| `transcript` | Ad-hoc parsing of Claude Code, Codex and Copilot CLI session logs: find, list, show, recover tool calls.                                               |
| `on`         | Hand-typed ssh lines to your other machines: run, copy with hash check, run everywhere, borrow the desktop session.                                    |
| `waitfor`    | `until …; do sleep` loops: HTTP, port, process, log line, file, GitHub Actions run, any command.                                                       |
| `tui`        | Driving a TUI in a private tmux server: start, keys, type, wait for text, screen, stop.                                                                |
| `xlab`       | Xvfb + window manager + xdotool + ImageMagick sequences for GUI tests on a private display, sound to a null sink.                                      |
| `webshot`    | Hand-written CDP drivers: screenshot, click, type, evaluate JS; always reports status, console errors and page exceptions.                             |
| `jshape`     | Recursive probes to learn a JSON file's structure.                                                                                                     |
| `nbdump`     | Scripts that print a Jupyter notebook's cells, outputs and tracebacks.                                                                                 |

[`agent-instructions.md`](agent-instructions.md) tells an agent when to use each one.

## Requirements

Python 3.11+ (stdlib only). Per tool: `on` needs ssh; `tui` needs tmux; `xlab` needs Xvfb, xdotool,
xwininfo, ImageMagick and optionally xfwm4 and pactl; `webshot` needs Node 22+ and a Chromium (Playwright's
`chrome-headless-shell`, `chromium` or `google-chrome`); `waitfor ci` needs `gh`.

## Install

```sh
git clone https://github.com/MattFor/agent-tools && agent-tools/install
```

`install` links every tool into `~/.local/bin` (or the folder you pass). Then add `agent-instructions.md` to
your agent's instructions: `@path/to/agent-instructions.md` in `CLAUDE.md`, or paste it into `AGENTS.md`
(Codex, Cursor) or `~/.copilot/copilot-instructions.md`.

## Usage

Every tool prints its usage with `-h`.

### Hosts for `on`

`on` reads `$ON_HOSTS` or `~/.config/on/hosts`: aliases, then the command that reaches the host, which gets
the remote command as its last argument and runs through `sh`.

```text
pc,desktop  ssh -o BatchMode=yes -o ConnectTimeout=15 me@desktop
phone       ssh -o BatchMode=yes -p 8022 "$(tailscale ip -4 phone)"
```

<!-- TODO(user): Disclosure section, if you want one. -->

## License

MIT, see [LICENSE](LICENSE). By [MattFor](https://github.com/MattFor).
