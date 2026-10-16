import sqlite3
import asyncio
from datetime import date, datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from sofascore_api import SofaScoreClient

load_dotenv()

DB_PATH = "/tmp/sportia.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY, league TEXT, country TEXT, home TEXT, away TEXT,
            kickoff TEXT, status TEXT, home_goals INTEGER, away_goals INTEGER,
            home_win REAL, draw REAL, away_win REAL, confidence REAL, updated_at TEXT
        )
    """)
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

def predict(home_rank: int, away_rank: int, home_pts: int, away_pts: int):
    if home_rank == 0 and away_rank == 0:
        return 0.40, 0.28, 0.32, 0.3
    home_strength = (1 / max(home_rank, 1)) + (home_pts / 100)
    away_strength = (1 / max(away_rank, 1)) + (away_pts / 100)
    home_strength *= 1.15
    total = home_strength + away_strength + 0.30
    hw = round(home_strength / total, 3)
    d = round(0.30 / total, 3)
    aw = round(away_strength / total, 3)
    confidence = round(abs(hw - aw) + abs(hw - d), 2)
    return hw, d, aw, min(confidence, 1.0)

async def daily_pipeline():
    print(f"=== Pipeline pysofascore {datetime.now().isoformat()} ===")
    today = date.today().isoformat()
    try:
        with SofaScoreClient() as client:
            events = client.get_events_by_date("football", today)
            print(f"{len(events)} matchs récupérés depuis pysofascore")
    except Exception as e:
        print(f"Erreur pysofascore : {e}")
        return

    conn = db()
    inserted = 0
    for m in events:
        try:
            match_id = m["id"]
            league = m.get("tournament", {}).get("name", "Unknown")
            country = m.get("tournament", {}).get("category", {}).get("name", "International")
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            kickoff_ts = m.get("startTimestamp")
            kickoff = datetime.fromtimestamp(kickoff_ts).isoformat() if kickoff_ts else None
            status = m.get("status", {}).get("type", "notstarted")
            home_goals = m.get("homeScore", {}).get("current")
            away_goals = m.get("awayScore", {}).get("current")

            hw, d, aw, conf = predict(0, 0, 0, 0)
            increment_count()

            conn.execute(
                """
                INSERT OR REPLACE INTO matches
                (id, league, country, home, away, kickoff, status,
                 home_goals, away_goals, home_win, draw, away_win, confidence, updated_at)
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
    print(f"{inserted} matchs enregistrés")

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

app = FastAPI(title="SportIA Predict (pysofascore)", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"status": "ok", "app": "SportIA Predict", "source": "pysofascore"}

@app.get("/matches/{day}")
def get_matches(day: str):
    conn = db()
    rows = conn.execute("SELECT * FROM matches WHERE date(kickoff)=? ORDER BY kickoff ASC", (day,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/refresh")
async def manual_refresh():
    await daily_pipeline()
    return {"status": "refreshed"}
