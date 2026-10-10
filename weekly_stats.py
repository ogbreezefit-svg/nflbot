"""Dashboard calculations only: no API calls, writes, or settlement."""
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")


def shadow_roi(rows):
    stake_total = Decimal("0")
    profit_total = Decimal("0")

    for row in rows:
        if not row.is_shadow or row.market_key != "h2h":
            continue
        if row.status not in ("WON", "LOST", "PUSH"):
            continue
        if row.realized_profit is None or row.stake is None:
            continue

        try:
            stake = Decimal(str(row.stake))
            profit = Decimal(str(row.realized_profit))
        except (InvalidOperation, ValueError, TypeError):
            continue

        if not stake.is_finite() or not profit.is_finite() or stake <= 0:
            continue

        stake_total += stake
        profit_total += profit

    if not stake_total:
        return "N/A (no settled picks)"

    return f"{profit_total / stake_total * 100:+.2f}%"


def weekly_pick_summary(rows, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    today = now.astimezone(CHICAGO).date()
    current_week = today - timedelta(days=today.weekday())
    groups = {current_week: Counter()}
    undated = 0

    for row in rows:
        kickoff = row.kickoff_time
        if kickoff is None:
            undated += 1
            continue

        # SQLite may return naive timestamps; this app stores UTC.
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)

        game_date = kickoff.astimezone(CHICAGO).date()
        monday = game_date - timedelta(days=game_date.weekday())
        counts = groups.setdefault(monday, Counter())
        status = str(row.status or "").upper()

        counts["total"] += 1

        if status == "WON":
            counts["wins"] += 1
        elif status == "LOST":
            counts["losses"] += 1
        elif status == "PUSH":
            counts["pushes"] += 1
        elif status == "ACTIVE":
            counts["pending"] += 1
        elif status in ("REVIEW_REQUIRED", "UNRESOLVED", "QUARANTINED"):
            counts["review"] += 1
        else:
            counts["other"] += 1

    weeks = []
    for monday in sorted(groups, reverse=True):
        counts = groups[monday]
        decisions = counts["wins"] + counts["losses"]
        weeks.append({
            "label": (
                f"{monday:%b %d, %Y} – "
                f"{monday + timedelta(days=6):%b %d, %Y}"
            ),
            "current": monday == current_week,
            "wins": counts["wins"],
            "losses": counts["losses"],
            "pushes": counts["pushes"],
            "pending": counts["pending"],
            "review": counts["review"],
            "other": counts["other"],
            "total": counts["total"],
            "win_rate": (
                f"{counts['wins'] / decisions * 100:.1f}%"
                if decisions else "—"
            ),
        })

    return {"weeks": weeks, "undated": undated}
