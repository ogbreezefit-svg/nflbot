"""Read-only dashboard presentation. No selection or settlement rules."""
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from weekly_stats import weekly_pick_summary

CHICAGO = ZoneInfo("America/Chicago")


def local_time(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CHICAGO)


def display_time(value):
    value = local_time(value)
    return value.strftime("%a %b %d, %I:%M %p %Z") if value else "Unknown"


def describe_pick(row):
    market = row.market_key
    side = row.pick_side or row.player_name or "Unknown selection"
    if market == "h2h":
        return f"{side} moneyline"
    if market == "spreads":
        line = row.picked_line
        return f"{side} {line:+g}" if line is not None else str(side)
    if market == "totals":
        return f"{side} {row.picked_line:g}" if row.picked_line is not None else str(side)
    return row.player_name or str(side)


def ticket_display(slip):
    publication_mode = getattr(slip, "publication_mode", None)
    is_trial = publication_mode == "TRIAL"
    is_monster = publication_mode == "MONSTER"
    approval_ref = getattr(slip, "publication_approval_ref", None)
    publication_approved = (
        is_monster
        and getattr(slip, "research_qualified", None) is True
        and getattr(slip, "prediction_approved", None) is True
        and getattr(slip, "publication_approved", None) is True
        and isinstance(approval_ref, str)
        and bool(approval_ref.strip())
    )

    def paper_money(field):
        value = getattr(slip, field, None)
        return f"${value:,.2f}" if value is not None else "—"

    try:
        labels = json.loads(slip.legs_json or "[]")
        if not isinstance(labels, list):
            labels = []
    except (TypeError, ValueError):
        labels = []

    # Hide the text-only game-script annotation, not an actual priced leg.
    labels = [
        label for label in labels
        if isinstance(label, str) and not label.startswith("Game Script:")
    ]

    return {
        "id": slip.id,
        "category": slip.category or "Ticket",
        "odds": slip.odds or "—",
        "stake": slip.stake or "—",
        "payout": slip.payout or "—",
        "legs": labels,
        "display_status": slip.status or "UNKNOWN",
        "is_trial": is_trial,
        "is_monster": is_monster,
        "publication_approved": publication_approved,
        "outcome": (
            getattr(slip, "outcome", None) or "UNTRACKED"
            if is_trial or is_monster else "UNTRACKED"
        ),
        "research_label": (
            "Trial · Not validated · Simulated"
            if is_trial else (
                "Monster · Recorded research and publication approval"
                if publication_approved else (
                    "Monster · Not approved for publication"
                    if is_monster else "Not research-qualified"
                )
            )
        ),
        "paper_return": paper_money("paper_return") if is_trial else "—",
        "paper_profit": paper_money("paper_profit") if is_trial else "—",
        "created": display_time(slip.created_at),
    }


def build_dashboard_context(picks, slips, now=None):
    now = local_time(now or datetime.now(timezone.utc))
    monday = now.date() - timedelta(days=now.weekday())
    next_monday = monday + timedelta(days=7)

    # Use identifiable engine records; don't reclassify old anonymous rows.
    managed = [
        row for row in picks
        if str(row.pick_key or "").startswith("oddsapi|")
        and row.event_id
        and row.market_key in ("h2h", "spreads", "totals")
    ]

    dated = [
        row for row in managed
        if row.kickoff_time is not None
        and monday <= local_time(row.kickoff_time).date() < next_monday
    ]

    # Deduplicate display records by the engine's selection key.
    unique = {}
    for row in dated:
        previous = unique.get(row.pick_key)
        if previous is None or row.id > previous.id:
            unique[row.pick_key] = row
    this_week = list(unique.values())

    straight_rows = sorted(
        [
            row for row in this_week
            if row.is_shadow and row.market_key == "h2h"
        ],
        key=lambda row: (local_time(row.kickoff_time), row.id),
    )

    straights = [
        {
            "game": row.market_name or "Unknown matchup",
            "pick": describe_pick(row),
            "odds": (
                f"{row.picked_odds:+g}"
                if row.picked_odds is not None else "—"
            ),
            "kickoff": display_time(row.kickoff_time),
            "status": row.status or "UNKNOWN",
        }
        for row in straight_rows
    ]

    counts = {
        status: sum(row.status == status for row in this_week)
        for status in ("WON", "LOST", "PUSH", "ACTIVE")
    }
    decisions = counts["WON"] + counts["LOST"]
    review_count = sum(
        row.status in ("REVIEW_REQUIRED", "UNRESOLVED", "QUARANTINED")
        for row in this_week
    )

    games = {}
    for row in sorted(
        dated, key=lambda item: (local_time(item.kickoff_time), item.id)
    ):
        games[row.event_id] = {
            "game": row.market_name or "Unknown matchup",
            "kickoff": display_time(row.kickoff_time),
        }

    ordered_slips = sorted(slips, key=lambda slip: slip.id, reverse=True)
    active = [
        ticket_display(slip)
        for slip in ordered_slips
        if slip.status == "ACTIVE"
    ]
    order = {"Standard Cap": 0, "Booster Matrix": 1, "Bomb Target": 2}
    active.sort(key=lambda ticket: order.get(ticket["category"], 99))

    undated = sum(row.kickoff_time is None for row in picks)
    return {
        "week_label": (
            f"{monday:%b %d} – "
            f"{monday + timedelta(days=6):%b %d, %Y}"
        ),
        "straight_count": len(straights),
        "pending_selections": counts["ACTIVE"],
        "record": f"{counts['WON']}–{counts['LOST']}–{counts['PUSH']}",
        "win_rate": f"{counts['WON'] / decisions * 100:.1f}%" if decisions else "—",
        "review_count": review_count,
        "straight_preview": straights[:6],
        "straight_more": straights[6:],
        "games": list(games.values()),
        "active_tickets": [
            ticket for ticket in active
            if ticket["category"] != "Micro Sandbox"
        ],
        "micro_tickets": [
            ticket for ticket in active
            if ticket["category"] == "Micro Sandbox"
        ],
        "ticket_history": [
            ticket_display(slip) for slip in ordered_slips[:50]
        ],
        "weekly_summary": weekly_pick_summary(managed, now=now),
        "undated": undated,
        "timestamp": now.strftime("%Y-%m-%d %I:%M:%S %p %Z"),
    }
