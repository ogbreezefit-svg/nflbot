"""Read-only database evaluation. Never calls APIs or enables parlays."""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from moneyline_evaluation import (
    FEATURE_FIELDS,
    select_observations,
    validate_selected,
    probability_metrics,
)


def database_time(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def run(args):
    # Load configuration before importing database modules.
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except ImportError:
        pass

    from db import SessionLocal, PickLog
    from moneyline_observations import MoneylineResearchObservation
    from sqlalchemy.exc import SQLAlchemyError

    now = datetime.now(timezone.utc)
    rows = []
    rejected_events = Counter()

    try:
        with SessionLocal() as session:
            dialect = session.get_bind().dialect.name

            # Read lightweight metadata first, not every frozen report.
            observations = session.query(
                MoneylineResearchObservation.observation_key,
                MoneylineResearchObservation.event_id,
                MoneylineResearchObservation.captured_at,
                MoneylineResearchObservation.home_pick_key,
            ).all()

            keys = sorted({item.home_pick_key for item in observations})
            picks_by_key = {}

            for start in range(0, len(keys), 500):
                picks = session.query(PickLog).filter(
                    PickLog.pick_key.in_(keys[start:start + 500])
                ).all()
                for pick in picks:
                    picks_by_key.setdefault(pick.pick_key, []).append(pick)

            records = []
            for item in observations:
                matches = picks_by_key.get(item.home_pick_key, [])
                pick = matches[0] if len(matches) == 1 else None
                records.append({
                    "observation_key": item.observation_key,
                    "event_id": item.event_id,
                    "captured_at": database_time(item.captured_at),
                    "home_pick_key": item.home_pick_key,
                    "pick_matches": len(matches),
                    "pick": None if pick is None else {
                        "pick_key": pick.pick_key,
                        "event_id": pick.event_id,
                        "market_key": pick.market_key,
                        "pick_side": pick.pick_side,
                        "status": pick.status,
                        "kickoff_time": database_time(pick.kickoff_time),
                        "settled_at": database_time(pick.settled_at),
                    },
                })

            selected, exclusions = select_observations(
                records,
                now,
                args.min_lead_hours,
                args.max_lead_hours,
            )

            # Fetch only the one chosen frozen report per event.
            for record in selected:
                observation = session.get(
                    MoneylineResearchObservation,
                    record["observation_key"],
                )
                try:
                    evidence = json.loads(observation.evidence_json)
                    rows.append(validate_selected(
                        record,
                        evidence,
                        args.max_quote_age_minutes,
                    ))
                except (ValueError, TypeError, AttributeError, KeyError) as exc:
                    reason = (
                        str(exc) if isinstance(exc, ValueError)
                        else "INVALID_SELECTED_EVIDENCE"
                    )
                    rejected_events[reason] += 1

    except SQLAlchemyError:
        print(
            "Database read failed. Check the configured database and whether "
            "the observation table has been deployed. "
            "No initialization or migration was attempted."
        )
        return 2

    baseline = probability_metrics(
        [row["home_won"] for row in rows],
        [row["baseline_home_share"] for row in rows],
    )

    report = {
        "generated_at": now.isoformat(),
        "database_dialect": dialect,
        "observation_records_read": len(records),
        "distinct_events_observed": len({
            record["event_id"] for record in records
        }),
        "events_selected_before_integrity_checks": len(selected),
        "eligible_settled_events": len(rows),
        **exclusions,
        "excluded_selected_events_by_reason": dict(rejected_events),
        "policy": {
            "min_lead_hours": args.min_lead_hours,
            "max_lead_hours": args.max_lead_hours,
            "max_quote_age_minutes": args.max_quote_age_minutes,
            "one_observation_per_event": True,
            "fallback_to_older_observation_on_integrity_failure": False,
        },
        "bookmaker_distribution": dict(Counter(
            row["bookmaker_key"] for row in rows
        )),
        "market_baseline_metrics": baseline,
        "research_model_status": "NOT_FITTED",
        "research_model_metrics": None,
        "production_approval": False,
        "automatic_parlays_enabled_by_this_tool": False,
        "notes": [
            "Market shares are a baseline, not research-model predictions.",
            "Metrics are descriptive; they do not establish profitability.",
            "Research model training is not implemented in this tool.",
            "Player/news predictors are extracted from frozen evidence; "
            "their presence does not establish predictive value.",
            "The configured database may differ from the deployed database.",
        ],
    }

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S_%f")

    fields = [
        "event_id", "observation_key", "home_pick_key",
        "captured_at", "odds_observed_at", "market_last_update",
        "kickoff_time", "settled_at", "actual_lead_hours",
        "home", "away", "bookmaker_key", "home_odds", "away_odds",
        "baseline_home_share", "home_won", "feature_version",
        *FEATURE_FIELDS,
    ]

    with (output / f"moneyline_dataset_{stamp}.csv").open(
        "w", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    (output / f"moneyline_evaluation_{stamp}.json").write_text(
        json.dumps(report, indent=2, allow_nan=False)
    )

    print(json.dumps(report, indent=2, allow_nan=False))
    print("\nCSV dataset and JSON summary written.")
    print("No database writes, API calls, training, or ticket creation.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", default="local_backups/evaluation"
    )
    parser.add_argument("--min-lead-hours", type=float, default=1)
    parser.add_argument("--max-lead-hours", type=float, default=24)
    parser.add_argument("--max-quote-age-minutes", type=float, default=60)
    args = parser.parse_args()

    import math
    values = (
        args.min_lead_hours,
        args.max_lead_hours,
        args.max_quote_age_minutes,
    )
    if (
        not all(math.isfinite(value) for value in values)
        or not 0 < args.min_lead_hours < args.max_lead_hours
        or args.max_quote_age_minutes <= 0
    ):
        parser.error("Invalid finite positive evaluation thresholds")

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
