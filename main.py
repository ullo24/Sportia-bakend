import os
import sqlite3
import asyncio
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from curl_cffi import requests
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# --- CONFIGURATION SOFASCORE ---
SOFA_BASE_URL = "https://api.sofascore.com/api/v1"
# En-têtes pour simuler un navigateur Chrome
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "X-Requested-With": "XMLHttpRequest",  # <- OBLIGATOIRE
}

DB_PATH = "/tmp/sportia.db"  # Chemin sur Render
MAX_REQUESTS = 95 # On garde une limite de sécurité (mais SofaScore n'a pas de quota officiel)

# --- BASE DE DONNÉES (inchangée) ---
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_log (day TEXT PRIMARY KEY, count INTEGER)
    """)
    conn.commit()
    conn.close()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- GESTION DU QUOTA ---
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

# --- APPEL SÉCURISÉ À SOFASCORE ---
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def safe_get_sofascore(endpoint: str):
    """Appel sécurisé avec curl_cffi et retry automatique."""
    if not can_request():
        raise HTTPException(429, "Quota journalier atteint")
    
    url = f"{SOFA_BASE_URL}{endpoint}"
    
    # On utilise curl_cffi qui imite Chrome
    response = requests.get(url, headers=HEADERS, impersonate="chrome110")
    
    if response.status_code == 403:
        # Erreur de challenge Cloudflare
        raise Exception("Blocage Cloudflare (403)")
    
    increment_count()
    return response.json()

# --- MODÈLE IA (inchangé) ---
def predict(home_rank: int, away_rank: int, home_pts: int, away_pts: int):
    if home_rank == 0 and away_rank == 0:
        return 0.40, 0.28, 0.32, 0.3
    home_strength = (1 / max(home_rank, 1)) + (home_pts / 100)
    away_strength = (1 / max(away_rank, 1)) + (away_pts / 100)
    home_strength *= 1.15
    total = home_strength + away_strength + 0.30
    hw = round(home_strength / total, 3)
    d  = round(0.30 / total, 3)
    aw = round(away_strength / total, 3)
    confidence = round(abs(hw - aw) + abs(hw - d), 2)
    return hw, d, aw, min(confidence, 1.0)

# --- RÉCUPÉRATION DES DONNÉES SOFASCORE ---
async def fetch_scheduled_tournaments(day: str):
    """Récupère la liste des tournois programmés pour une date."""
    endpoint = f"/sport/football/scheduled-tournaments/{day}"
    try:
        data = await safe_get_sofascore(endpoint)
        return data.get("tournaments", [])
    except Exception as e:
        print(f"Erreur récupération tournois : {e}")
        return []

async def fetch_events_for_tournament(unique_tournament_id: int, day: str):
    """Récupère les matchs d'un tournoi spécifique pour une date."""
    endpoint = f"/unique-tournament/{unique_tournament_id}/scheduled-events/{day}"
    try:
        data = await safe_get_sofascore(endpoint)
        return data.get("events", [])
    except Exception as e:
        # On ignore silencieusement les tournois qui n'ont pas de matchs
        return []

# --- PIPELINE QUOTIDIEN ---
async def daily_pipeline():
    print(f"=== Pipeline SofaScore {datetime.now().isoformat()} ===")
    today = date.today().isoformat()

    # Étape 1 : Récupérer les tournois du jour
    tournaments = await fetch_scheduled_tournaments(today)
    print(f"{len(tournaments)} tournois trouvés pour {today}")

    if not tournaments:
        print("Aucun tournoi programmé pour cette date.")
        return

    # Étape 2 : Récupérer les matchs de chaque tournoi
    all_matches = []
    for tournament in tournaments:
        try:
            ut_id = tournament["uniqueTournament"]["id"]
            events = await fetch_events_for_tournament(ut_id, today)
            # On ajoute le nom du tournoi à chaque match pour l'affichage
            for event in events:
                event["_tournament_name"] = tournament["name"]
            all_matches.extend(events)
        except (KeyError, TypeError):
            continue  # On ignore les entrées mal formées

    print(f"{len(all_matches)} matchs récupérés au total depuis SofaScore")
    
    # Le reste de la fonction (insertion en base de données) reste inchangé
    # Le reste du code d'insertion existant)

    conn = db()
    inserted = 0
    for m in matches:
        try:
            # La structure JSON de SofaScore est différente
            # La structure des événements est maintenant différente
              match_id = m["id"]
            # Le nom du tournoi est maintenant dans une clé que nous avons ajoutée
              league = m.get("_tournament_name", "Unknown League")
            # L'ID du tournoi est aussi utile
            unique_tournament_id = m.get("tournament", {}).get("uniqueTournament", {}).get("id")
            # Le pays n'est plus toujours présent, on met une valeur par défaut
            country = "International" 
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            
            # Date de coup d'envoi (timestamp UNIX à convertir)
            kickoff_ts = m["startTimestamp"]
            kickoff = datetime.fromtimestamp(kickoff_ts).isoformat()
            
            # Statut et score (si le match a commencé)
            status = m.get("status", {}).get("type", "notstarted")
            home_goals = m.get("homeScore", {}).get("current")
            away_goals = m.get("awayScore", {}).get("current")
            
            # Pour l'instant, on utilise un modèle simple basé sur des valeurs par défaut
            # (On n'a pas encore les classements, on pourrait les récupérer via un autre endpoint)
            hw, d, aw, conf = predict(0, 0, 0, 0)
            
            conn.execute("""
                INSERT OR REPLACE INTO matches
                (id, league, country, home, away, kickoff, status,
                 home_goals, away_goals, home_win, draw, away_win, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match_id, league, country, home, away, kickoff, status,
                home_goals, away_goals, hw, d, aw, conf,
                datetime.now().isoformat()
            ))
            inserted += 1
        except Exception as e:
            print(f"Erreur match {m.get('id')}: {e}")

    conn.commit()
    conn.close()
    print(f"{inserted} matchs SofaScore enregistrés")

# --- APP FASTAPI ---
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

app = FastAPI(title="SportIA Predict (SofaScore)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS (identiques) ---
@app.get("/")
def root():
    return {"status": "ok", "app": "SportIA Predict", "source": "SofaScore"}

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

@app.post("/refresh")
async def manual_refresh():
    await daily_pipeline()
    return {"status": "refreshed"}
