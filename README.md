# commit-cleaner-hook

Keeps AI attribution out of your git history and your pull requests.

Strips trailers like these from commit messages and PR bodies, without you
having to remember:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_03EgpJ4AzYq9eFNpAOH80
```

Claude Code's own `attribution` setting suppresses these, but the setting
gets reset, other agents add their own, and a pasted commit carries
whatever it carries. This is the layer that doesn't depend on anyone
remembering.

## How it works

**A `commit-msg` git hook** cleans every commit made in a repo where it's
installed, whatever tool made it — it runs after git assembles the message,
so it catches `-m`, heredocs, `--amend`, `$EDITOR`, and the rest. It fails
open: if it errors, hangs, or `python3` is missing, your commit still goes
through.

**A `PreToolUse` guard** inside Claude Code blocks the ways around it —
`git commit --no-verify`, deleting or chmodding the hook, redirecting
`core.hooksPath` — and denies `gh`/GitHub MCP calls carrying a dirty PR
body. It prevents rather than cleans up, because GitHub keeps a publicly
readable edit history: editing a body afterward leaves a permanent record
of exactly what was removed.

## Install

```
/plugin marketplace add ya8282/commit-cleaner-hook
/plugin install commit-cleaner@commit-cleaner-hook
```

That wires the guard. To clean commits in a repo, install the git hook
there too:

```
/commit-cleaner-install
```

Use the slash command — `${CLAUDE_PLUGIN_ROOT}` is set inside Claude Code
but not in your shell, so pasting that path into a terminal fails. From a
terminal, substitute the real plugin directory (under `~/.claude/plugins/`;
the session-start reminder prints the resolved path).

The install writes a self-contained payload into the repo's hooks directory
(`core.hooksPath` if set, else `.git/hooks`) and chains any existing
`commit-msg` hook so it still runs. If that directory is tracked by git, it
refuses to write there — a shared hooks directory is team infrastructure —
and prints the two lines to add to your committed hook instead. Submodules
get their own install.

```
python3 <plugin-dir>/install.py --uninstall   # restore any chained hook
python3 <plugin-dir>/install.py --list        # repos it's installed into
python3 <plugin-dir>/install.py --upgrade     # regenerate the payload
```

## What gets stripped

- `Co-Authored-By:` lines whose email is `@anthropic.com` — a human
  co-author named Claude, with a different email, survives.
- `Claude-Session:` and `*-Session:` lines pointing at `claude.ai/code/session_...`.
- `Generated with [Claude Code](...)` footers, with or without the emoji.

A message that is *only* attribution is left alone rather than emptied, so
git never rejects your commit. A clean message comes back byte-identical.

## Configuration

Via `git config`, not environment variables — a git hook doesn't inherit
your Claude Code session's environment, so an env var would make the same
repo behave differently depending on who ran the commit.

```
git config commitcleaner.patterns .commitcleaner-patterns
git config commitcleaner.defaults false   # use only your file
```

One Python regex per line, matched case-insensitively against whole lines.
`#` comments and blank lines ignored. A regex that won't compile is skipped
with a warning rather than failing your commit.

```
# .commitcleaner-patterns
^\s*Co-Authored-By:.*@cursor\.com\s*>?\s*$
^\s*Co-Authored-By:.*\bcodex\b.*$
```

## Known limitations

Overstating coverage would be worse than admitting the gaps:

- **Replayed commits keep their trailers.** `cherry-pick`, `rebase`, and
  `git am` don't run `commit-msg`, so `git rebase main` re-lands existing
  messages untouched.
- **`gh pr create --editor` / `--web`** compose the body where no hook can
  see it. `--body-file -` (stdin) prompts instead of deciding.
- **`gh api` against the Contents API**, or an MCP server whose git-write
  tools aren't named like GitHub's, bypasses the guard — it matches known
  tool names, not arbitrary API calls.
- **`git notes`, `git tag -a`, `git stash push`** have no git hook at all.
- **Deep shell nesting.** The guard unwraps one layer of `bash -c "..."` /
  `eval`, but not `$(echo git commit --no-verify)` or three-plus levels of
  alternating quotes.
- **A `core.hooksPath` change after install** (husky, lefthook) redirects
  hooks away; the session-start check surfaces it next session.
- **No global install**, deliberately: a global hooks path is dead in any
  repo that sets its own, and silently replaces `.git/hooks` in every repo
  that doesn't.

## Contributing

`docs/writing-a-hook.md` has the conventions and the Claude Code hook-protocol
details that are easy to get wrong. Shipped code is stdlib-only on Python 3.9+:

```
pip install pytest ruff
pytest
ruff check .
```

CI runs both on Python 3.9–3.13 on Linux, plus macOS at each end. Test
fixtures build attribution trailers by concatenating fragments at runtime —
a guard matching raw command text otherwise rejects this repo's own test
data.

MIT.
