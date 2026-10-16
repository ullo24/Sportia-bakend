import os
import sqlite3
import httpx
import asyncio
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}
MAX_REQUESTS = int(os.getenv("MAX_REQUESTS_PER_DAY", 95))
DB_PATH = "sportia.db"

# Ligues prioritaires (IDs API-Football)
PRIORITY_LEAGUES = {
    39:  "Premier League",
    140: "La Liga",
    135: "Serie A",
    78:  "Bundesliga",
    61:  "Ligue 1",
    2:   "Champions League",
    3:   "Europa League",
    848: "Conference League",
    94:  "Primeira Liga",
    88:  "Eredivisie",
}

# ---------- BASE DE DONNÉES ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            league_id INTEGER,
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
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS standings (
            league_id INTEGER,
            team TEXT,
            rank INTEGER,
            points INTEGER,
            played INTEGER,
            cached_at TEXT,
            PRIMARY KEY (league_id, team)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_log (
            day TEXT PRIMARY KEY,
            count INTEGER
        )
    """)
    conn.commit()
    conn.close()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------- GESTION DU QUOTA ----------
def get_today_count() -> int:
    today = date.today().isoformat()
    conn = db()
    row = conn.execute("SELECT count FROM api_log WHERE day=?", (today,)).fetchone()
    conn.close()
    return row["count"] if row else 0

def increment_count():
    today = date.today().isoformat()
    conn = db()
    conn.execute("""
        INSERT INTO api_log (day, count) VALUES (?, 1)
        ON CONFLICT(day) DO UPDATE SET count = count + 1
    """, (today,))
    conn.commit()
    conn.close()

def can_request() -> bool:
    return get_today_count() < MAX_REQUESTS

async def safe_get(endpoint: str, params: dict):
    if not can_request():
        raise HTTPException(429, "Quota journalier API atteint")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params)
        increment_count()
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"Erreur API: {r.text[:200]}")
        return r.json()

# ---------- MODÈLE IA (à remplacer par XGBoost plus tard) ----------
def predict(home_rank: int, away_rank: int, home_pts: int, away_pts: int):
    """
    Modèle simple basé sur le classement et les points.
    Plus tard : remplacer par un vrai modèle XGBoost entraîné sur données historiques.
    """
    if home_rank == 0 and away_rank == 0:
        return 0.40, 0.28, 0.32, 0.3  # pas de data

    # Force = inverse du rang + points
    home_strength = (1 / max(home_rank, 1)) + (home_pts / 100)
    away_strength = (1 / max(away_rank, 1)) + (away_pts / 100)

    # Avantage domicile
    home_strength *= 1.15

    total = home_strength + away_strength + 0.30  # 0.30 = match nul
    hw = round(home_strength / total, 3)
    d  = round(0.30 / total, 3)
    aw = round(away_strength / total, 3)

    # Confiance = écart entre les probas
    confidence = round(abs(hw - aw) + abs(hw - d), 2)
    confidence = min(confidence, 1.0)

    return hw, d, aw, confidence

# ---------- RÉCUPÉRATION DES DONNÉES ----------
async def fetch_today_matches():
    today = date.today().isoformat()
    data = await safe_get("fixtures", {"date": today})
    return data.get("response", [])

async def fetch_standings(league_id: int, season: int):
    conn = db()
    row = conn.execute("""
        SELECT cached_at FROM standings
        WHERE league_id=? LIMIT 1
    """, (league_id,)).fetchone()
    conn.close()

    # Cache 24h
    if row:
        cached = datetime.fromisoformat(row["cached_at"])
        if datetime.now() - cached < timedelta(hours=24):
            return  # données fraîches

    data = await safe_get("standings", {"league": league_id, "season": season})
    try:
        standings = data["response"][0]["league"]["standings"][0]
    except (IndexError, KeyError):
        return

    conn = db()
    for team in standings:
        conn.execute("""
            INSERT OR REPLACE INTO standings
            (league_id, team, rank, points, played, cached_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            league_id,
            team["team"]["name"],
            team["rank"],
            team["points"],
            team["all"]["played"],
            datetime.now().isoformat()
        ))
    conn.commit()
    conn.close()

