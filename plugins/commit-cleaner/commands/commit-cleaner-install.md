---
description: Install the commit-cleaner commit-msg hook into the current repo
---

Run `python3 ${CLAUDE_PLUGIN_ROOT}/install.py` and report what it printed.

If it refused because the hooks directory is tracked by git, show the user the
two lines it printed and explain that a shared hooks directory is team
infrastructure, so the tool will not edit it silently.
