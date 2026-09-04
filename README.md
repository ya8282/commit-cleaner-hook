# Commit cleaner hook

Prevent Claude (`@anthropic.com`) from slipping into your git commit messages and pull requests.

You've probably seen these surface before:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_ID
```

Claude Code has an [attribution](https://code.claude.com/docs/en/settings-reference#attribution) setting that turns them off. It works right up until the
setting gets reset/deprecated, a different assistant shows up with its own signature, or you paste a message from somewhere and it arrives with a friend. 
This is the layer that doesn't depend on anyone remembering.

## Install

1. Add the plugin in Claude Code by running the following commands:

```
/plugin marketplace add ya8282/commit-cleaner-hook
/plugin install commit-cleaner@commit-cleaner-hook
```

2. Then, in each project you want to keep clean:

```
/commit-cleaner-install
```

Claude Code reminds you at the start of a session if the current project is missing it.

Commit cleaner runs prior to other installed pre-commit hooks, such as `commitlint` and `husky`.

Additional commands:

```
# Uninstall
python3 <PLUGIN_DIR>/install.py --uninstall

# List the installed locations
python3 <PLUGIN_DIR>/install.py --list

# Update to the latest version
python3 <PLUGIN_DIR>/install.py --upgrade
```

By default, your `<PLUGIN_DIR>` is `~/.claude/plugins/`. The session-start reminder prints the full path.

See [What the hook skips](#what-the-hook-skips).

## How it works

This plugin is composed of two components:

1. **A `commit-msg` git hook**: cleans every commit in a repo where it's installed.
2. **A `PreToolUse` guard**: prevents most workarounds of the `commit-msg` hook.

The git hook performs the cleaning, and it works regardless of who makes the commit.
The guard stops the hook from being skipped or switched off.

See [Coverage at a glance](#coverage-at-a-glance) for more details.

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

Settings are stored in `git config` instead of environment variables, so every
user inherits the same commit behavior.

```
git config commitcleaner.patterns .commitcleaner-patterns
git config commitcleaner.defaults false   # use only your file
```

This features one Python regex per line, matched case-insensitively against whole lines.

## What the hook skips

While the hooks prevent nearly all the paths that Claude Code can crawl
into your commit messages, there are a few remaining ways it can happen:

- **Commits copied in from somewhere else.** `rebase`, `cherry-pick` and
  friends replay existing messages without re-running the hook, so an old
  trailer comes along for the ride. This is the one that will actually bite
  you.
- **Anything you write outside the terminal** — a pull request body typed
  into a browser tab or popped open in an editor. Nothing is watching there.
- **Projects where you haven't run the install.** It's per-project by
  design; a machine-wide version would quietly break other tools' hooks.
- **Deliberate evasion.** This stops accidents and habits. Someone
  determined to route around it can, and at that point they're not slipping
  up, they're committing a crime.

## Contributing

`docs/writing-a-hook.md` contains the conventions and the Claude Code
hook details. Commit cleaner uses `stdlib`-only on Python 3.9+ and requires 
installing a test runner and a linter as dependencies:

```
pip install pytest ruff
pytest
ruff check .
```

## Coverage at a glance

✅ prevented &nbsp;·&nbsp; ⚠️ prompts you &nbsp;·&nbsp; ❌ gets through

### Local commits (the `commit-msg` hook)

| Path | | Notes |
| :-- | :--: | :-- |
| `git commit -m` / `-am` / repeated `-m` | ✅ | |
| `-F file`, `-F -`, heredoc, pipe | ✅ | The hook sees the assembled message, not your command |
| `$EDITOR` (no `-m`) | ✅ | |
| `--amend`, including `--no-edit` | ✅ | |
| `-C <commit>` (reuse a message) | ✅ | |
| `git merge -m`, `rebase -i` reword | ✅ | |
| Commits by any other tool in an installed repo | ✅ | It is a git hook, not a Claude hook |
| **`cherry-pick`, `rebase` replay, `git am`** | ❌ | git never runs `commit-msg` on these. `git rebase main` re-lands old messages intact. **The gap most likely to bite you.** |
| `git notes add -m`, `git tag -a -m`, `git stash push -m` | ❌ | git offers no hook for any of them |
| Repos where you have not run the install | ❌ | Per-repo on purpose; the session-start check reminds you |

### Keeping the hook switched on (the guard)

| Attempt | | Notes |
| :-- | :--: | :-- |
| `--no-verify`, `--no-verif`, `--no-veri` | ✅ | git accepts abbreviated flags, so all three are covered |
| `-n`, `-nm`, `-anm` flag clusters | ✅ | |
| `git -c core.hooksPath=... commit` | ✅ | |
| `rm` or `chmod -x` on the hook file | ✅ | |
| `GIT_CONFIG_GLOBAL=`, `HOME=`, `GIT_DIR=`, `HUSKY=0` prefixes | ✅ | |
| `/usr/bin/git`, `command git`, `env FOO=1 git`, `rtk git` | ✅ | |
| One layer of `bash -c`, `sh -c`, `eval`, or backticks | ✅ | |
| `git config core.hooksPath ...` (persistent) | ⚠️ | `husky init` runs exactly this |
| `Write` or `Edit` into `.git/hooks/` or `.git/config` | ⚠️ | Adding a remote is routine |
| `$(echo git commit --no-verify)` | ❌ | Arbitrary command substitution |
| Three or more nested wrappers with alternating quotes | ❌ | |
| A git alias repointing `core.hooksPath` after install | ❌ | Surfaces at the next session start, not immediately |

### Pull requests, issues and comments (`gh`)

| Call | | Notes |
| :-- | :--: | :-- |
| `gh pr create/edit --body` or `-b`, quoted or unquoted | ✅ | |
| `gh pr create/edit --body-file` or `-F <file>` | ✅ | The file is read and checked |
| `gh issue create/comment --body` | ✅ | |
| `gh pr merge --body` / `--subject` / `-b` / `-t` / `-F` | ✅ | Denied outright: it lands where nothing can clean it |
| `gh pr create --fill` / `--fill-verbose` | ✅ | The body comes from commits the hook already cleaned |
| `--body-file -` (stdin) | ⚠️ | The hook cannot read stdin, so it asks instead of guessing |
| **`gh pr create --editor` / `--web`** | ❌ | Composed in an editor or a browser tab |
| `gh api` straight at the Contents API | ❌ | Matches tool names, not arbitrary HTTP |
| `gh release create --notes`, `gh gist create` | ❌ | Out of scope |

### GitHub MCP tools

| Tool | | Notes |
| :-- | :--: | :-- |
| `create_pull_request`, `update_pull_request` | ✅ | `body` field |
| `create_or_update_file`, `delete_file`, `push_files` | ✅ | `message` field |
| `merge_pull_request` | ✅ | |
| `add_issue_comment`, `add_reply_to_pull_request_comment` | ✅ | |
| `add_comment_to_pending_review`, `pull_request_review_write` | ✅ | |
| `issue_write`, `discussion_comment_write` | ✅ | |
| A renamed server, or the `mcp__plugin_*__` scoped prefix | ✅ | The matcher is a regex over the tool name |
| An MCP server whose git-write tools use different names | ❌ | |

### After the fact

| | | Notes |
| :-- | :--: | :-- |
| Editing a PR body in the GitHub web UI | ❌ | Nothing observes it |
| History that already carries trailers | ❌ | Non-goal. `git filter-repo` exists |

Short version: if it goes through `git` in an installed repo, or through
`gh` or the GitHub MCP tools in a Claude Code session, the commit cleaner covers it.
It doesn't cover the more complex situations like replayed commits, browser-composed PR bodies, and raw API calls.

**License**: MIT