"""
SEC 10-K relevant-section extraction.

Extracts the actual financial/legal sections required by Agentic Wealth
Intelligence while explicitly preserving revenue disclosures/tables.

The extractor is deterministic and company-agnostic. It cleans SEC/XBRL
conversion noise before selecting filing sections consumed by the extraction
agent.
"""

from __future__ import annotations

import re


TARGET_ITEMS = ["1a", "3", "7", "7a"]

DEFAULT_MAX_CHARS_PER_SECTION = 20000
DEFAULT_MAX_TOTAL_CHARS = 80000
REVENUE_MAX_CHARS = 16000


ITEM_HEADING_PATTERN = re.compile(
    r"""(?ix)
    (?:
        ^[ \t]*
        |
        (?<=\n)
        |
        (?<=[.;:])\s+
    )
    item[ \t]+
    (1a|3|7a|7)
    (?:[ \t]*[\.:])?
    [ \t]+
    """
)


XBRL_NOISE_PATTERNS = (
    "http://fasb.org/",
    "https://fasb.org/",
    "http://xbrl.org/",
    "https://xbrl.org/",
    "iso4217:",
    "xbrli:",
    "us-gaap:",
)


def _is_xbrl_noise(text: str) -> bool:
    """Return True when text is dominated by XBRL taxonomy metadata."""

    if not text:
        return False

    lowered = text.casefold()

    hits = sum(
        marker.casefold() in lowered
        for marker in XBRL_NOISE_PATTERNS
    )

    return hits >= 3


def _find_heading_positions(text: str, item_number: str) -> list[int]:
    """Find likely Item headings while rejecting TOC/metadata hits."""

    positions: list[int] = []

    for match in ITEM_HEADING_PATTERN.finditer(text):
        if match.group(1).lower() != item_number.lower():
            continue

        start = match.start()

        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", start)

        if line_end == -1:
            line_end = len(text)

        line = text[line_start:line_end].strip()

        if not line:
            continue

        if re.search(r"\.{3,}", line):
            continue

        if re.search(r"\b\d{1,4}\s*$", line) and len(line) < 160:
            continue

        if _is_xbrl_noise(line):
            continue

        positions.append(start)

    return positions


def _clean_sec_text(text: str) -> str:
    """Clean common SEC HTML/XBRL conversion artifacts."""

    if not text:
        return ""

    text = re.sub(
        r"&#160;|&nbsp;",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"&#8220;|&#8221;|&ldquo;|&rdquo;",
        '"',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"&#8217;|&rsquo;",
        "'",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"&#8211;|&ndash;",
        "-",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"&#8212;|&mdash;",
        "-",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+\n", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _extract_revenue_disclosure(
    full_text: str,
    max_chars: int = REVENUE_MAX_CHARS,
) -> str:
    """
    Extract the strongest revenue-disclosure region available.

    Priority:
    1. Apple Products and Services Performance
    2. Revenue by segment
    3. Revenue by product/category
    4. Disaggregated revenue
    5. Net sales by segment/category/product

    The revenue disclosure is deliberately extracted BEFORE Item-section
    payload limiting so it cannot be lost by the global 80K-character cap.
    """

    patterns = [
        r"Products\s+and\s+Services\s+Performance",
        r"Revenue\s+by\s+segment",
        r"Revenue\s+by\s+product",
        r"Revenue\s+by\s+category",
        r"Net\s+sales\s+by\s+segment",
        r"Net\s+sales\s+by\s+product",
        r"Net\s+sales\s+by\s+category",
        r"Disaggregated\s+Revenue",
        r"Revenue\s+Disaggregation",
        r"Revenue\s+from\s+external\s+customers",
        r"Net\s+revenue\s+by\s+segment",
    ]

    best_match: re.Match[str] | None = None

    for pattern in patterns:
        match = re.search(
            pattern,
            full_text,
            re.IGNORECASE,
        )

        if match is None:
            continue

        # Prefer Products and Services Performance when present.
        if re.search(
            r"Products\s+and\s+Services\s+Performance",
            match.group(0),
            re.IGNORECASE,
        ):
            best_match = match
            break

        if best_match is None:
            best_match = match

    if best_match is None:
        return ""

    start = best_match.start()

    candidate = full_text[
        start:min(len(full_text), start + max_chars)
    ].strip()

    if not candidate:
        return ""

    if _is_xbrl_noise(candidate[:5000]):
        return ""

    return candidate


