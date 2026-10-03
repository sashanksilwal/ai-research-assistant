# Project notes for Claude Code

CS593 HW1 AI Research Assistant. Plan: `docs/PLAN.md`. Coding-agent log (reflection evidence): `docs/agent-log.md`.

## Known agent mistakes — do not repeat
- **No backslashes inside f-string expressions.** The venv is Python 3.11 (system `/usr/bin/python3` is 3.9); `f"{re.sub(r'\w', ...)}"` is a SyntaxError before Python 3.12. Compute the value into a variable first. (Made twice on 2026-10-02: status-line script, then `app/main.py`, which stopped the server from starting.)

- **Never send the user's personal information (email, name, keys) to any external service** — not in URLs, headers, or test requests — unless the user explicitly asks. On 2026-10-02 the agent put the user's email in OpenAlex `mailto=` parameters while probing the API, without asking. Contact details for APIs go only in opt-in `.env` settings the user fills in.

## Workflow rules
- After editing Python, run `.venv/bin/python -c "import app.main"` **before** restarting the server, so syntax errors show up immediately instead of as failed requests.
- After editing `static/app.js`, run `node --check static/app.js`.
- The agent's browser automation cannot reach this machine's localhost; the user does visual UI checks. Don't commit a milestone until the user has confirmed the UI.
- Log each milestone and every agent mistake in `docs/agent-log.md`; screenshots go in `docs/screenshots/`.
- Never commit `.env` or `data/`.
