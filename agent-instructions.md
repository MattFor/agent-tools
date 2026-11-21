# Shortcut tools (agent-tools)

Use these instead of writing the same heredoc, loop or ssh line again. Each has `-h`.

- **Edit files from the shell** (several hunks, several files, or over ssh): `subst [FILE]` reads
  `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` blocks on stdin; a path line above a block picks its
  file. SEARCH is exact text (may be part of a line) and must match once (`-a`: every match); one failing
  block writes nothing; `-n` shows the diff. Not a Python `s.replace()` heredoc.
- **Past sessions** (Claude Code, Codex, Copilot CLI): `transcript find TERM… [--role user|assistant|tool|result] [-a codex] [-p FOLDER] [--since DATE]`,
  `transcript sessions`, `transcript show ID`, `transcript tools ID --grep RE --full` (recover a command as it was run).
- **Other machines**: `on HOST 'cmd'` (stdin and exit code pass through), `on HOST put SRC… DEST` / `get`
  (prints sha256 vs local), `on all 'cmd'`, `-d` for the desktop's DISPLAY/DBUS, `on -l` lists hosts.
- **Waiting**: `waitfor [-t SECS] http URL | port N | proc PAT | gone PID|PAT | log FILE RE | file PATH | ci | -- CMD`.
  Exit 124 on timeout. Never a hand-written `until …; sleep` loop or `time.sleep`.
- **TUIs** in a private tmux: `tui start NAME -- CMD`, `tui keys NAME Down Enter`, `tui type NAME text`,
  `tui wait NAME RE`, `tui screen NAME`, `tui stop NAME`.
- **GUI apps** on a private X display: `eval "$(xlab up 1280x800)"` (also routes sound to a null sink), start
  the app, `xlab win PATTERN`, `xlab input -w PATTERN click X Y type text key Return`,
  `xlab shot -w PATTERN --crop WxH+X+Y out.png`, `xlab down`.
- **Web pages**: `webshot URL out.png [--size WxH] [--full] [--mobile] [--dark] [--click CSS] [--wait-for CSS]`,
  `webshot URL --eval 'JS'`; always reports status, console errors and page exceptions.
- **Lint and test a repo**: `check [--fix] [--only lint|test]` finds the toolchains (Rust, Python, JS, shell,
  C/C++, Lua, workflows) and runs their format, lint and test steps: one `ok`/`FAIL`/`skip` line each, failure
  tails shown. Not a hand-chained `fmt && clippy && test | tail`.
- **Disk space**: `reclaim [PATH]` ranks regenerable space (build dirs, venvs, caches, trash, old downloads)
  with the command that frees each; it never deletes.
- **Bot pull requests**: `gh-dependabot [--owner OWNER | REPO…] [--merge]` lists Dependabot/Renovate PRs with
  check state; `--merge` merges only the green, mergeable ones (only when the user asked for merging).
- **GitHub vs Codeberg mirrors**: `forge-diff [--owner OWNER | REPO…] --tea-login NAME` reports missing repos,
  stale branches, tags, visibility, description and topic differences.
- **JSON**: `jshape FILE` (or stdin) for the structure, then `jq` (`gh … --jq`) for the values; `jshape --paths`
  for greppable `.a.b[3] = v` lines. Never `python3 -c 'import json…'` to pick a field.
- **Notebooks**: `nbdump NB.ipynb [CELLS] [--errors]`.
- **Images**: `magick in.png -crop WxH+X+Y +repage -scale 200% out.png`; side by side
  `montage a.png b.png -tile 2x -geometry +4+4 out.png`; difference `magick compare -metric AE a.png b.png null:`.
- **Minified or huge one-line files**: `grep -oP '.{0,200}\Qneedle\E.{0,400}' FILE`.
- **Killing by pattern**: `pkill -f '[s]erver.py'` (bracket one letter); a bare pattern matches the shell
  running the command and kills it too.