def _extract_item_sections(
    full_text: str,
    max_chars_per_section: int,
) -> list[str]:
    """Extract requested SEC Item sections."""

    all_heading_positions: list[tuple[int, str]] = []

    for item_number in TARGET_ITEMS:
        for position in _find_heading_positions(
            full_text,
            item_number,
        ):
            all_heading_positions.append(
                (position, item_number)
            )

    all_heading_positions.sort(
        key=lambda item: item[0]
    )

    sections: list[str] = []

    for item_number in TARGET_ITEMS:
        positions = [
            position
            for position, number in all_heading_positions
            if number == item_number
        ]

        if not positions:
            continue

        start = positions[-1]

        next_positions = [
            position
            for position, _ in all_heading_positions
            if position > start
        ]

        end = (
            min(next_positions)
            if next_positions
            else min(
                len(full_text),
                start + max_chars_per_section,
            )
        )

        section_text = full_text[
            start:end
        ].strip()

        if not section_text:
            continue

        if _is_xbrl_noise(section_text[:5000]):
            continue

        sections.append(
            section_text[:max_chars_per_section]
        )

    return sections


def _find_narrative_start(full_text: str) -> int:
    """Locate the beginning of human-readable filing content."""

    candidates = [
        r"\bPART\s+I\b",
        r"\bPART\s+II\b",
        r"\bItem\s+1A[\.:]?\s+Risk\s+Factors\b",
        r"\bItem\s+7[\.:]?\s+Management",
        r"\bCONSOLIDATED\s+STATEMENTS?\s+OF\s+OPERATIONS\b",
        r"\bCONSOLIDATED\s+STATEMENTS?\s+OF\s+INCOME\b",
    ]

    positions: list[int] = []

    for pattern in candidates:
        match = re.search(
            pattern,
            full_text,
            re.IGNORECASE,
        )

        if match:
            positions.append(match.start())

    return min(positions) if positions else 0


def extract_relevant_sections(
    full_text: str,
    max_chars_per_section: int = DEFAULT_MAX_CHARS_PER_SECTION,
) -> str:
    """
    Extract relevant 10-K sections.

    Revenue disclosure is intentionally placed FIRST so the global payload
    limit cannot silently remove the authoritative revenue table.
    """

    if not full_text:
        return ""

    text = _clean_sec_text(full_text)

    if not text:
        return ""

    sections: list[str] = []

    # ------------------------------------------------------------
    # 1. Revenue disclosure FIRST.
    # ------------------------------------------------------------

    revenue_disclosure = _extract_revenue_disclosure(text)

    if revenue_disclosure:
        sections.append(
            "REVENUE DISCLOSURE\n\n"
            + revenue_disclosure
        )

    # ------------------------------------------------------------
    # 2. SEC Item sections.
    # ------------------------------------------------------------

    sections.extend(
        _extract_item_sections(
            text,
            max_chars_per_section,
        )
    )

    # ------------------------------------------------------------
    # 3. Fallback if no structured sections were found.
    # ------------------------------------------------------------

    if not sections:
        narrative_start = _find_narrative_start(text)

        fallback = text[
            narrative_start:
            narrative_start + DEFAULT_MAX_TOTAL_CHARS
        ].strip()

        if fallback and not _is_xbrl_noise(
            fallback[:5000]
        ):
            return fallback[:DEFAULT_MAX_TOTAL_CHARS]

        meaningful_patterns = [
            r"Risk\s+Factors",
            r"Management(?:'s|â€™s)\s+Discussion",
            r"Legal\s+Proceedings",
            r"Revenue",
            r"Net\s+sales",
            r"Long[-\s]+term\s+debt",
        ]

        for pattern in meaningful_patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if not match:
                continue

            fallback = text[
                match.start():
                match.start() + DEFAULT_MAX_TOTAL_CHARS
            ]

            if fallback and not _is_xbrl_noise(
                fallback[:5000]
            ):
                return fallback[:DEFAULT_MAX_TOTAL_CHARS]

        return ""

    # ------------------------------------------------------------
    # 4. Deduplicate.
    # ------------------------------------------------------------

    unique_sections: list[str] = []
    seen: set[str] = set()

    for section in sections:
        section = section.strip()

        if not section:
            continue

        key = re.sub(
            r"\s+",
            " ",
            section[:500],
        ).casefold()

        if key in seen:
            continue

        seen.add(key)
        unique_sections.append(section)

    # ------------------------------------------------------------
    # 5. Global payload limit.
    #
    # Revenue disclosure is already first, therefore it receives priority.
    # ------------------------------------------------------------

    result_parts: list[str] = []
    total_chars = 0

    for section in unique_sections:
        separator_size = 9 if result_parts else 0

        if total_chars + separator_size >= DEFAULT_MAX_TOTAL_CHARS:
            break

        remaining = (
            DEFAULT_MAX_TOTAL_CHARS
            - total_chars
            - separator_size
        )

        if remaining <= 0:
            break

        result_parts.append(
            section[:remaining]
        )

        total_chars += (
            separator_size
            + min(len(section), remaining)
        )

    return "\n\n---\n\n".join(result_parts)