def get_team_stats(league_id: int, team_name: str):
    conn = db()
    row = conn.execute("""
        SELECT rank, points FROM standings
        WHERE league_id=? AND team=?
    """, (league_id, team_name)).fetchone()
    conn.close()
    if row:
        return row["rank"], row["points"]
    return 0, 0

# ---------- PIPELINE QUOTIDIEN ----------
async def daily_pipeline():
    print(f"=== Pipeline {datetime.now().isoformat()} ===")
    try:
        matches = await fetch_today_matches()
        print(f"{len(matches)} matchs récupérés")
    except Exception as e:
        print(f"Erreur récupération matchs : {e}")
        return

    # Récupérer les classements des ligues prioritaires
    season = date.today().year
    if date.today().month < 7:
        season -= 1

    for league_id in PRIORITY_LEAGUES:
        try:
            await fetch_standings(league_id, season)
            await asyncio.sleep(0.5)  # éviter le rate limit
        except Exception as e:
            print(f"Erreur classement ligue {league_id}: {e}")

    # Générer les prédictions
    conn = db()
    inserted = 0
    for m in matches:
        try:
            match_id = m["fixture"]["id"]
            league_id = m["league"]["id"]
            home = m["teams"]["home"]["name"]
            away = m["teams"]["away"]["name"]

            home_rank, home_pts = get_team_stats(league_id, home)
            away_rank, away_pts = get_team_stats(league_id, away)

            hw, d, aw, conf = predict(home_rank, away_rank, home_pts, away_pts)

            conn.execute("""
                INSERT OR REPLACE INTO matches
                (id, league_id, league, country, home, away, kickoff, status,
                 home_goals, away_goals, home_win, draw, away_win, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match_id,
                league_id,
                m["league"]["name"],
                m["league"]["country"],
                home,
                away,
                m["fixture"]["date"],
                m["fixture"]["status"]["short"],
                m["goals"]["home"],
                m["goals"]["away"],
                hw, d, aw, conf,
                datetime.now().isoformat()
            ))
            inserted += 1
        except Exception as e:
            print(f"Erreur match {m.get('fixture', {}).get('id')}: {e}")

    conn.commit()
    conn.close()
    print(f"{inserted} matchs enregistrés avec prédictions")

# ---------- APP FASTAPI ----------
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(daily_pipeline, "cron", hour=6, minute=0)
    scheduler.add_job(daily_pipeline, "cron", hour=12, minute=0)  # refresh midi
    scheduler.start()
    # Premier lancement immédiat en tâche de fond
    asyncio.create_task(daily_pipeline())
    yield
    scheduler.shutdown()

app = FastAPI(title="SportIA Predict API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- ENDPOINTS ----------
@app.get("/")
def root():
    return {"status": "ok", "app": "SportIA Predict"}

@app.get("/quota")
def quota():
    used = get_today_count()
    return {"used": used, "max": MAX_REQUESTS, "remaining": MAX_REQUESTS - used}

@app.get("/matches/{day}")
def get_matches(day: str):
    conn = db()
    rows = conn.execute("""
        SELECT * FROM matches WHERE date(kickoff)=?
        ORDER BY kickoff ASC
    """, (day,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/matches/{day}/league/{league_id}")
def get_by_league(day: str, league_id: int):
    conn = db()
    rows = conn.execute("""
        SELECT * FROM matches WHERE date(kickoff)=? AND league_id=?
        ORDER BY kickoff ASC
    """, (day, league_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/leagues")
def get_leagues():
    conn = db()
    rows = conn.execute("""
        SELECT DISTINCT league_id, league, country FROM matches
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/top-predictions/{day}")
def top_predictions(day: str, limit: int = Query(20, le=100)):
    """Meilleures prédictions (confidence élevée)."""
    conn = db()
    rows = conn.execute("""
        SELECT * FROM matches
        WHERE date(kickoff)=? AND confidence IS NOT NULL
        ORDER BY confidence DESC LIMIT ?
    """, (day, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/refresh")
async def manual_refresh():
    """Déclenche un refresh manuel (à protéger en prod !)."""
    await daily_pipeline()
    return {"status": "refreshed"}
