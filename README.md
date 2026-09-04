# commit-cleaner-hook

Prevent Claude from slipping into your git commit messages and pull requests.

You might have seen then the unwanted messages before:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_ID
```

Currently, you can use the Claude Code attribution setting to turn
them off. However, when the behavior breaks or if you unknowingly paste
them into a commit message, you're unprotected from its intrusion.

## How it works

This is a Claude Code plugin, composed of two components:

1. **A `commit-msg` git hook**: cleans every commit in a repo where it's installed. It runs after git adds the commit message,
   whether added by the `-m` or `--amend` options, heredoc, `$EDITOR`, or `printf`.
a good trade.
2.  **A `PreToolUse` guard** inside Claude Code covers the exits — `git commit --no-verify`, deleting the hook, chmodding it, quietly repointing `core.hooksPath` — and refuses `gh` and GitHub MCP calls carrying a dirty
PR body. It stops these before they happen rather than tidying up after, because GitHub keeps a public edit history: cleaning a body later just
publishes a diff of exactly what you removed and when. The receipts outlive the cover-up.

## Install

```
/plugin marketplace add ya8282/commit-cleaner-hook
/plugin install commit-cleaner@commit-cleaner-hook
```

That's the guard — the bouncer at the door. The git hook is the one doing
the actual work, and it installs per repo:

```
/commit-cleaner-install
```

Use the slash command. `${CLAUDE_PLUGIN_ROOT}` only means something inside
Claude Code; your shell has no idea and will cheerfully try to run
`/install.py`. From a terminal, substitute the real plugin directory (under
`~/.claude/plugins/` — the session-start reminder prints the resolved path
when the hook is missing).

The install drops a self-contained payload into the repo's hooks directory
(`core.hooksPath` if set, otherwise `.git/hooks`) and chains any existing
`commit-msg` hook so your commitlint keeps its veto. If that directory is
tracked by git, it refuses to write there and prints the two lines to add
yourself — a shared hooks directory belongs to your team, and this tool is
not going to redecorate it while nobody's looking. Submodules get their own
install.

```
python3 <plugin-dir>/install.py --uninstall   # restore any chained hook
python3 <plugin-dir>/install.py --list        # repos it's installed into
python3 <plugin-dir>/install.py --upgrade     # regenerate the payload
```

## What gets stripped

- `Co-Authored-By:` lines whose email is `@anthropic.com`. If you work with
  a human named Claude, they keep their credit — we match on the address,
  not the name.
- `Claude-Session:` and `*-Session:` lines pointing at `claude.ai/code/session_...`.
- `Generated with [Claude Code](...)` footers, robot emoji optional.

A message that is *nothing but* attribution survives untouched rather than
being emptied out. git rejects an empty commit message, and we're not going
to pick that fight on your behalf. A clean message comes back
byte-identical — this thing has one job and it doesn't get creative.

## Configuration

Through `git config`, not environment variables. A git hook doesn't inherit
your Claude Code session's environment, so an env var would mean the same
repo behaves differently depending on who typed the command — which is
precisely the flavour of chaos we're here to eliminate.

```
git config commitcleaner.patterns .commitcleaner-patterns
git config commitcleaner.defaults false   # use only your file
```

One Python regex per line, matched case-insensitively against whole lines.
`#` comments and blank lines ignored. A regex that won't compile gets
skipped with a warning instead of failing your commit, because your typo
should not become your problem at 2am.

Other agents ship commented out, opt-in — removing someone else's signature
without being asked is a different kind of rude:

```
# .commitcleaner-patterns
^\s*Co-Authored-By:.*@cursor\.com\s*>?\s*$
^\s*Co-Authored-By:.*\bcodex\b.*$
```

## Known limitations

Everything below is a real gap, found by testing rather than guessed at.
Overstating coverage would be worse than admitting it:

- **Replayed commits keep their trailers.** `cherry-pick`, `rebase`, and
  `git am` don't run `commit-msg` at all, so `git rebase main` re-lands old
  messages exactly as they were. This is the one that will actually bite
  you.
- **`gh pr create --editor` / `--web`** compose the body somewhere no hook
  can see. `--body-file -` reads from stdin, which the hook can't inspect,
  so it asks rather than guessing.
- **`gh api` straight at the Contents API**, or an MCP server whose
  git-write tools aren't named like GitHub's, goes around the guard — it
  matches known tool names, not arbitrary HTTP.
- **`git notes`, `git tag -a`, `git stash push`** have no hook to attach
  to. git simply doesn't offer one.
- **Deep shell nesting.** The guard unwraps one layer of `bash -c "..."` /
  `eval`, but not `$(echo git commit --no-verify)` or three-plus levels of
  alternating quotes. At some point you're not slipping up, you're
  committing a crime.
- **A `core.hooksPath` change after install** (husky, lefthook) redirects
  hooks elsewhere. The session-start check catches it next session, not
  the instant it happens.
- **No global install**, on purpose. A global hooks path is dead in any
  repo that sets its own, and silently replaces `.git/hooks` in every repo
  that doesn't — a blast radius nobody asked for.

