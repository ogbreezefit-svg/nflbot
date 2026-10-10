import pytest
from datetime import datetime, timedelta, timezone
from validator import validate_pick
from settlement import Tank01SettlementEngine

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def mock_sleeper_roster():
    """Simulates Sleeper API roster data."""
    return {
        "101": {
            "first_name": "Davante",
            "last_name": "Adams",
            "status": "Active",
            "injury_status": None
        },
        "102": {
            "first_name": "Christian",
            "last_name": "McCaffrey",
            "status": "Active",
            "injury_status": "Out"
        },
        "103": {
            "first_name": "Tua",
            "last_name": "Tagovailoa",
            "status": "Inactive",
            "injury_status": "IR"
        }
    }

@pytest.fixture
def settlement_engine():
    """Instantiates the Tank01 Settlement Engine."""
    return Tank01SettlementEngine()


# ------------------------------------------------------------------
# Gatekeeper Validator Tests
# ------------------------------------------------------------------

def test_validator_passes_valid_pick(mock_sleeper_roster):
    valid_pick = {
        "player_name": "Davante Adams",
        "kickoff_time": datetime.now(timezone.utc) + timedelta(days=2),
        "players": ["Davante Adams"],
        "market": "player_pass_tds",
        "pick_side": "OVER",
        "line": 0.5
    }
    passed, reason = validate_pick(valid_pick, mock_sleeper_roster)
    assert passed is True
    assert reason == "PASSED"


def test_validator_fails_out_of_window_kickoff(mock_sleeper_roster):
    far_future_pick = {
        "player_name": "Davante Adams",
        "kickoff_time": datetime.now(timezone.utc) + timedelta(days=10),
        "players": ["Davante Adams"]
    }
    passed, reason = validate_pick(far_future_pick, mock_sleeper_roster)
    assert passed is False
    assert "Time Horizon Violation" in reason


def test_validator_quarantines_injured_player(mock_sleeper_roster):
    injured_pick = {
        "player_name": "Christian McCaffrey",
        "kickoff_time": datetime.now(timezone.utc) + timedelta(days=1),
        "players": ["Christian McCaffrey"]
    }
    passed, reason = validate_pick(injured_pick, mock_sleeper_roster)
    assert passed is False
    assert "Injury Check Failed" in reason


def test_validator_quarantines_contradictory_parlay(mock_sleeper_roster):
    contradictory_parlay = {
        "kickoff_time": datetime.now(timezone.utc) + timedelta(days=1),
        "players": [],
        "legs": [
            {"market": "totals", "pick_side": "UNDER", "line": 38.5},
            {"market": "player_pass_tds", "pick_side": "OVER", "line": 2.5}
        ]
    }
    passed, reason = validate_pick(contradictory_parlay, mock_sleeper_roster)
    assert passed is False
    assert "Math Check Failed" in reason


# ------------------------------------------------------------------
# Settlement Engine Tests
# ------------------------------------------------------------------

def test_settlement_grade_player_prop_over_win(settlement_engine):
    player_stats = {"Passing": {"passYds": "285.0"}}
    outcome = settlement_engine.grade_player_prop(
        market="player_pass_yds",
        line=250.5,
        side="OVER",
        player_stats=player_stats
    )
    assert outcome == "WON"


def test_settlement_grade_player_prop_under_loss(settlement_engine):
    player_stats = {"Rushing": {"rushYds": "82.0"}}
    outcome = settlement_engine.grade_player_prop(
        market="player_rush_yds",
        line=65.5,
        side="UNDER",
        player_stats=player_stats
    )
    assert outcome == "LOST"


def test_settlement_grade_game_total_over(settlement_engine):
    outcome = settlement_engine.grade_total_or_spread(
        market="totals",
        side="OVER",
        line=45.5,
        home_score=27,
        away_score=24,
        is_home=True
    )
    assert outcome == "WON"


def test_settlement_grade_spread_cover(settlement_engine):
    # Home team favored by -3.5 (line = -3.5). Final score: Home 24, Away 20 -> 24 - 3.5 = 20.5 > 20
    outcome = settlement_engine.grade_total_or_spread(
        market="spreads",
        side="HOME_TEAM",
        line=-3.5,
        home_score=24,
        away_score=20,
        is_home=True
    )
    assert outcome == "WON"