# commit-cleaner-hook

Deterministic Claude Code hooks. The first one removes AI attribution
trailers from commit messages and pull request bodies.

## What it does

Two components work together:

- **A commit-msg git hook** cleans the message of every commit made in a
  repo where it is installed, regardless of which tool made the commit. It
  strips lines like `Co-Authored-By: Claude <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_...`, then commits the
  result. It fails open: if the cleaner errors, hangs, or is missing
  `python3`, the commit still goes through unmodified.
- **A PreToolUse guard** inside Claude Code denies (or, where a legitimate
  use exists, asks about) actions that would bypass or disable the git hook
  — `git commit --no-verify`, deleting or chmodding the hook file,
  redirecting `core.hooksPath` or `GIT_DIR` — and denies `gh` CLI and
  GitHub MCP calls that would post a dirty body straight to GitHub, where
  no git hook runs. That covers pull request bodies, review and issue
  comments, issue and discussion bodies, and file writes through the
  Contents API, in both their `gh` and MCP forms — GitHub keeps a publicly
  readable edit history, so anything that lands is permanent and the guard
  prevents rather than remediates.

Together they cover the common case: a Claude Code session driving `git`
and `gh` in this repo. Neither is a substitute for the other; see
**Known limitations** below for what they miss.

## Install

```
/plugin marketplace add ya8282/commit-cleaner-hook
/plugin install commit-cleaner@commit-cleaner-hook
```

The plugin install alone only wires the PreToolUse guard and the
SessionStart reminder. To actually clean commits in a given repo, install
the commit-msg hook into that repo:

```
/commit-cleaner-install
```

or directly:

```
python3 ${CLAUDE_PLUGIN_ROOT}/install.py
```

This writes a self-contained payload (no dependency on the plugin being
present later) into the repo's hooks directory — `core.hooksPath` if set,
otherwise `.git/hooks` — and chains any pre-existing `commit-msg` hook so
it still runs and can still block a bad commit.

If the hooks directory is tracked by git, install refuses to write into it
(a shared hooks directory is team infrastructure the tool will not edit
silently) and instead prints the two lines to add to your committed hook by
hand.

Other invocations:

```
python3 ${CLAUDE_PLUGIN_ROOT}/install.py --uninstall   # remove, restore any chained hook
python3 ${CLAUDE_PLUGIN_ROOT}/install.py --list         # every repo it's installed into
python3 ${CLAUDE_PLUGIN_ROOT}/install.py --upgrade      # regenerate the payload
```

Install also walks `git submodule foreach` and installs into each
submodule, since a submodule is its own repo with its own hooks directory.

## What gets stripped

By default:

- `Co-Authored-By:` lines whose email is on `@anthropic.com` — a human
  co-author literally named Claude, with a different email, survives.
- `Claude-Session:` and other `*-Session:` lines pointing at
  `https://claude.ai/code/session_...`.
- `Generated with [Claude Code](...)` footer lines, with or without the
  robot emoji.

A message that is *only* attribution is left untouched rather than emptied
— git refuses an empty commit message, and this tool never blocks a
commit. A clean message is returned byte-identical.

## Configuration

Set via `git config`, never via environment variables — a git hook does not
inherit the Claude Code session environment, so an env var would make the
same repo strip differently depending on who ran the commit.

- `commitcleaner.patterns` — path to a file of additional patterns.
- `commitcleaner.defaults` — set to `false` to disable the built-in pattern
  set above and use only your own file.

Pattern file format: one Python regular expression per line, matched with
`re.search` (case-insensitive) against a whole line of the message. Lines
starting with `#` and blank lines are ignored. A line that fails to compile
as a regex is skipped with a warning on stderr rather than failing the
commit.

```
git config commitcleaner.patterns .commitcleaner-patterns
```

```
# .commitcleaner-patterns
^\s*Co-Authored-By:.*@cursor\.com\s*>?\s*$
^\s*Co-Authored-By:.*\bcodex\b.*$
```

## Known limitations

This tool covers the common path — a Claude Code session running `git`,
`gh`, and the GitHub MCP tools in a normal repo. It does not cover
everything, and overstating coverage would be worse than admitting the
gap:

- **`cherry-pick`, `rebase` replay, and `git am` do not run `commit-msg`.**
  A commit authored elsewhere with a trailer already baked in keeps that
  trailer when it is replayed onto this repo. `git rebase main` is the
  common case: rebasing branch commits onto `main` does not re-run
  `commit-msg` on each replayed commit.
- **`gh api` posting directly to the Contents API**, or any MCP server
  whose git-write tools are not named the way GitHub's are, bypasses the
  guard entirely — the guard matches on known tool names and known `gh`
  subcommands, not on arbitrary API calls.
- **`gh pr create --editor` or `--web`** compose the body somewhere the
  hook cannot see — an external editor or a browser tab — so nothing is
  checked.
- **`gh pr create --body-file -`** (reading the body from stdin) returns
  `ask` rather than a decision, because the hook cannot read the process's
  stdin to inspect it.
- **Submodules need their own install.** `install.py` walks `git submodule
  foreach` at install time, but a submodule added afterward needs a
  re-run.
- **`git notes add -m`, `git tag -a -m`, and `git stash push -m`** have no
  corresponding git hook at all, so attribution in any of these is never
  stripped.
- **A git alias that sets `core.hooksPath`** (for example one wired up by
  `husky init` after this tool installed) can silently redirect hooks
  elsewhere and defeat the guard. The SessionStart check surfaces this at
  the start of the next session, not immediately.
- **Command substitution and deep nesting are not covered.** The guard
  unwraps one layer of `bash -c "..."` / `eval '...'`, but not arbitrary
  command substitution such as `$(echo git commit --no-verify)`, nor three
  or more levels of nested shell wrappers using alternating quote types.
- **No global `core.hooksPath` install is shipped**, on purpose. A global
  hooks path is dead in any repo that already sets its own `core.hooksPath`
  (husky, lefthook, pre-commit all do), and in every repo that does *not*
  set one, it would silently replace `.git/hooks` machine-wide — a much
  bigger blast radius than an explicit per-repo install.

## Contributing

See `docs/writing-a-hook.md` for the conventions this repo's hooks follow
and the facts about Claude Code's hook protocol that are easy to get wrong.
