# Round 3 — Mutation feedback

**Agent:** same subagent, resumed, in the same scratch copy.
**Input given:** `mutation.txt` from round2: the score table and a diff for each of the 173 reported survivors.

**Prompt, verbatim:**

> Round 3: kill the meaningful surviving mutants listed in `feedback3/mutation.txt`.
>
> The file has a score table, then a diff for each of the 173 mutants that survived mutmut. Non-browser tests only (`-m "not e2e"`) count against these.
>
> 1. Classify every survivor into one of these, by group where many share a cause, with counts per module:
>    - **Logic:** a real behavior change a user or requirement would notice. Write a test that fails for the mutant, based on intended behavior.
>    - **Boundary:** an off-by-one on a limit. Test it only if the limit is a documented or meaningful boundary.
>    - **Wording/data:** prompt text, user-facing strings, stopword entries. Don't pin strings just to kill mutants. A few checks are worthwhile: every stopword is actually dropped from the query (table-driven, one test), every required section is requested in the summary prompt.
>    - **Equivalent:** no observable behavior change. Explain why, and don't test it.
> 2. Do not write tests that assert exact prompts or constants merely to raise the score. That is the failure the audit calls MIRROR, and I'll check for it.
> 3. Prefer one strong test that kills many mutants to many narrow tests.
>
> Rules: same as before. Don't change `app/` or `static/`, keep strict xfails, no network, nothing outside this directory, foreground runs. Keep the suite under 450 cases. If a mutant shows the app's behavior is actually wrong, record it as a new bug with a strict xfail.
>
> Report: the classification counts per module; tests added, changed and removed; survivors you left alone and why; new bugs. Add `tests/MUTATION_NOTES.md` with the classification so it is reviewable.
