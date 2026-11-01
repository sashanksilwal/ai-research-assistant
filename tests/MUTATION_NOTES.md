# Mutation survivors: classification

Source: `feedback3/mutation.txt` (mutmut, non-browser tests only, reported 507/680 = 74.6%, 173 survivors).
Ids below are each survivor's position in that file, 1 to 173.

Every diff was applied to its own copy of the repo and run against `-m "not e2e"`. That re-run changed the
picture: **18 reported survivors never ran.** They are syntax errors or crash at import, so any real run fails
them. They are listed as "Not a survivor".

| Result | Mutants |
|---|---|
| Reported survived | 173 |
| Not a survivor (syntax error or import crash) | 18 |
| Killed by tests added this round | 76 |
| Left alone | 79 (26 equivalent, 41 wording/data, 12 boundary) |

Score: 601/680 = 88.4%, or 601/654 = 91.9% excluding the 26 equivalent mutants.

## Counts per module

| Module | Reported | Logic | Boundary tested | Boundary left | Wording/data tested | Wording/data left | Equivalent | Not a survivor |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| analysis | 29 | 7 | 1 | 6 | 0 | 11 | 1 | 3 |
| arxiv | 43 | 6 | 0 | 1 | 32 | 2 | 2 | 0 |
| citations | 24 | 14 | 0 | 3 | 0 | 0 | 7 | 0 |
| config | 8 | 2 | 0 | 0 | 0 | 2 | 0 | 4 |
| db | 6 | 0 | 0 | 0 | 0 | 0 | 5 | 1 |
| llm | 16 | 2 | 1 | 0 | 0 | 8 | 3 | 2 |
| main | 28 | 3 | 5 | 0 | 0 | 7 | 5 | 8 |
| metadata | 11 | 1 | 0 | 1 | 0 | 7 | 2 | 0 |
| pdf | 8 | 2 | 0 | 1 | 0 | 4 | 1 | 0 |
| **Total** | **173** | **37** | **7** | **12** | **32** | **41** | **26** | **18** |

## Not a survivor (18)

| Ids | Mutation | Why it can't survive |
|---|---|---|
| 110, 117, 137, 144 | `{*dict(r), "a": 1}`, `[x, /[...]]` | Syntax errors |
| 3, 7, 12 | `PLAIN_MATH = None`, `- PLAIN_MATH` | TypeError at import |
| 98, 99, 100, 102 | `DATA_DIR = None`, `DATA_DIR * "app.db"` | TypeError at import |
| 111, 130, 132, 134 | `X & None` in evaluated annotations | TypeError at import |
| 129 | `app = None` | Import fails: `None.get` |
| 152, 153 | Mount path `XX/XX`, directory `XXstaticXX` | AssertionError and RuntimeError at import |

Ids 152 to 154 didn't apply as patches, so they were edited in by hand.

## Logic (37, all killed)

| Ids | Behavior | Test |
|---|---|---|
| 30, 73, 74 | Base URLs broken | The fake transport now refuses schemes real httpx refuses, so existing tests fail. It was accepting `XXhttps://` |
| 77 to 80 | OpenAlex request parameters | `test_openalex_request_gets_the_fields_the_graph_needs`: a fake that applies `search` and `select` and rejects unknown parameters |
| 90 to 93 | Semantic Scholar request | `test_semantic_scholar_request_gets_the_fields_the_graph_needs`: a fake that needs `ids` and returns only requested fields |
| 84, 96 | A match not stored or shown as matched | `test_recorded_openalex_search_picks_the_first_close_title` |
| 75, 76 | `OPENALEX_EMAIL` ignored | `test_contact_email_is_read_from_the_documented_setting` |
| 63 | Empty abstract becomes junk | `test_search_treats_an_empty_abstract_as_empty` |
| 66 to 69 | PDF link from the feed ignored or left `http` | `test_search_uses_the_pdf_link_from_the_feed_over_https` |
| 14 | Title-case reference entry taken as a heading | `test_is_appendix_heading` |
| 19 | Appendix not found after the list | `test_tail_of_the_last_entry_goes_when_an_appendix_follows` |
| 21, 22, 24 | Last entry's tail stays | `test_tail_of_the_last_entry_goes_when_a_blank_line_ends_the_list` |
| 25, 26 | Text after the list is lost | `test_text_right_after_the_list_is_kept_when_no_blank_line_follows` |
| 97, 101 | Default data location moves, orphaning a library | `test_default_data_directory_is_data`, `test_paths_derive_from_data_dir_and_folder_is_created` |
| 112 | Fresh process crashes instead of explaining the missing key | `test_fresh_process_without_a_key_gets_a_readable_error` |
| 124 | 401 bad key not explained | `test_readable_error_messages` |
| 131, 133, 135 | Omitted optional fields stored as `""` | `test_save_treats_omitted_optional_fields_as_unknown` |
| 162 | Extraction sent with no instructions | `test_r3_gemini_reads_the_first_pages_of_the_upload` |
| 170 | Junk between PDF pages | `test_extract_text_keeps_pages_in_order_and_adds_nothing` |
| 172 | NUL replaced, not removed | `test_extract_text_removes_nul_characters` |

