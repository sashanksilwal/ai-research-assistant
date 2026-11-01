# Round 2 triage

411 cases: 388 passed, 23 xfailed, 0 failed, 0 flaky over 5 seeds. Python coverage 100%; `static/app.js` 99.0%. Mutation: see `mutation.txt`.

| Label | R1 | R2 | Note |
|---|---|---|---|
| TEST-BUG | 0 | 0 | Fakes corrected against recordings; those were wrong models, not wrong assertions |
| WEAK | 0 | 0 | |
| MIRROR | 10 | 0 | Real marked, DOMPurify, KaTeX, vis-network replace all stubs |
| REDUNDANT | 0 | 0 | 8 replaced tests removed |
| FLAKY | 0 | 0 | A round 1 test was found flaky under coverage and fixed; the 5-seed check had missed it |

## New bugs

| ID | Severity | Behavior | Detecting test |
|---|---|---|---|
| B15 | Medium | Math is restored after DOMPurify, so math inside an HTML attribute corrupts the sanitized DOM. No script ran in Chromium 153; DOM corruption shown, XSS not demonstrated | `test_math_inside_an_attribute_stays_inside_it` |
| B16 | Low | Model text containing `KATEXMATH99END` renders as "undefined" | `test_text_resembling_the_math_placeholder_is_kept` |
| B17 | Low | `$x$` in a code span renders as a formula | `test_code_span_is_shown_verbatim` |
| B18 | Medium | Wrapped reference line such as `G. E. Hinton and R. Salakhutdinov` is read as an appendix heading, so the rest of the reference list reaches the prompt | `test_r4_wrapped_author_line_does_not_end_the_reference_list` |
| B19 | Low | Hyphenation fix misses `representa- ` with a trailing space | `test_failure_8_hyphenation_with_a_trailing_space_is_removed` |

## Fakes versus reality

- A bad arXiv query returns an empty 200 feed, not the `/api/errors` entry the app's comment and the fake assumed.
- The fake used `http` PDF links; alternate link, `updated`, `category` and `arxiv:` elements were missing from the fake.
- Real Semantic Scholar references can have null `paperId` and `externalIds`.
- All 41 recorded references have titles, which lowers the likelihood of the B12 title-less trigger.

## Cannot be tested without the real model

R5 "answers come only from the paper" and the off-paper refusal; R3 extraction quality. Tests prove what is sent and that a refusal reaches the user unchanged.
