from src.filing_sections import extract_relevant_sections


def _fake_filing():
    return (
        "TABLE OF CONTENTS\n"
        "Item 1. Business\n"
        "Item 1A. Risk Factors\n"
        "Item 3. Legal Proceedings\n"
        "Item 7. Management Discussion and Analysis\n"
        "Item 7A. Quantitative and Qualitative Disclosures About Market Risk\n"
        "Item 8. Financial Statements\n\n"
        "PART I\n\nItem 1. Business\n" + ("Business description text. " * 50) + "\n\n"
        "Item 1A. Risk Factors\n" + ("Risk factor text about competition. " * 50) + "\n\n"
        "Item 3. Legal Proceedings\n" + ("Legal matter text about litigation. " * 50) + "\n\n"
        "PART II\n\nItem 7. Management Discussion and Analysis\n"
        + ("Revenue growth discussion text. " * 50)
        + "\n\n"
        "Item 7A. Quantitative and Qualitative Disclosures About Market Risk\n"
        + ("Interest rate risk text. " * 50)
        + "\n\n"
        "Item 8. Financial Statements\n" + ("Balance sheet data text. " * 50)
    )


def test_excludes_table_of_contents_entries():
    result = extract_relevant_sections(_fake_filing(), max_chars_per_section=500)
    # The TOC line "Item 1A. Risk Factors" appears with nothing after it on
    # that line - if we'd grabbed the TOC occurrence instead of the body,
    # the actual risk factor content wouldn't appear.
    assert "Risk factor text about competition" in result


def test_excludes_irrelevant_items():
    result = extract_relevant_sections(_fake_filing(), max_chars_per_section=500)
    assert "Business description text" not in result  # Item 1, not a target
    assert "Balance sheet data text" not in result  # Item 8, not a target


def test_includes_all_four_target_sections():
    result = extract_relevant_sections(_fake_filing(), max_chars_per_section=500)
    assert "Risk factor text" in result
    assert "Legal matter text" in result
    assert "Revenue growth discussion" in result
    assert "Interest rate risk text" in result


def test_output_is_dramatically_smaller_than_input():
    full = _fake_filing()
    result = extract_relevant_sections(full, max_chars_per_section=500)
    assert len(result) < len(full) / 3


def test_respects_max_chars_per_section_cap():
    result = extract_relevant_sections(_fake_filing(), max_chars_per_section=100)
    # 4 sections, each capped at 100 chars, plus separators - should be small
    assert len(result) < 4 * 100 + 4 * 10


def test_falls_back_gracefully_when_no_item_headings_found():
    plain_text = "This document has no SEC-style Item headings at all, just prose."
    result = extract_relevant_sections(plain_text, max_chars_per_section=500)
    assert result  # doesn't crash, returns something bounded
    assert len(result) <= 500 * 4


def test_empty_input_does_not_crash():
    result = extract_relevant_sections("", max_chars_per_section=500)
    assert result == ""
