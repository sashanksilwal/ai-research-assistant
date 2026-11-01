# Requirement traceability

Requirements and failures are from the HW1 plan. Each row is one completion check, mapped to the tests that
prove it. `test_requirements.py::test_every_test_named_in_the_traceability_table_exists` fails if a name here
stops existing.

Status: **Tested**, **Partial** (what can't be proven is stated), or **Open bug** (strict xfail).

## Requirements

| Req | Completion check | Tests | Status |
|---|---|---|---|
| R1 | Topic query renders cards with title, authors, year, abstract, link | `test_r1_topic_query_renders_all_five_fields`, `test_recorded_arxiv_search_parses_every_field` | Tested |
| R1 | Link opens | `test_r1_link_opens_the_paper_in_a_new_tab` | Tested (arXiv page is a local placeholder) |
| R1 | Bad query shows a message | `test_r1_bad_query_shows_a_message`, `test_recorded_bad_query_is_an_empty_feed_not_an_error`, `test_search_failure_is_shown_and_the_form_recovers`, `test_too_long_search_shows_a_readable_error` | Open bug (over-long query, B6) |
| R2 | Save 2, restart server, refresh: both listed | `test_r2_two_saved_papers_survive_a_server_restart_and_refresh` | Tested (separate OS process, killed and restarted on the same data directory) |
| R2 | Re-save doesn't duplicate | `test_r2_saving_again_after_a_restart_does_not_duplicate`, `test_saving_twice_returns_the_same_paper_without_downloading`, `test_save_is_safe_against_a_concurrent_save` | Tested |
| R2 | Browse the library | `test_library_card_details`, `test_save_then_find_in_library`, `test_list_is_newest_first_and_never_exposes_full_text` | Tested |
| R3 | Distinct PDFs yield correct title, authors, year, abstract | `test_r3_distinct_pdfs_yield_their_own_fields_without_gemini`, `test_r3_gemini_reads_the_first_pages_of_the_upload`, `test_generated_papers_really_are_multi_page` | Partial: PDFs are generated, multi-page and structured, but not from real publishers. Gemini's extraction quality needs the real model; only its input and output handling are tested |
| R3 | Same card component as search results | `test_r3_uploads_render_in_the_same_card_as_search_results` | Tested |
| R4 | Prompt contains the full text | `test_r4_prompt_contains_every_section_of_the_full_text`, `test_r4_reference_list_is_dropped_but_the_appendix_is_kept`, `test_r4_wrapped_author_line_does_not_end_the_reference_list` | Open bug (reference leak only; body text is always sent) |
| R4 | Abstract alone is never used | `test_r4_abstract_field_is_not_what_gets_summarized` | Tested |
| R4 | Papers without text are refused, never summarized from the abstract | `test_r4_paper_with_only_an_abstract_is_refused`, `test_upload_of_a_scan_warns_and_disables_analysis` | Tested |
| R5 | Natural-language question about the selected paper | `test_r5_question_is_asked_of_the_selected_paper_only`, `test_ask_with_the_button`, `test_enter_sends_and_shift_enter_adds_a_line`, `test_example_question_chip` | Tested |
| R5 | Answers come only from the paper | `test_r5_question_is_asked_of_the_selected_paper_only`, `test_r5_instructions_restrict_answers_to_the_paper` | Partial: proves only this paper and the restriction are sent. Whether the model obeys needs the real model |
| R5 | Off-paper question gives "the paper doesn't say" | `test_r5_instructions_restrict_answers_to_the_paper`, `test_r5_model_refusal_reaches_the_user_unchanged` | Partial: same limit. A faked refusal only proves the UI shows it |
| X1 | A → B when A cites B | `test_recorded_s2_batch_builds_edges_by_arxiv_id`, `test_recorded_openalex_search_picks_the_first_close_title`, `test_graph_draws_papers_and_citations` | Tested |
| X1 | Only library papers | `test_reference_outside_the_library_is_ignored`, `test_recorded_s2_batch_links_uploads_by_title_when_no_arxiv_id`, `test_title_less_reference_does_not_link_to_a_non_latin_title` | Open bug (B12) |
| X1 | Click opens the paper | `test_graph_click_opens_the_paper` | Tested with a real mouse click on the real canvas |

## Failures that really happened

| # | Failure | Tests |
|---|---|---|
| 1 | Stopwords ANDed into the arXiv query | `test_failure_1_stopwords_do_not_empty_the_search` |
| 2 | NUL characters cut SQLite's `length()` | `test_failure_2_nul_characters_do_not_cut_the_stored_text` |
| 3 | Reference stripper removed an appendix with a bare "A" heading | `test_failure_3_stripper_keeps_an_appendix_with_a_bare_letter_heading` |
| 4 | Models never answered; spinner ran forever | `test_failure_4_models_that_never_answer_end_in_an_error`, `test_failure_4_spinner_stops_when_models_never_answer` |
| 5 | 503 and 429 on some models | `test_failure_5_503_and_429_fall_back_to_a_working_model` |
| 6 | Raw LaTeX; KaTeX rendered formulas twice | `test_failure_6_latex_renders_once_and_never_raw`, `test_each_formula_renders_exactly_once` |
| 7 | Inactive tab labels invisible | `test_failure_7_inactive_tab_labels_are_visible` |
| 8 | Line-break hyphenation kept in the abstract | `test_failure_8_line_break_hyphenation_is_removed_from_the_abstract`, `test_failure_8_hyphenation_with_a_trailing_space_is_removed` (open bug) |
| 9 | Semantic Scholar 429; graph fell back and recovered | `test_failure_9_rate_limited_s2_falls_back_to_openalex_then_recovers` |
| 10 | Junk OpenAlex record matched | `test_failure_10_junk_openalex_record_is_not_matched`, `test_failure_10_real_record_is_found_behind_the_junk` |
