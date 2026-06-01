"""
Backfill name_metaphone for all existing entities that have NULL name_metaphone.

Usage:
    python -m app.scripts.backfill_metaphone [--batch-size N] [--dry-run]
"""
import argparse
import asyncio

from metaphone import doublemetaphone
from sqlalchemy import text

from app.db.session import async_session_factory


async def backfill(batch_size: int, dry_run: bool) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            text("SELECT id, canonical_name FROM entities WHERE name_metaphone IS NULL ORDER BY id")
        )
        rows = result.fetchall()

        total = len(rows)
        updated = 0

        print(f"Found {total} entities with NULL name_metaphone.")

        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                entity_id, canonical_name = row[0], row[1]
                primary, _ = doublemetaphone(canonical_name or "")
                metaphone_code = primary or None
                if not metaphone_code:
                    continue
                if dry_run:
                    print(f"  [dry-run] {entity_id} ({canonical_name!r}) → {metaphone_code!r}")
                else:
                    await db.execute(
                        text("UPDATE entities SET name_metaphone = :m WHERE id = :id"),
                        {"m": metaphone_code, "id": str(entity_id)},
                    )
                updated += 1

            if not dry_run:
                await db.commit()
                print(f"  Committed batch {i // batch_size + 1} ({len(batch)} rows).")

    if dry_run:
        print(f"[dry-run] Would update {updated}/{total} entities.")
    else:
        print(f"Done. Updated {updated}/{total} entities.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill name_metaphone for entities.")
    parser.add_argument("--batch-size", type=int, default=100, help="Rows per DB commit (default: 100)")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    args = parser.parse_args()

    asyncio.run(backfill(args.batch_size, args.dry_run))


if __name__ == "__main__":
    main()
