# backtest/collect_history.py
"""
Collecte un historique de matchs terminés via football-data.org.
Stocke dans backtest/history.db (table historical_matches).
Usage : python -m backtest.collect_history [--seasons 2024 2025]
"""
import argparse
import asyncio
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_KEY")
if not API_KEY:
    raise SystemExit("FOOTBALL_DATA_KEY non définie dans .env ou variable d'env")

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}

HISTORY_DB = Path(__file__).parent / "history.db"

LEAGUES = {
    "PL": "Premier League",
    "PD": "La Liga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
}


def init_historical_db():
    HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HISTORY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_matches (
            id INTEGER PRIMARY KEY,
            league_code TEXT NOT NULL,
            league_name TEXT,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            ht_home_goals INTEGER,
            ht_away_goals INTEGER,
            kickoff TEXT NOT NULL,
            status TEXT DEFAULT 'FINISHED'
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hist_date ON historical_matches(kickoff)"
    )
    conn.commit()
    conn.close()


def store_matches(matches, code, league_name):
    conn = sqlite3.connect(HISTORY_DB)
    inserted = 0
    for m in matches:
        try:
            if m.get("status") not in ("FINISHED", "AWARDED"):
                continue
            score = m.get("score", {}).get("fullTime", {})
            if score.get("home") is None or score.get("away") is None:
                continue
            ht = m.get("score", {}).get("halfTime", {}) or {}
            conn.execute("""
                INSERT OR REPLACE INTO historical_matches
                (id, league_code, league_name, home, away,
                 home_goals, away_goals, ht_home_goals, ht_away_goals,
                 kickoff, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'FINISHED')
            """, (
                m["id"], code, league_name,
                m["homeTeam"]["name"], m["awayTeam"]["name"],
                score["home"], score["away"],
                ht.get("home"), ht.get("away"),
                m["utcDate"],
            ))
            inserted += 1
        except Exception as e:
            print(f"  Erreur store {m.get('id')}: {e}")
    conn.commit()
    conn.close()
    return inserted


async def fetch_month(code, d_from, d_to):
    url = f"{BASE_URL}/competitions/{code}/matches"
    params = {"dateFrom": d_from.isoformat(), "dateTo": d_to.isoformat()}
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url, headers=HEADERS, params=params)
            if r.status_code == 200:
                return r.json().get("matches", [])
            if r.status_code == 429:
                print(f"  Rate limit, attente 60s (tentative {attempt+1}/3)")
                await asyncio.sleep(60)
                continue
            print(f"  Erreur HTTP {r.status_code} sur {code} {d_from}")
            return []
        except Exception as e:
            print(f"  Exception {code} {d_from}: {e}")
            await asyncio.sleep(10)
    return []


async def collect_league(code, season_start_year):
    league_name = LEAGUES[code]
    season_end_year = season_start_year + 1
    start = date(season_start_year, 7, 1)
    end = date(season_end_year, 6, 30)

    print(f"\n=== {code} saison {season_start_year}-{season_end_year} ===")
    total = 0
    current = start
    while current < end:
        nxt = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
        month_end = min(nxt - timedelta(days=1), end)
        matches = await fetch_month(code, current, month_end)
        n = store_matches(matches, code, league_name) if matches else 0
        total += n
        print(f"  {current} → {month_end}: {len(matches)} reçus, {n} stockés")
        await asyncio.sleep(6.5)  # respect 10 req/min
        current = nxt
    print(f"=== {code} {season_start_year}: {total} matchs stockés au total ===")
    return total


async def main(seasons):
    init_historical_db()
    grand_total = 0
    for season in seasons:
        for code in LEAGUES:
            grand_total += await collect_league(code, season)
    conn = sqlite3.connect(HISTORY_DB)
    n_total = conn.execute("SELECT COUNT(*) FROM historical_matches").fetchone()[0]
    conn.close()
    print(f"\n✅ Terminé. {grand_total} matchs ajoutés cette session.")
    print(f"   Total en base : {n_total} matchs ({HISTORY_DB})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons", type=int, nargs="+", default=[2024, 2025],
        help="Années de début des saisons à collecter (ex: 2023 2024 2025)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.seasons))
