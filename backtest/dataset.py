import sqlite3
from datetime import datetime
from collections import defaultdict

DB_PATH = "/tmp/sportia.db"  # à ajuster si tu changes

def load_finished_matches(min_date=None, league=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    q = """
        SELECT id, home_team, away_team, home_goals, away_goals,
               league, kickoff, home_xg, away_xg
        FROM matches
        WHERE status = 'FIN'
          AND home_goals IS NOT NULL
          AND away_goals IS NOT NULL
    """
    params = []
    if min_date:
        q += " AND kickoff >= ?"
        params.append(min_date)
    if league:
        q += " AND league = ?"
        params.append(league)
    q += " ORDER BY kickoff ASC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return rows

def build_team_history(matches):
    """
    Retourne {team_name: [ {date, gf, ga, is_home, league}, ... ]} trié par date.
    Sert à calculer des stats 'avant' un match donné (pas de leak).
    """
    hist = defaultdict(list)
    for m in matches:
        d = m['kickoff']
        hist[m['home_team']].append({'date': d, 'gf': m['home_goals'],
                                     'ga': m['away_goals'], 'is_home': True,
                                     'league': m['league']})
        hist[m['away_team']].append({'date': d, 'gf': m['away_goals'],
                                     'ga': m['home_goals'], 'is_home': False,
                                     'league': m['league']})
    for k in hist:
        hist[k].sort(key=lambda x: x['date'])
    return hist

def stats_before(history, team, before_date, n=10):
    """Stats des n derniers matchs de team avant before_date."""
    past = [h for h in history.get(team, []) if h['date'] < before_date]
    past = past[-n:]
    if not past:
        return None
    return {
        'n': len(past),
        'gf_avg': sum(h['gf'] for h in past) / len(past),
        'ga_avg': sum(h['ga'] for h in past) / len(past),
        'home_gf_avg': (sum(h['gf'] for h in past if h['is_home']) /
                        max(1, sum(1 for h in past if h['is_home']))),
        'away_gf_avg': (sum(h['gf'] for h in past if not h['is_home']) /
                        max(1, sum(1 for h in past if not h['is_home']))),
    }
