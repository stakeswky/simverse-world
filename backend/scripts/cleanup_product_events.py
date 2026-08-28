#!/usr/bin/env python3
"""Remove expired first-party Product Events; dry-run unless ``--apply``.

Run from ``backend/``::

    python3 scripts/cleanup_product_events.py --retention-days 90
    python3 scripts/cleanup_product_events.py --retention-days 90 --apply

The report intentionally contains counts and the UTC cutoff only.  It never
prints user IDs, session IDs, event properties, or event payloads.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, func, select  # noqa: E402

from app.models.product_event import ProductEvent  # noqa: E402


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso_z(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


async def cleanup_product_events(
    db,
    *,
    retention_days: int = 90,
    apply: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    """Report or delete rows whose ``created_at`` is strictly before cutoff."""

    if not 1 <= retention_days <= 365:
        raise ValueError("retention_days must be between 1 and 365")

    cutoff = _utc(now or datetime.now(UTC)) - timedelta(days=retention_days)
    criterion = ProductEvent.created_at < cutoff
    candidates = int((await db.execute(
        select(func.count()).select_from(ProductEvent).where(criterion)
    )).scalar() or 0)

    deleted = 0
    if apply and candidates:
        result = await db.execute(delete(ProductEvent).where(criterion))
        await db.commit()
        rowcount = getattr(result, "rowcount", None)
        deleted = candidates if rowcount is None or rowcount < 0 else int(rowcount)

    return {
        "mode": "apply" if apply else "dry-run",
        "cutoff": _iso_z(cutoff),
        "candidates": candidates,
        "deleted": deleted,
    }


async def _run(*, retention_days: int, apply: bool) -> dict[str, object]:
    from app.database import async_session

    async with async_session() as db:
        return await cleanup_product_events(
            db,
            retention_days=retention_days,
            apply=apply,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Report or remove Product Events older than the retention window."
    )
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete matching rows; without this flag the command is read-only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicitly select the default read-only mode",
    )
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    if not 1 <= args.retention_days <= 365:
        parser.error("--retention-days must be between 1 and 365")

    report = asyncio.run(_run(
        retention_days=args.retention_days,
        apply=args.apply,
    ))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
