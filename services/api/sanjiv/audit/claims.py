from __future__ import annotations

import re

BLOCKED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CARGO_OWNERSHIP", re.compile(r"\b(definitely|confirmed)\b.{0,40}\b(cargo|carrying)\b", re.I)),
    (
        "CHARTER_AVAILABILITY",
        re.compile(r"\b(available for charter|tanker booked|charter confirmed)\b", re.I),
    ),
    ("ORDER_EXECUTION", re.compile(r"\b(cargo secured|order placed|supplier confirmed)\b", re.I)),
    (
        "RESERVE_EXECUTION",
        re.compile(r"\b(reserve (was |has been )?released|release executed)\b", re.I),
    ),
    (
        "PRIVATE_INVENTORY",
        re.compile(r"\b(current|confirmed)\b.{0,30}\b(private inventory|reserve fill)\b", re.I),
    ),
    (
        "EXACT_PRICE_EFFECT",
        re.compile(r"\b(prices?|petrol|diesel)\b.{0,30}\b(exactly|will)\b.{0,20}%", re.I),
    ),
)


def blocked_claim_codes(text: str) -> list[str]:
    """Return stable reason codes for language that exceeds available decision evidence."""
    return [code for code, pattern in BLOCKED_PATTERNS if pattern.search(text)]


def assert_audited_narrative(text: str, allowed_figures: set[str]) -> list[str]:
    failures = blocked_claim_codes(text)
    figures = set(re.findall(r"(?<![A-Za-z0-9-])\d+(?:\.\d+)?%?", text))
    if not figures <= allowed_figures:
        failures.append("UNAUDITED_FIGURE")
    return sorted(set(failures))
