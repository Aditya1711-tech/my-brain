"""Unit tests for the groundedness module (D-GROUND-01).

Covers:
- check_groundedness top-level API
- Per-type matchers: string, identifier, date, number, enum, boolean
- Variant generators: identifier_variants, date_variants, number_variants
- Edge cases: empty values, short ambiguous values, missing fields
"""

import pytest

from app.services.pipeline.groundedness import (
    GroundResult,
    check_groundedness,
    date_variants,
    excerpt_around,
    identifier_variants,
    normalize_text,
    number_variants,
)


# ── Helpers ─────────────────────────────────────────────────────────────

RAW_TEXT = """
REPUBLIC OF INDIA
PASSPORT
Surname: DOE
Given Name: JOHN WILLIAM
Passport No: A1234567
Date of Birth: 15/01/1990
Date of Issue: 01 Jan 2020
Place of Issue: MUMBAI
Nationality: INDIAN
Sex: M
Amount Paid: ₹1,500.00
Reference: REF-2024-00123
"""

SCHEMA = [
    {"name": "full_name", "field_type": "string"},
    {"name": "passport_number", "field_type": "identifier"},
    {"name": "date_of_birth", "field_type": "date"},
    {"name": "nationality", "field_type": "enum"},
    {"name": "amount_paid", "field_type": "currency_amount"},
    {"name": "sex", "field_type": "enum"},
    {"name": "reference", "field_type": "identifier"},
    {"name": "is_scanned", "field_type": "boolean"},
]


# ── check_groundedness API tests ───────────────────────────────────────


