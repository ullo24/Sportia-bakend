import os
import sqlite3
import asyncio
import httpx
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_KEY")
if not API_KEY:
    print("ATTENTION : FOOTBALL_DATA_KEY n'est pas definie !")

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY or ""}
DB_PATH = "/tmp/sportia.db"

# Competitions disponibles sur le plan gratuit
COMPETITIONS = {
    "PL": "Premier League",
    "PD": "La Liga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "DED": "Eredivisie",
    "PPL": "Primeira Liga",
    "CL": "Champions League",
    "EC": "European Championship",
    "WC": "World Cup",
}

# Nombre de jours de predictions en avance
DAYS_AHEAD = 7


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            league TEXT,
            country TEXT,
            home TEXT,
            away TEXT,
            kickoff TEXT,
            status TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_win REAL,
            draw REAL,
            away_win REAL,
            confidence REAL,
            updated_at TEXT
        )
        """
    )
    c.execute("CREATE TABLE IF NOT EXISTS api_log (day TEXT PRIMARY KEY, count INTEGER)")
    conn.commit()
    conn.close()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def increment_count():
    today = date.today().isoformat()
    conn = db()
    conn.execute(
        """
        INSERT INTO api_log (day, count) VALUES (?, 1)
        ON CONFLICT(day) DO UPDATE SET count = count + 1
        """,
        (today,),
    )
    conn.commit()
    conn.close()


def get_today_count() -> int:
    today = date.today().isoformat()
    conn = db()
    row = conn.execute("SELECT count FROM api_log WHERE day=?", (today,)).fetchone()
    conn.close()
    return row["count"] if row else 0


def predict(home_rank: int = 0, away_rank: int = 0, home_pts: int = 0, away_pts: int = 0):
    """
    Modele IA simple base sur le classement et les points.
    A remplacer plus tard par un vrai modele XGBoost.
    """
    if home_rank == 0 and away_rank == 0:
        return 0.40, 0.28, 0.32, 0.3

    home_strength = (1 / max(home_rank, 1)) + (home_pts / 100)
    away_strength = (1 / max(away_rank, 1)) + (away_pts / 100)
    home_strength *= 1.15  # avantage domicile

    total = home_strength + away_strength + 0.30
    hw = round(home_strength / total, 3)
    d = round(0.30 / total, 3)
    aw = round(away_strength / total, 3)
    confidence = round(abs(hw - aw) + abs(hw - d), 2)
    return hw, d, aw, min(confidence, 1.0)


async def fetch_competition_matches(code: str, date_from: str, date_to: str):
    """Recupere les matchs d'une competition sur une plage de dates."""
    url = f"{BASE_URL}/competitions/{code}/matches"
    params = {"dateFrom": date_from, "dateTo": date_to}
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.get(url, headers=HEADERS, params=params)
            increment_count()
            if r.status_code != 200:
                print(f"Erreur {code} : {r.status_code} - {r.text[:150]}")
                return []
            return r.json().get("matches", [])
        except Exception as e:
            print(f"Exception {code} : {e}")
            return []


async def daily_pipeline():
    print(f"=== Pipeline football-data.org {datetime.now().isoformat()} ===")
    today = date.today()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=DAYS_AHEAD)).isoformat()

    all_matches = []
    for code in COMPETITIONS:
        matches = await fetch_competition_matches(code, date_from, date_to)
        for m in matches:
            m["_competition_code"] = code
        all_matches.extend(matches)
        await asyncio.sleep(6)  # respecte la limite 10 req/min

    print(f"{len(all_matches)} matchs recuperes sur {DAYS_AHEAD} jours")

    if not all_matches:
        return

    conn = db()
    inserted = 0
    for m in all_matches:
        try:
            match_id = m["id"]
            code = m.get("_competition_code", "")
            league = COMPETITIONS.get(code, m.get("competition", {}).get("name", "Unknown"))
            country = m.get("area", {}).get("name", "International")
            home = m["homeTeam"]["name"] or m["homeTeam"].get("shortName", "?")
            away = m["awayTeam"]["name"] or m["awayTeam"].get("shortName", "?")
            kickoff = m.get("utcDate")
            status = m.get("status", "SCHEDULED")
            home_goals = m.get("score", {}).get("fullTime", {}).get("home")
            away_goals = m.get("score", {}).get("fullTime", {}).get("away")

            hw, d, aw, conf = predict()

            conn.execute(
                """
                INSERT OR REPLACE INTO matches
                (id, league, country, home, away, kickoff, status,
                 home_goals, away_goals, home_win, draw, away_win,
                 confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (match_id, league, country, home, away, kickoff, status,
                 home_goals, away_goals, hw, d, aw, conf, datetime.now().isoformat()),
            )
            inserted += 1
        except Exception as e:
            print(f"Erreur match {m.get('id')}: {e}")

    conn.commit()
    conn.close()
    print(f"{inserted} matchs enregistres sur {DAYS_AHEAD} jours")


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(daily_pipeline, "cron", hour=6, minute=0)
    scheduler.add_job(daily_pipeline, "cron", hour=12, minute=0)
    scheduler.start()
    asyncio.create_task(daily_pipeline())
    yield
    scheduler.shutdown()


app = FastAPI(title="SportIA Predict", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "app": "SportIA Predict", "source": "football-data.org"}


@app.get("/quota")
def quota():
    used = get_today_count()
    return {"used": used, "remaining_today": max(0, 95 - used)}


@app.get("/matches/{day}")
def get_matches(day: str):
    """Matchs d'un jour precis (format YYYY-MM-DD)."""
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff)=? ORDER BY kickoff ASC",
        (day,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/matches-week")
def matches_week():
    """Tous les matchs des 7 prochains jours."""
    today = date.today()
    week_later = (today + timedelta(days=DAYS_AHEAD)).isoformat()
    conn = db()
    rows = conn.execute(
        """
        SELECT * FROM matches
        WHERE date(kickoff) BETWEEN ? AND ?
        ORDER BY kickoff ASC
        """,
        (today.isoformat(), week_later),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/matches/{day}/top")
def top_matches(day: str, limit: int = 20):
    """Top N predictions du jour triees par confiance."""
    conn = db()
    rows = conn.execute(
        """
        SELECT * FROM matches
        WHERE date(kickoff)=? AND confidence IS NOT NULL
        ORDER BY confidence DESC
        LIMIT ?
        """,
        (day, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/leagues")
def get_leagues():
    """Liste des championnats presents dans la base."""
    conn = db()
    rows = conn.execute("SELECT DISTINCT league FROM matches").fetchall()
    conn.close()
    return [r["league"] for r in rows]


@app.get("/leagues/{league_name}/matches")
def matches_by_league(league_name: str):
    """Tous les matchs d'un championnat (7 jours)."""
    conn = db()
    rows = conn.execute(
        """
        SELECT * FROM matches
        WHERE LOWER(league) = LOWER(?)
        ORDER BY kickoff ASC
        """,
        (league_name,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/refresh")
async def manual_refresh():
    """Declenche un refresh manuel du pipeline."""
    await daily_pipeline()
    return {"status": "refreshed", "days_ahead": DAYS_AHEAD}
