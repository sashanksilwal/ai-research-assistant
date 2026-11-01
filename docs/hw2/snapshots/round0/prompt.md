# Round 0 — Baseline generation

**Agent:** fresh Claude Code subagent (general-purpose, Claude Opus 5.5), no shared context with the planning session.
**Workspace:** scratch copy holding only `app/`, `static/`, `README.md`, `requirements.txt`, `railway.json`, `.env.example`, `.python-version`.
Withheld on purpose: `docs/`, `CLAUDE.md`, `scripts/`, `.git`, `.env`, `data/`, so the HW1 plan and bug log could not leak in.

**Prompt, verbatim:**

> The repository is at <scratch path> — work only inside this directory. Python environment with all packages and pytest tools: <repo>/.venv/bin/python (use it, but do not change it and do not read anything else in that parent project).
>
> Examine this repository and write an automated test suite for the web application. Cover its main functionality, including normal use cases, edge cases and error handling. Use a testing framework appropriate for the stack, and make sure the tests are executable and contain assertions that check expected behavior. Put tests in `tests/` and dev dependencies in `requirements-dev.txt`. Tests must not call any real external service or use the real `data/` directory or `.env`. Do not change application code. Run the tests and report the results.

**Deviations from the plan:** the plan said a fresh interactive session; the user instead asked the agent to prompt itself, so a subagent ran it. The first two sentences were added to point at the scratch copy.

**Contamination to disclose:** the venv already held pytest, pytest-socket, pytest-randomly, playwright and mutmut (installed for measurement), so tool choice was partly primed. The subagent also ran its own 40-fault injection check and closed 4 gaps before reporting, unprompted, so R0 is stronger than a one-shot generation.
