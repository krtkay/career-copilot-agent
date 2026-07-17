"""PII detection & redaction (regex-based, no external service).

Covers the common identifiers that show up in support conversations. This is a
pragmatic, transparent baseline; for a regulated deployment you would swap in
Microsoft Presidio behind the same ``scan_pii`` / ``redact_pii`` interface.
"""

from __future__ import annotations

import re

# Ordered so that more specific patterns (e.g. credit card) are checked first.
_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)\d{3}[\s-]?\d{4}\b"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "api_key_like": re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b"),
}

# credit_card/phone/ipv4 match on bare digit runs, which routinely false-positive on
# numeric IDs inside URLs (e.g. a job-listing "apply" link's path/query string).
# email/ssn/api_key_like are structurally distinctive enough (an "@", a 3-2-4 dash
# pattern, an sk-/pk-/rk- prefix) that they're left checking the real URL text too.
_URL_BLIND_LABELS = frozenset({"credit_card", "phone", "ipv4"})
_URL = re.compile(r"https?://\S+")


def _mask_urls(text: str) -> tuple[str, dict[str, str]]:
    """Replace URL spans with opaque placeholder tokens; return (masked, mapping)."""
    mapping: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        token = f"\x00URL{len(mapping)}\x00"
        mapping[token] = match.group(0)
        return token

    return _URL.sub(_replace, text), mapping


def _unmask_urls(text: str, mapping: dict[str, str]) -> str:
    for token, url in mapping.items():
        text = text.replace(token, url)
    return text


def scan_pii(text: str) -> list[str]:
    """Return the list of PII categories detected in ``text`` (deduplicated)."""
    found: list[str] = []
    for label, pattern in _PII_PATTERNS.items():
        haystack = _mask_urls(text)[0] if label in _URL_BLIND_LABELS else text
        if pattern.search(haystack):
            found.append(label)
    return found


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Replace detected PII with ``[REDACTED_<TYPE>]``.

    Returns ``(redacted_text, categories_redacted)``. URL spans are hidden from the
    credit_card/phone/ipv4 patterns (then restored) so a job-listing link's numeric
    ID is never mistaken for one of those.
    """
    redacted = text
    categories: list[str] = []
    for label, pattern in _PII_PATTERNS.items():
        if label in _URL_BLIND_LABELS:
            masked, url_map = _mask_urls(redacted)
            if pattern.search(masked):
                categories.append(label)
                masked = pattern.sub(f"[REDACTED_{label.upper()}]", masked)
            redacted = _unmask_urls(masked, url_map)
        else:
            if pattern.search(redacted):
                categories.append(label)
                redacted = pattern.sub(f"[REDACTED_{label.upper()}]", redacted)
    return redacted, categories
