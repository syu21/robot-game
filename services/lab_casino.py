from services.lab_casino_service import (
    LAB_CASINO_BET_AMOUNTS,
    LAB_CASINO_COIN_CAP,
    LAB_CASINO_CONDITIONS,
    LAB_CASINO_DAILY_GRANT,
    LAB_CASINO_ODDS_MAX,
    LAB_CASINO_ODDS_MIN,
    LAB_CASINO_ROLE_LABELS,
    LAB_CASINO_STARTING_COINS,
    LAB_CASINO_WATCH_BONUS,
    build_casino_entries,
    payout_amount,
)
from services.lab_race_course import course_meta
from services.lab_race_engine import build_course, simulate_mode_race


LAB_CASINO_ENTRY_TARGET = 6
LAB_CASINO_COURSE = course_meta("casino_scrapyard_cup", mode="casino")


def simulate_casino_race(entries, seed, course=None):
    resolved_course = course if isinstance(course, dict) else build_course(seed, mode="casino", course_key="casino_scrapyard_cup")
    return simulate_mode_race(entries, seed, resolved_course, mode="casino")