def test_grounded_string_found_in_text():
    fields = [{"name": "full_name", "value": "JOHN WILLIAM"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["full_name"].is_grounded is True
    assert results["full_name"].method == "string_substring"


def test_grounded_string_case_insensitive():
    fields = [{"name": "full_name", "value": "John William"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["full_name"].is_grounded is True


def test_ungrounded_string_hallucinated():
    fields = [{"name": "full_name", "value": "Jane Smith"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["full_name"].is_grounded is False
    assert results["full_name"].method == "unground"


def test_empty_value_treated_as_grounded():
    fields = [{"name": "full_name", "value": ""}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["full_name"].is_grounded is True
    assert results["full_name"].method == "na"


def test_none_value_treated_as_grounded():
    fields = [{"name": "full_name", "value": None}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["full_name"].is_grounded is True
    assert results["full_name"].method == "na"


def test_boolean_always_grounded():
    fields = [{"name": "is_scanned", "value": "true"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["is_scanned"].is_grounded is True
    assert results["is_scanned"].method == "na"


# ── Identifier matcher ─────────────────────────────────────────────────


def test_identifier_exact_match():
    fields = [{"name": "passport_number", "value": "A1234567"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["passport_number"].is_grounded is True
    assert results["passport_number"].method == "identifier_normalized"


def test_identifier_with_added_hyphen():
    """Identifier found even if extracted with hyphen that's not in source."""
    fields = [{"name": "passport_number", "value": "A-1234567"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    # After stripping hyphens, "A1234567" should match
    assert results["passport_number"].is_grounded is True


def test_identifier_hallucinated():
    fields = [{"name": "passport_number", "value": "X9999999"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["passport_number"].is_grounded is False


def test_identifier_with_spaces_stripped():
    """Reference with hyphens should be found."""
    fields = [{"name": "reference", "value": "REF-2024-00123"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["reference"].is_grounded is True


# ── Date matcher ───────────────────────────────────────────────────────


def test_date_iso_found_as_dd_mm_yyyy():
    """Date of birth in text is DD/MM/YYYY; extracted as ISO."""
    fields = [{"name": "date_of_birth", "value": "1990-01-15"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["date_of_birth"].is_grounded is True
    assert results["date_of_birth"].method == "fuzzy_date"


def test_date_hallucinated():
    fields = [{"name": "date_of_birth", "value": "2000-06-30"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["date_of_birth"].is_grounded is False


def test_date_dd_month_yyyy_format():
    """'01 Jan 2020' is in the text and should match."""
    schema = [{"name": "issue_date", "field_type": "date"}]
    fields = [{"name": "issue_date", "value": "2020-01-01"}]
    results = check_groundedness(fields, RAW_TEXT, schema)
    assert results["issue_date"].is_grounded is True


# ── Number matcher ─────────────────────────────────────────────────────


def test_number_with_currency_symbol():
    fields = [{"name": "amount_paid", "value": "₹1,500.00"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["amount_paid"].is_grounded is True
    assert results["amount_paid"].method == "number_normalized"


def test_number_plain_digits():
    fields = [{"name": "amount_paid", "value": "1500"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["amount_paid"].is_grounded is True


def test_number_hallucinated():
    fields = [{"name": "amount_paid", "value": "2500.00"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["amount_paid"].is_grounded is False


# ── Enum matcher ───────────────────────────────────────────────────────


def test_enum_found_case_insensitive():
    fields = [{"name": "nationality", "value": "Indian"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["nationality"].is_grounded is True
    assert results["nationality"].method == "enum_lower"


def test_enum_hallucinated():
    fields = [{"name": "nationality", "value": "American"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["nationality"].is_grounded is False


def test_enum_short_value_ambiguous():
    """Short enum value like 'M' is marked ambiguous when not found."""
    # "M" IS actually in the text, so it should be grounded
    fields = [{"name": "sex", "value": "M"}]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["sex"].is_grounded is True


# ── String edge cases ──────────────────────────────────────────────────


def test_string_short_value_is_ambiguous():
    """Values under 4 chars are grounded but flagged ambiguous."""
    text = "The ID is AB."
    schema = [{"name": "code", "field_type": "string"}]
    fields = [{"name": "code", "value": "AB"}]
    results = check_groundedness(fields, text, schema)
    assert results["code"].is_grounded is True
    assert results["code"].is_ambiguous is True


def test_string_normalized_whitespace():
    """Collapsed whitespace still matches."""
    text = "Name:   JOHN    WILLIAM   DOE"
    schema = [{"name": "name", "field_type": "string"}]
    fields = [{"name": "name", "value": "JOHN WILLIAM DOE"}]
    results = check_groundedness(fields, text, schema)
    assert results["name"].is_grounded is True


def test_string_aggressive_normalize_strips_punctuation():
    """Aggressive normalization catches value with stripped punctuation."""
    text = "Account No.: 1234-5678-9012"
    schema = [{"name": "account", "field_type": "string"}]
    fields = [{"name": "account", "value": "123456789012"}]
    results = check_groundedness(fields, text, schema)
    assert results["account"].is_grounded is True
    assert results["account"].method == "string_normalized"


# ── Variant generator tests ───────────────────────────────────────────


def test_identifier_variants_produces_expected():
    variants = identifier_variants("A-123 456")
    assert "A-123 456" in variants
    assert "a-123 456" in variants
    assert "A-123456" in variants   # spaces stripped
    assert "A123 456" in variants   # hyphens stripped
    assert "A123456" in variants    # both stripped


def test_date_variants_from_iso():
    variants = date_variants("1990-01-15")
    assert "15/01/1990" in variants
    assert "01/15/1990" in variants
    assert "15 January 1990" in variants
    assert "15 Jan 1990" in variants
    assert "1990-01-15" in variants


def test_date_variants_unparseable_returns_original():
    variants = date_variants("not a date")
    assert variants == ["not a date"]


def test_number_variants_from_currency():
    variants = number_variants("₹1,500.00")
    assert "1500.00" in variants
    assert "1500" in variants
    assert "1,500.00" in variants


# ── Helpers ─────────────────────────────────────────────────────────────


def test_normalize_text():
    assert normalize_text("  Hello   WORLD  \n\t test  ") == "hello world test"


def test_excerpt_around_found():
    text = "The quick brown fox jumps over the lazy dog"
    result = excerpt_around(text, "fox", window=10)
    assert "fox" in result
    assert result.startswith("...")


def test_excerpt_around_not_found():
    assert excerpt_around("hello world", "xyz") is None


# ── Multiple fields at once ────────────────────────────────────────────


def test_multiple_fields_mixed_results():
    fields = [
        {"name": "full_name", "value": "JOHN WILLIAM"},
        {"name": "passport_number", "value": "X9999999"},
        {"name": "date_of_birth", "value": "1990-01-15"},
    ]
    results = check_groundedness(fields, RAW_TEXT, SCHEMA)
    assert results["full_name"].is_grounded is True
    assert results["passport_number"].is_grounded is False
    assert results["date_of_birth"].is_grounded is True


def test_field_not_in_schema_defaults_to_string():
    """Unknown field type should fall back to string matching."""
    schema = []  # no schema info
    fields = [{"name": "mystery", "value": "MUMBAI"}]
    results = check_groundedness(fields, RAW_TEXT, schema)
    assert results["mystery"].is_grounded is True
