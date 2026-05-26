"""Regression test for D-RETRY-01: retry_count increments on first verifier pass.

Verifies that:
- update_verification does NOT touch retry_count (verification != retry)
- retry_count only increments when the extractor actually re-runs for a field
"""

import re

import pytest

from app.repositories.extracted_fields_repo import ExtractedFieldsRepo


def test_update_verification_sql_does_not_increment_retry_count():
    """The UPDATE in update_verification must not modify retry_count.

    D-RETRY-01: Previously, retry_count was incremented inside
    update_verification whenever needs_retry was True, meaning the
    count went up before any retry actually happened.
    """
    import inspect
    source = inspect.getsource(ExtractedFieldsRepo.update_verification)

    # The SQL should NOT contain any retry_count assignment
    assert "retry_count" not in source, (
        "update_verification still modifies retry_count — "
        "it should only be incremented in the orchestrator's retry path (D-RETRY-01)"
    )


def test_orchestrator_retry_path_increments_retry_count():
    """The orchestrator's retry UPDATE must increment retry_count.

    Reads source file directly to avoid importing heavy dependencies
    (supabase, etc.) that aren't installed in the test environment.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "app" / "services" / "pipeline" / "orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "retry_count = retry_count + 1" in src, (
        "Orchestrator retry path does not increment retry_count (D-RETRY-01)"
    )
