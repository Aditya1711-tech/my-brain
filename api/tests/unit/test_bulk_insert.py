"""Tests for ExtractedFieldsRepo.bulk_insert (D-AGENT-INSERT-01).

Verifies:
1. Single execute call for multiple fields (not N calls)
2. SQL contains multi-row VALUES clause
3. Empty list results in no execute call
4. Single field works correctly
5. All field values are passed as params
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories.extracted_fields_repo import (
    ExtractedFieldCreate,
    ExtractedFieldsRepo,
)


def _mock_db():
    """Build a mock AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_field(**overrides):
    """Create an ExtractedFieldCreate with defaults."""
    defaults = {
        "user_id": uuid4(),
        "document_id": uuid4(),
        "field_name": "full_name",
        "field_value": "John Doe",
        "field_type": "string",
        "confidence": None,
        "is_entity_ref": False,
    }
    defaults.update(overrides)
    return ExtractedFieldCreate(**defaults)


@pytest.mark.asyncio
async def test_empty_list_no_db_call():
    """Empty field list results in zero DB calls."""
    db = _mock_db()
    repo = ExtractedFieldsRepo(db)

    await repo.bulk_insert([])

    db.execute.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_single_field_one_execute():
    """Single field produces one execute call with one VALUES row."""
    db = _mock_db()
    repo = ExtractedFieldsRepo(db)

    await repo.bulk_insert([_make_field(field_name="passport_number")])

    assert db.execute.call_count == 1
    sql_arg = str(db.execute.call_args[0][0])
    assert "INSERT INTO extracted_fields" in sql_arg
    assert ":uid_0" in sql_arg
    assert db.commit.call_count == 1


@pytest.mark.asyncio
async def test_multiple_fields_single_execute():
    """N fields produce exactly one execute call, not N."""
    db = _mock_db()
    repo = ExtractedFieldsRepo(db)
    user_id = uuid4()
    doc_id = uuid4()

    fields = [
        _make_field(user_id=user_id, document_id=doc_id, field_name="full_name"),
        _make_field(user_id=user_id, document_id=doc_id, field_name="dob"),
        _make_field(user_id=user_id, document_id=doc_id, field_name="passport_number"),
        _make_field(user_id=user_id, document_id=doc_id, field_name="nationality"),
        _make_field(user_id=user_id, document_id=doc_id, field_name="gender"),
    ]

    await repo.bulk_insert(fields)

    assert db.execute.call_count == 1, (
        f"Expected 1 execute call for 5 fields, got {db.execute.call_count}"
    )
    assert db.commit.call_count == 1


@pytest.mark.asyncio
async def test_sql_contains_multi_row_values():
    """SQL statement contains all N row placeholders."""
    db = _mock_db()
    repo = ExtractedFieldsRepo(db)
    user_id = uuid4()
    doc_id = uuid4()

    fields = [
        _make_field(user_id=user_id, document_id=doc_id, field_name="a"),
        _make_field(user_id=user_id, document_id=doc_id, field_name="b"),
        _make_field(user_id=user_id, document_id=doc_id, field_name="c"),
    ]

    await repo.bulk_insert(fields)

    sql_arg = str(db.execute.call_args[0][0])
    # Should have placeholders for all 3 rows
    for i in range(3):
        assert f":uid_{i}" in sql_arg
        assert f":fn_{i}" in sql_arg


@pytest.mark.asyncio
async def test_params_contain_all_field_values():
    """All field values are correctly passed as named params."""
    db = _mock_db()
    repo = ExtractedFieldsRepo(db)
    user_id = uuid4()
    doc_id = uuid4()

    fields = [
        _make_field(
            user_id=user_id,
            document_id=doc_id,
            field_name="passport_number",
            field_value="A1234567",
            field_type="identifier",
            confidence=0.95,
            is_entity_ref=False,
        ),
        _make_field(
            user_id=user_id,
            document_id=doc_id,
            field_name="full_name",
            field_value="Jane Doe",
            field_type="string",
            confidence=None,
            is_entity_ref=True,
        ),
    ]

    await repo.bulk_insert(fields)

    params = db.execute.call_args[0][1]
    assert params["fn_0"] == "passport_number"
    assert params["fv_0"] == "A1234567"
    assert params["ft_0"] == "identifier"
    assert params["c_0"] == 0.95
    assert params["ie_0"] is False
    assert params["fn_1"] == "full_name"
    assert params["fv_1"] == "Jane Doe"
    assert params["ie_1"] is True
    assert params["uid_0"] == str(user_id)
    assert params["did_0"] == str(doc_id)
