# backtest/dataset.py
import sqlite3
from collections import defaultdict
from pathlib import Path

HISTORY_DB = Path(__file__).parent / "history.db"


def load_finished_matches(min_date=None, league_code=None):
    conn = sqlite3.connect(HISTORY_DB)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM historical_matches WHERE status='FINISHED'"
    params = []
    if min_date:
        q += " AND kickoff >= ?"
        params.append(min_date)
    if league_code:
        q += " AND league_code = ?"
        params.append(league_code)
    q += " ORDER BY kickoff ASC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return rows


def build_team_history(matches):
    """{team: [{'date','gf','ga','is_home'}...]} trié par date."""
    hist = defaultdict(list)
    for m in matches:
        d = m["kickoff"]
        hist[m["home"]].append({
            "date": d, "gf": m["home_goals"], "ga": m["away_goals"],
            "is_home": True,
        })
        hist[m["away"]].append({
            "date": d, "gf": m["away_goals"], "ga": m["home_goals"],
            "is_home": False,
        })
    for k in hist:
        hist[k].sort(key=lambda x: x["date"])
    return hist


def stats_before(history, team, before_date, n=10):
    """Stats des n derniers matchs AVANT before_date (walk-forward, pas de leak)."""
    past = [h for h in history.get(team, []) if h["date"] < before_date][-n:]
    if not past:
        return None

    points = gf = ga = 0
    form_chars = []
    gf_home = ga_home = n_home = 0
    gf_away = ga_away = n_away = 0

    for h in past:
        gf += h["gf"]; ga += h["ga"]
        if h["gf"] > h["ga"]:
            points += 3; form_chars.append("W")
        elif h["gf"] == h["ga"]:
            points += 1; form_chars.append("D")
        else:
            form_chars.append("L")
        if h["is_home"]:
            gf_home += h["gf"]; ga_home += h["ga"]; n_home += 1
        else:
            gf_away += h["gf"]; ga_away += h["ga"]; n_away += 1

    return {
        "matches_played": len(past),
        "points": points,
        "goals_for": gf,
        "goals_against": ga,
        "goals_for_home": gf_home,
        "goals_against_home": ga_home,
        "goals_for_away": gf_away,
        "goals_against_away": ga_away,
        "n_home": n_home,
        "n_away": n_away,
        "form": "".join(form_chars[-5:]),
    }