## Contributing

`docs/writing-a-hook.md` has the conventions, plus the Claude Code
hook-protocol details that are easy to get wrong (several of which cost
this repo a fix round to learn). Shipped code is stdlib-only on Python 3.9+,
so the dev dependencies are a test runner and a linter:

```
pip install pytest ruff
pytest
ruff check .
```

CI runs both on Python 3.9–3.13 on Linux, plus macOS at each end of that
range.

One quirk worth knowing before it confuses you: the test fixtures build
attribution trailers by concatenating fragments at runtime, because a guard
that matches raw command text will happily block commits containing this
repo's own test data. The tool is aggressive enough to fight its own test
suite, which we find funnier than we probably should.

## Coverage at a glance

`OK` prevented, `ASK` prompts you, `NO` gets through.

### Local commits (the `commit-msg` hook)

| Path | | Notes |
| :-- | :--: | :-- |
| `git commit -m` / `-am` / repeated `-m` | OK | |
| `-F file`, `-F -`, heredoc, pipe | OK | The hook sees the assembled message, not your command |
| `$EDITOR` (no `-m`) | OK | |
| `--amend`, including `--no-edit` | OK | |
| `-C <commit>` (reuse a message) | OK | |
| `git merge -m`, `rebase -i` reword | OK | |
| Commits by any other tool in an installed repo | OK | It is a git hook, not a Claude hook |
| **`cherry-pick`, `rebase` replay, `git am`** | NO | git never runs `commit-msg` on these. `git rebase main` re-lands old messages intact. **The gap most likely to bite you.** |
| `git notes add -m`, `git tag -a -m`, `git stash push -m` | NO | git offers no hook for any of them |
| Repos where you have not run the install | NO | Per-repo on purpose; the session-start check reminds you |

### Keeping the hook switched on (the guard)

| Attempt | | Notes |
| :-- | :--: | :-- |
| `--no-verify`, `--no-verif`, `--no-veri` | OK | git accepts abbreviated flags, so all three are covered |
| `-n`, `-nm`, `-anm` flag clusters | OK | |
| `git -c core.hooksPath=... commit` | OK | |
| `rm` or `chmod -x` on the hook file | OK | |
| `GIT_CONFIG_GLOBAL=`, `HOME=`, `GIT_DIR=`, `HUSKY=0` prefixes | OK | |
| `/usr/bin/git`, `command git`, `env FOO=1 git`, `rtk git` | OK | |
| One layer of `bash -c`, `sh -c`, `eval`, or backticks | OK | |
| `git config core.hooksPath ...` (persistent) | ASK | `husky init` runs exactly this |
| `Write` or `Edit` into `.git/hooks/` or `.git/config` | ASK | Adding a remote is routine |
| `$(echo git commit --no-verify)` | NO | Arbitrary command substitution |
| Three or more nested wrappers with alternating quotes | NO | |
| A git alias repointing `core.hooksPath` after install | NO | Surfaces at the next session start, not immediately |

### Pull requests, issues and comments (`gh`)

| Call | | Notes |
| :-- | :--: | :-- |
| `gh pr create/edit --body` or `-b`, quoted or unquoted | OK | |
| `gh pr create/edit --body-file` or `-F <file>` | OK | The file is read and checked |
| `gh issue create/comment --body` | OK | |
| `gh pr merge --body` / `--subject` / `-b` / `-t` / `-F` | OK | Denied outright: it lands where nothing can clean it |
| `gh pr create --fill` / `--fill-verbose` | OK | The body comes from commits the hook already cleaned |
| `--body-file -` (stdin) | ASK | The hook cannot read stdin, so it asks instead of guessing |
| **`gh pr create --editor` / `--web`** | NO | Composed in an editor or a browser tab |
| `gh api` straight at the Contents API | NO | Matches tool names, not arbitrary HTTP |
| `gh release create --notes`, `gh gist create` | NO | Out of scope |

### GitHub MCP tools

| Tool | | Notes |
| :-- | :--: | :-- |
| `create_pull_request`, `update_pull_request` | OK | `body` field |
| `create_or_update_file`, `delete_file`, `push_files` | OK | `message` field |
| `merge_pull_request` | OK | |
| `add_issue_comment`, `add_reply_to_pull_request_comment` | OK | |
| `add_comment_to_pending_review`, `pull_request_review_write` | OK | |
| `issue_write`, `discussion_comment_write` | OK | |
| A renamed server, or the `mcp__plugin_*__` scoped prefix | OK | The matcher is a regex over the tool name |
| An MCP server whose git-write tools use different names | NO | |

### After the fact

| | | Notes |
| :-- | :--: | :-- |
| Editing a PR body in the GitHub web UI | NO | Nothing observes it |
| History that already carries trailers | NO | Non-goal. `git filter-repo` exists |

Short version: if it goes through `git` in an installed repo, or through
`gh` or the GitHub MCP tools in a Claude Code session, it is covered. The
real holes are replayed commits, browser-composed PR bodies, and raw API
calls.

MIT. Take it, fork it, ship it — no attribution required, which is, after
all, the entire point.
