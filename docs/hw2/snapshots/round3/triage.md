# Round 3 triage (final suite)

429 cases: 406 passed, 23 xfailed, 0 failed, 0 flaky over 5 seeds. Python line and branch coverage 100%; `static/app.js` 99.0%. Mutation by mutmut: **85.7%** (583/680, 97 survived).

The agent's own figure is 88.4% (601/680). It reran each diff and found 18 reported survivors are syntax errors or import crashes that mutmut counted as survived; the cause in mutmut was not confirmed. The two figures differ by exactly those 18. All rounds are compared on the mutmut figure.

Of the 76 mutants R3 killed, 32 came from one stopword table, so about 42% of the gain is data, not logic. Survivors left alone: 26 equivalent, 41 wording or data, 12 undocumented boundaries (`tests/MUTATION_NOTES.md`).

| Label | R2 | R3 | Note |
|---|---|---|---|
| TEST-BUG | 0 | 0 | |
| WEAK | 0 | 0 | |
| MIRROR | 0 | 1 | `test_every_stopword_is_dropped_from_the_query` restates a table by design; it was requested and is hand-written, not read from the app |
| REDUNDANT | 0 | 0 | |
| FLAKY | 0 | 0 | |

Bugs: same 19; 23 xfail cases. No mutant revealed wrong behavior.

**Unconfirmed, from reading only:** `resolve_missing_s2` sends all pending ids in one request, while its comment gives a 500-per-request limit. Not tested, not counted.

Remaining gaps: real Gemini quality (R3 extraction, R5 grounding); mutation does not cover `static/app.js`; browser tests depend on a matching Chromium. A human sample check of these audits has not been done.
