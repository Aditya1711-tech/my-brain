#!/usr/bin/env python3
"""Phase 1.5 benchmark script.

Queries pipeline event durations from the database and prints a
comparison table for baseline and optimization tracking.

Usage:
    DATABASE_URL=postgresql://... python scripts/bench_phase_1_5.py
    DATABASE_URL=postgresql://... python scripts/bench_phase_1_5.py --user-id <uuid>
    DATABASE_URL=postgresql://... python scripts/bench_phase_1_5.py --last 10
"""

import argparse
import asyncio
import os
import statistics
from collections import defaultdict
from uuid import UUID

import asyncpg

STAGES_ORDER = [
    "text_extraction",
    "classification",
    "schema_building",
    "extraction",
    "verification",
    "integration",
    "vectorization",
]


async def connect(database_url: str) -> asyncpg.Connection:
    """Connect to PostgreSQL, accepting both SQLAlchemy and plain URLs.

    Handles passwords with special characters (?, *, @) by manually
    extracting and percent-encoding the password before urlparse sees it.
    """
    from urllib.parse import quote

    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    scheme, rest = url.split("://", 1)          # rest = "user:pass@host:port/db"
    at_pos = rest.rfind("@")                     # last @ separates userinfo from host
    userinfo, hostdb = rest[:at_pos], rest[at_pos + 1:]
    colon_pos = userinfo.find(":")               # first : separates user from password
    user = userinfo[:colon_pos]
    password = userinfo[colon_pos + 1:]
    encoded = f"{scheme}://{user}:{quote(password, safe='')}@{hostdb}"
    return await asyncpg.connect(encoded)


async def fetch_pipeline_stats(
    conn: asyncpg.Connection,
    user_id: UUID | None = None,
    last_n: int | None = None,
) -> list[asyncpg.Record]:
    """Fetch per-doc, per-stage durations for completed documents."""
    doc_filter = "WHERE d.status = 'vectorized'"
    params: list = []
    idx = 1

    if user_id:
        doc_filter += f" AND d.user_id = ${idx}"
        params.append(user_id)
        idx += 1

    limit_clause = ""
    if last_n:
        limit_clause = f" LIMIT ${idx}"
        params.append(last_n)

    query = f"""
        WITH target_docs AS (
            SELECT id, original_filename, doc_type
            FROM documents d
            {doc_filter}
            ORDER BY d.created_at DESC
            {limit_clause}
        )
        SELECT
            e.document_id,
            td.original_filename,
            td.doc_type,
            e.stage,
            e.status,
            e.duration_ms,
            e.details,
            e.created_at
        FROM document_pipeline_events e
        JOIN target_docs td ON td.id = e.document_id
        ORDER BY e.document_id, e.created_at
    """
    return await conn.fetch(query, *params)


def compute_stats(
    rows: list[asyncpg.Record],
) -> tuple[dict[str, list[int]], list[int], list[dict]]:
    """Compute per-stage and per-document statistics."""
    by_doc: dict = defaultdict(list)
    for row in rows:
        by_doc[row["document_id"]].append(row)

    stage_durations: dict[str, list[int]] = defaultdict(list)
    doc_totals: list[int] = []
    doc_details: list[dict] = []

    for _doc_id, events in by_doc.items():
        ok = [e for e in events if e["status"] == "success"]
        if not ok:
            continue

        total_ms = sum(e["duration_ms"] or 0 for e in ok)
        doc_totals.append(total_ms)

        # Wall-clock: first event start to last event end
        timestamps = [e["created_at"] for e in events]
        wall_ms = (
            int((max(timestamps) - min(timestamps)).total_seconds() * 1000)
            if len(timestamps) > 1
            else total_ms
        )

        info: dict = {
            "filename": events[0]["original_filename"],
            "doc_type": events[0]["doc_type"] or "unknown",
            "total_ms": total_ms,
            "wall_clock_ms": wall_ms,
            "stages": {},
        }

        for e in ok:
            dur = e["duration_ms"] or 0
            stage_durations[e["stage"]].append(dur)
            info["stages"][e["stage"]] = dur

        doc_details.append(info)

    return stage_durations, doc_totals, doc_details


def pct(data: list[int | float], p: float) -> float:
    """Compute percentile (linear interpolation)."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def fmt(ms: float) -> str:
    """Format milliseconds for display."""
    if ms < 1000:
        return f"{int(ms)} ms"
    return f"{ms / 1000:.1f} s"


def print_report(
    stage_durations: dict[str, list[int]],
    doc_totals: list[int],
    doc_details: list[dict],
) -> None:
    """Print markdown benchmark report to stdout."""
    n = len(doc_details)
    print(f"\n## Pipeline Benchmark Results  ({n} documents)\n")

    # ---- per-document breakdown ----
    print("### Per-document breakdown\n")
    stage_hdrs = [s.replace("_", " ").title()[:12] for s in STAGES_ORDER]
    print(
        "| Document | Type | Sum (ms) | Wall (ms) | "
        + " | ".join(stage_hdrs)
        + " |"
    )
    print(
        "|----------|------|----------|-----------|"
        + "".join(" --- |" for _ in STAGES_ORDER)
    )
    for d in doc_details:
        cols = " | ".join(
            fmt(d["stages"].get(s, 0)) for s in STAGES_ORDER
        )
        print(
            f"| {d['filename'][:28]:<28} "
            f"| {d['doc_type'][:10]:<10} "
            f"| {fmt(d['total_ms']):>8} "
            f"| {fmt(d['wall_clock_ms']):>9} "
            f"| {cols} |"
        )

    # ---- aggregate stats ----
    print("\n### Aggregate statistics\n")
    print("| Metric | p50 | p95 | Mean |")
    print("|--------|-----|-----|------|")

    if doc_totals:
        print(
            f"| **Pipeline total (sum)** "
            f"| {fmt(pct(doc_totals, 50))} "
            f"| {fmt(pct(doc_totals, 95))} "
            f"| {fmt(statistics.mean(doc_totals))} |"
        )

    for stage in STAGES_ORDER:
        durs = stage_durations.get(stage, [])
        if not durs:
            continue
        label = stage.replace("_", " ").title()
        print(
            f"| {label} "
            f"| {fmt(pct(durs, 50))} "
            f"| {fmt(pct(durs, 95))} "
            f"| {fmt(statistics.mean(durs))} |"
        )

    print()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1.5 pipeline benchmark"
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Filter to a specific user UUID",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Limit to the N most recently created documents",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: Set DATABASE_URL environment variable.")
        print("  Example: DATABASE_URL=postgresql://user:pass@host:5432/db")
        raise SystemExit(1)

    conn = await connect(database_url)
    try:
        uid = UUID(args.user_id) if args.user_id else None
        rows = await fetch_pipeline_stats(conn, user_id=uid, last_n=args.last)

        if not rows:
            print("No completed documents found. Process some documents first.")
            raise SystemExit(0)

        stage_durations, doc_totals, doc_details = compute_stats(rows)
        print_report(stage_durations, doc_totals, doc_details)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
