# Writing a hook in this repo

Nine conventions every hook here follows, plus three facts about Claude
Code's hook protocol that cost this project a fix round each to learn.

## The nine conventions

1. **Fail open.** Any exception, timeout, or unparseable input exits 0 and
   silent. Where the language cannot guarantee it — a git hook whose
   interpreter may be missing — a `/bin/sh` wrapper guarantees it instead,
   and a `signal.alarm` covers the hang the wrapper cannot.
2. **Enforce by deny, never by rewrite.** `deny > defer > ask > allow` is
   documented; multi-hook `updatedInput` behaviour is not.
3. **Prefer `ask` to `deny` when the action has a legitimate use.** A deny
   that blocks `husky init` is a bug, not a guard.
4. **Guards match on code; cleaners match on content.** A guard strips
   heredoc bodies and quoted spans before matching, so a message *about*
   `git push` is not mistaken for running one. A cleaner does the opposite.
   Separate passes over separately-derived strings, never one pass doing
   both.
5. **One `if:` rule per handler, one tool per rule.** Combining conditions
   is not supported; write another handler.
6. **Resolve, do not assume.** `core.hooksPath` before `.git/hooks`; the
   executable bit, not file existence; absolute paths in file-tool
   payloads.
7. **Never write into tracked files.** A tool the user did not commit does
   not belong in their repo.
8. **A deny or ask message says what to do instead**, not only what went
   wrong.
9. **One purpose per file, stdlib only, `timeout` declared** in
   `hooks.json` — the default is 600 seconds, which is never what a guard
   wants.

## Three facts about the protocol

- **`if` holds exactly one permission rule and matches one tool.** A single
  `if` cannot express "Bash or PowerShell" or "git commit or git push" —
  combining conditions is not supported. If a handler needs to react to two
  tools or two conditions, write another handler, not a compound `if`.
- **`if` is best-effort in the safe direction.** When Claude Code cannot
  determine which commands a Bash input actually runs — for example a
  command built from a variable, or wrapped in a way the matcher can't
  parse — it runs the hook regardless rather than skipping it. A guard must
  not assume `if` filtered anything; it still has to check.
- **`updatedInput` replaces the entire input object** and can be paired
  with `"ask"` rather than `"allow"` — it does not force auto-approval on
  its own. Multi-hook merge behaviour (what happens when two hooks both
  return `updatedInput` for the same tool call) is undocumented. Do not
  build enforcement on it; enforce by `deny`/`ask` instead (convention 2).

## Contributor note: this repo is self-blocking to test

A guard that denies commands containing attribution trailers — such as the
author's own `guard-bash.sh`, which matches the raw command text — denies
this repo's own fixtures, because the fixture text *is* the trailer. It also
denies `git commit` when the hook's cwd is not a repo. Fixtures must build
trailer strings at runtime from concatenated fragments (for example
`"Co-Authored" + "-By: Claude <noreply@anthropic.com>"`) and run from a
script file, never as inline literals in a command string.
