"""Deterministic groundedness check for extracted field values.

Verifies each extracted value is actually present in the source document
text before it reaches the LLM verifier. Catches hallucinations the
verifier might rationalize as correct.

Part of D-GROUND-01 (Phase 1.5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class GroundResult:
    """Result of checking one field against the source text."""

    field_name: str
    is_grounded: bool
    is_ambiguous: bool  # value is short/common — substring match unreliable
    method: str  # which check passed/failed
    matched_excerpt: str | None  # snippet around the match


def check_groundedness(
    fields: list[dict],
    raw_text: str,
    schema_fields: list[dict],
) -> dict[str, GroundResult]:
    """Check every extracted field value against the source text.

    Args:
        fields: list of dicts with at least ``name`` and ``value`` keys.
        raw_text: the full document text to verify against.
        schema_fields: list of schema field dicts with ``name`` and
            ``field_type`` keys.

    Returns:
        Mapping of field name → GroundResult.
    """
    schema_map = {sf["name"]: sf for sf in schema_fields}
    normalized = normalize_text(raw_text)
    results: dict[str, GroundResult] = {}

    for f in fields:
        name = f["name"]
        value = f.get("value")

        if not value or not str(value).strip():
            results[name] = GroundResult(name, True, False, "na", None)
            continue

        value = str(value).strip()
        sf = schema_map.get(name, {})
        ftype = sf.get("field_type", "string")
        results[name] = _check_one(name, value, ftype, raw_text, normalized)

    return results


def _check_one(
    name: str,
    value: str,
    field_type: str,
    raw: str,
    normalized: str,
) -> GroundResult:
    """Dispatch to per-type matcher."""
    if field_type == "identifier":
        return _check_identifier(name, value, raw, normalized)
    if field_type == "date":
        return _check_date(name, value, raw, normalized)
    if field_type in ("currency_amount", "number"):
        return _check_number(name, value, raw, normalized)
    if field_type == "enum":
        return _check_enum(name, value, normalized)
    if field_type == "boolean":
        # Booleans are inferred, not literally in text
        return GroundResult(name, True, False, "na", None)
    # Default: string
    return _check_string(name, value, raw, normalized)


# ── Per-type matchers ──────────────────────────────────────────────────


def _check_identifier(
    name: str, value: str, raw: str, normalized: str,
) -> GroundResult:
    for variant in identifier_variants(value):
        if variant.lower() in normalized:
            return GroundResult(
                name, True, False, "identifier_normalized",
                excerpt_around(raw, variant),
            )
    return GroundResult(name, False, False, "unground", None)


def _check_date(
    name: str, value: str, raw: str, normalized: str,
) -> GroundResult:
    for variant in date_variants(value):
        if variant in raw or variant.lower() in normalized:
            return GroundResult(
                name, True, False, "fuzzy_date",
                excerpt_around(raw, variant),
            )
    return GroundResult(name, False, False, "unground", None)


def _check_number(
    name: str, value: str, raw: str, normalized: str,
) -> GroundResult:
    for variant in number_variants(value):
        if variant in raw or variant in normalized:
            return GroundResult(
                name, True, False, "number_normalized",
                excerpt_around(raw, variant),
            )
    return GroundResult(name, False, False, "unground", None)


def _check_enum(name: str, value: str, normalized: str) -> GroundResult:
    if value.lower() in normalized:
        return GroundResult(name, True, False, "enum_lower", None)
    is_ambiguous = len(value) < 4
    return GroundResult(name, False, is_ambiguous, "unground", None)


def _check_string(
    name: str, value: str, raw: str, normalized: str,
) -> GroundResult:
    if value.lower() in normalized:
        is_ambiguous = len(value) < 4
        return GroundResult(
            name, True, is_ambiguous, "string_substring",
            excerpt_around(raw, value),
        )
    agg_value = _aggressive_normalize(value)
    agg_raw = _aggressive_normalize(raw)
    if agg_value and agg_value in agg_raw:
        return GroundResult(name, True, False, "string_normalized", None)
    return GroundResult(name, False, False, "unground", None)


# ── Variant generators ─────────────────────────────────────────────────


def identifier_variants(value: str) -> list[str]:
    """Generate normalized variants of an identifier value."""
    base = value.strip()
    variants = {
        base,
        base.upper(),
        base.lower(),
        base.replace(" ", ""),
        base.replace("-", ""),
        base.replace(" ", "").replace("-", ""),
        base.replace("-", " "),
        base.replace(" ", "-"),
    }
    return list(variants)


def date_variants(value: str) -> list[str]:
    """Generate multiple date format variants from a value string.

    Tries to parse the value as a date, then returns it formatted in
    several common representations. Falls back to [value] if unparseable.
    """
    dt = _try_parse_date(value)
    if dt is None:
        return [value]

    day = dt.day
    month = dt.month
    year = dt.year
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    month_abbr = [
        "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    variants = {
        value,
        f"{year}-{month:02d}-{day:02d}",          # ISO
        f"{day:02d}/{month:02d}/{year}",           # DD/MM/YYYY
        f"{month:02d}/{day:02d}/{year}",           # MM/DD/YYYY
        f"{day:02d}-{month:02d}-{year}",           # DD-MM-YYYY
        f"{day:02d} {month_names[month]} {year}",  # DD Month YYYY
        f"{day:02d} {month_abbr[month]} {year}",   # DD Mon YYYY
        f"{month_names[month]} {day:02d}, {year}",  # Month DD, YYYY
        f"{day}/{month}/{year}",                    # D/M/YYYY (no padding)
        f"{day}-{month}-{year}",                    # D-M-YYYY (no padding)
        f"{day:02d}.{month:02d}.{year}",           # DD.MM.YYYY
    }
    return list(variants)


def number_variants(value: str) -> list[str]:
    """Generate variants of a number/currency value.

    Strips currency symbols and separators; tries with and without
    decimals and commas.
    """
    cleaned = re.sub(r"[₹$€£¥,\s]", "", value.strip())
    variants = {value.strip(), cleaned}

    # Add comma-separated version (Indian and Western)
    if re.fullmatch(r"\d+\.?\d*", cleaned):
        try:
            num = float(cleaned)
            variants.add(f"{num:,.2f}")      # 1,234.56
            variants.add(f"{num:.2f}")        # 1234.56
            variants.add(f"{num:,.0f}")       # 1,235
            variants.add(f"{num:.0f}")        # 1235
            if num == int(num):
                variants.add(str(int(num)))   # 1235
            # Indian format (last 3 digits separated, then groups of 2)
            int_part = str(int(num))
            if len(int_part) > 3:
                last3 = int_part[-3:]
                rest = int_part[:-3]
                indian = ""
                while len(rest) > 2:
                    indian = "," + rest[-2:] + indian
                    rest = rest[:-2]
                indian = rest + indian + "," + last3
                variants.add(indian)
        except (ValueError, OverflowError):
            pass

    # Keep the original digits-only form
    digits_only = re.sub(r"[^\d.]", "", cleaned)
    if digits_only:
        variants.add(digits_only)

    return list(variants)


# ── Text normalization ──────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _aggressive_normalize(text: str) -> str:
    """Strip all non-alphanumeric, lowercase, collapse spaces."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ── Helpers ─────────────────────────────────────────────────────────────


def excerpt_around(text: str, value: str, window: int = 40) -> str | None:
    """Return a snippet of text surrounding the first occurrence of value."""
    idx = text.lower().find(value.lower())
    if idx == -1:
        return None
    start = max(0, idx - window)
    end = min(len(text), idx + len(value) + window)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y%m%d",
]


def _try_parse_date(value: str) -> datetime | None:
    """Try common date formats; return datetime or None."""
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