## Boundary

Tested because the limit is documented in the README or the UI (7):

| Ids | Limit | Test |
|---|---|---|
| 1 | 300,000 characters | `test_exactly_the_documented_300000_characters_are_sent_whole`, `test_text_over_the_documented_limit_is_cut_and_reported` |
| 150 | Same limit, cached branch | `test_cached_summary_of_exactly_300000_characters_is_not_truncated` |
| 116 | 40 s per model (`<= 40`, so lowering it stays legal) | `test_every_model_answers_within_the_documented_40_seconds` |
| 138 to 140 | 50 MB upload | `test_upload_over_the_documented_50_mb_is_rejected` |
| 151 | Non-empty question | `test_ask_accepts_the_shortest_and_longest_questions` |

Left alone: undocumented tuning values, where a test would only restate the number (12):

| Ids | Value |
|---|---|
| 13, 17 | Year gap of 1500 in the reference stripper |
| 15 | Small words up to 3 letters in a heading |
| 16 | Heading exactly at the 40% mark |
| 20, 23 | Search windows of 600 and 400 characters |
| 70, 85 | HTTP timeouts of 30 and 20 s (`assert_bounded_timeout` still requires a bound) |
| 81 | OpenAlex `per-page` 5 |
| 83 | Similarity exactly 0.9 |
| 155 | `HEAD_CHARS` 8000 |
| 166 | `MIN_TEXT_CHARS` 500 |

## Wording/data

Tested (32): ids 31 to 62, stopwords, by one table in `test_every_stopword_is_dropped_from_the_query`. The list
is written out in the test, not read from the app. `test_summary_asks_for_every_required_section` also checks
the five sections. It kills no survivor; it was requested as a check of the prompt's contract.

Left alone, because pinning these would be MIRROR (41):

| Ids | What |
|---|---|
| 2, 4, 5, 6, 8, 9, 10, 11 | Summary and Q&A instruction text. `test_r5_instructions_restrict_answers_to_the_paper` checks the two phrases R5 depends on; `XX` padding keeps them |
| 27, 28, 29, 163 | Prompt delimiters and the `[References omitted]` marker |
| 156 to 161 | Metadata instruction text |
| 71, 72, 113, 114, 115, 121, 122, 123, 125, 126, 141, 145 to 149, 167, 168, 171, 173 | User-facing messages. Tests check their substance (`HTTP 503`, `GEMINI_API_KEY`), which `XX` padding keeps |
| 103, 104 | Default Gemini model names, expected to change |
| 128 | FastAPI docs title |

## Equivalent (26)

| Ids | Why nothing observable changes |
|---|---|
| 18 | `break` to `continue`: years only increase, so every later year also exceeds the gap |
| 64, 65, 86, 87, 88, 89 | `rsplit(sep, 2)[-1]` and `rsplit(sep, 1)[+1]` give the same last segment for these URLs, which always contain the separator once |
| 82 | A missing title becomes `"XXXX"`, which is as unlike any real title as `""` |
| 94 | The first `resp` value is always overwritten by the loop |
| 95 | Nothing distinguishes the `not_found` label from another non-retried status |
| 105 to 109 | SQLite accepts any type name, and `XXTEXTXX` still has TEXT affinity |
| 118, 119 | A local annotation isn't evaluated, and `last_error` is always set before it's raised |
| 120 | `break` to `continue` on the last pass of a two-pass loop |
| 127 | Starlette also accepts a plain async generator as a lifespan |
| 136 | The replacement character only changes an internal filename |
| 142 | Unreachable: an upload with an empty filename is a 422 |
| 143 | `"XXXX"` contains no abstract to find, the same as `""` |
| 154 | Route name, never looked up |
| 164, 169 | PyMuPDF detects PDFs from their content when `filetype` is unknown |
| 165 | `"XXXX"` contains no year, the same as `""` |
