import pytest

from app import analysis
from helpers import reply, run

BODY = "Body sentence about the method. " * 40  # 1280 chars, so a heading after it is past the 40% mark
REFS = "\n".join(f"[{i}] Author. A title of a paper. Venue, 20{i:02d}." for i in range(1, 10))


def strip(text):
    return analysis.strip_references(text)


def test_reference_list_is_removed():
    result = strip(f"{BODY}\nReferences\n{REFS}\n")
    assert "[1] Author" not in result
    assert "[9] Author" not in result
    assert result.startswith(BODY)
    assert "[References omitted]" in result


@pytest.mark.parametrize(
    "heading", ["References", "REFERENCES", "7. References", "7 References", "Bibliography", "Literature Cited", "  references  "]
)
def test_heading_variants_are_recognized(heading):
    assert "[1] Author" not in strip(f"{BODY}\n{heading}\n{REFS}\n")


def test_text_without_a_heading_is_unchanged():
    assert strip(BODY) == BODY


def test_empty_text_is_unchanged():
    assert strip("") == ""


def test_heading_in_the_first_40_percent_is_ignored():
    text = f"Contents\nReferences\n{BODY}{BODY}{BODY}"
    assert strip(text) == text


def test_later_heading_is_used_when_an_early_one_exists():
    result = strip(f"References\n{BODY}{BODY}\nReferences\n{REFS}\n")
    assert result.startswith("References\n")
    assert "[1] Author" not in result


def test_mention_inside_a_sentence_is_not_a_heading():
    text = f"{BODY}\nSee the references for details.\n{BODY}"
    assert strip(text) == text


@pytest.mark.parametrize(
    "appendix", ["Appendix A", "APPENDIX", "Supplementary Material", "A", "B.2", "A Experimental Details", "C. Proofs Of Theorems"]
)
def test_appendix_after_references_is_kept(appendix):
    result = strip(f"{BODY}\nReferences\n{REFS}\n{appendix}\nAppendix body stays.\n")
    assert "[1] Author" not in result
    assert appendix in result
    assert "Appendix body stays." in result


def test_text_after_the_list_ends_is_kept():
    result = strip(f"{BODY}\nReferences\n{REFS}\n\nAcknowledgements of funding.")
    assert "[9] Author" not in result
    assert "Acknowledgements of funding." in result


def test_list_ends_where_years_stop_appearing():
    tail = "Trailing prose with no dates at all. " * 100
    result = strip(f"{BODY}\nReferences\n{REFS}\n\n{tail}")
    assert tail.strip() in result


def test_prose_before_a_much_later_year_is_kept():
    prose = "Trailing prose with no dates at all. " * 100
    result = strip(f"{BODY}{BODY}{BODY}{BODY}\nReferences\n{REFS}\n\n{prose}\nWritten in 2021.")
    assert prose.strip() in result


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Appendix B: Proofs", True),
        ("Appendices", True),
        ("supplementary figures", True),
        ("A", True),
        ("B.2.1", True),
        ("A Experimental Details", True),
        ("A new tool for measuring readability.", False),  # a reference entry
        ("A Smith, B Jones", False),
        ("Z Unrelated Heading", False),  # letters past H are not appendix labels
        ("", False),
    ],
)
def test_is_appendix_heading(line, expected):
    assert analysis._is_appendix_heading(line) is expected


def test_paper_block_at_the_limit_is_not_truncated():
    assert analysis._paper_block("x" * analysis.MAX_TEXT_CHARS)[1] is False


def test_paper_block_over_the_limit_is_cut_and_reported():
    block, truncated = analysis._paper_block("x" * (analysis.MAX_TEXT_CHARS + 1))
    assert truncated is True
    assert block.count("x") == analysis.MAX_TEXT_CHARS


def test_truncation_is_measured_after_stripping_references():
    body = "x" * (analysis.MAX_TEXT_CHARS - 100)
    refs = "\n".join(f"Ref {i} 2020" for i in range(30_000))
    assert analysis._paper_block(f"{body}\nReferences\n{refs}\n")[1] is False


def test_summarize_prompt_and_result(gemini):
    gemini.script(reply("## Problem\nSomething"))
    summary, truncated = run(analysis.summarize(f"{BODY}\nReferences\n{REFS}\n"))
    assert summary == "## Problem\nSomething"
    assert truncated is False
    assert "Summarize this paper" in gemini.last_prompt
    assert "[1] Author" not in gemini.last_prompt
    assert "Base everything on the paper text" in gemini.calls[0].config.system_instruction


def test_answer_puts_the_question_after_the_paper(gemini):
    gemini.script(reply("It is 42."))
    result, truncated = run(analysis.answer("Paper text", "What is it?"))
    assert (result, truncated) == ("It is 42.", False)
    assert gemini.last_prompt.index("</paper>") < gemini.last_prompt.index("Question: What is it?")
    instruction = gemini.calls[0].config.system_instruction
    assert "using only the paper text" in instruction
    assert "doesn't say" in instruction


