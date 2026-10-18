import os
import math
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

COMPETITIONS = {
    "PL": "Premier League", "PD": "La Liga", "SA": "Serie A",
    "BL1": "Bundesliga", "FL1": "Ligue 1", "DED": "Eredivisie",
    "PPL": "Primeira Liga", "CL": "Champions League",
    "EC": "European Championship", "WC": "World Cup",
}

LEAGUE_AVG_GOALS = {
    "PL": 2.85, "PD": 2.65, "SA": 2.75, "BL1": 3.15, "FL1": 2.70,
    "DED": 3.20, "PPL": 2.55, "CL": 2.80, "EC": 2.60, "WC": 2.70,
}

DAYS_AHEAD = 7
HOME_ADVANTAGE = 1.18
FREE_MATCHES_PER_DAY = 2


# ===== BASE DE DONNEES =====

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # ATTENTION : plus de DROP TABLE. La base est conservee entre redeploiements.
    # Si tu dois ajouter une colonne, fais un DROP une seule fois puis retire-le.
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            league TEXT, country TEXT,
            home TEXT, away TEXT,
            home_logo TEXT, away_logo TEXT,
            kickoff TEXT, status TEXT,
            home_goals INTEGER, away_goals INTEGER,
            home_win REAL, draw REAL, away_win REAL,
            over_15 REAL, under_15 REAL,
            over_25 REAL, under_25 REAL,
            over_35 REAL, under_35 REAL,
            over_45 REAL, under_45 REAL,
            btts_yes REAL, btts_no REAL,
            first_half_goal REAL,
            handicap_home_1 REAL, handicap_away_1 REAL,
            home_xg REAL, away_xg REAL, total_xg REAL,
            confidence REAL,
            free_access INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    # Dans init_db(), après les colonnes existantes :
c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        ... -- colonnes existantes
        dc_1x REAL, dc_12 REAL, dc_x2 REAL,
        dnb_home REAL, dnb_away REAL,
        over_05 REAL, under_05 REAL,
        btts_over_25 REAL, btts_under_35 REAL,
        handicap_home_minus1 REAL, handicap_away_minus1 REAL,
        handicap_home_plus1 REAL, handicap_away_plus1 REAL,
        exact_scores TEXT,  -- JSON string
        home_scores REAL, away_scores REAL,
        updated_at TEXT
    )
""")
    c.execute("CREATE TABLE IF NOT EXISTS api_log (day TEXT PRIMARY KEY, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS team_logos (team TEXT PRIMARY KEY, logo TEXT)")
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
        "INSERT INTO api_log (day, count) VALUES (?, 1) "
        "ON CONFLICT(day) DO UPDATE SET count = count + 1",
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


# ===== LOGOS =====

async def get_team_logo(team_data: dict) -> str:
    crest = team_data.get("crest")
    if crest:
        if not crest.endswith('.svg'):
            crest = crest.rsplit('.', 1)[0] + '.svg'
        return crest

    team_name = team_data.get("name") or team_data.get("shortName", "")
    if not team_name:
        return ""

    conn = db()
    row = conn.execute("SELECT logo FROM team_logos WHERE team=?", (team_name,)).fetchone()
    conn.close()
    if row and row["logo"]:
        return row["logo"]

    url = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, params={"t": team_name})
            if "application/json" not in r.headers.get("content-type", ""):
                return ""
            data = r.json()
            teams = data.get("teams")
            if teams:
                for t in teams:
                    if t.get("strTeam", "").lower() == team_name.lower():
                        logo = t.get("strTeamBadge") or t.get("strTeamLogo")
                        if logo:
                            conn = db()
                            conn.execute(
                                "INSERT OR REPLACE INTO team_logos (team, logo) VALUES (?, ?)",
                                (team_name, logo),
                            )
                            conn.commit()
                            conn.close()
                            return logo
    except Exception as e:
        print("Erreur logo " + team_name + ": " + str(e))
    return ""


# ===== MODELE POISSON =====

def poisson_prob(k: int, lam: float) -> float:
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def calc_expected_goals(league_code: str):
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)
    home_xg = (base / 2.0) * HOME_ADVANTAGE
    away_xg = base / 2.0
    return max(0.3, round(home_xg, 2)), max(0.3, round(away_xg, 2))


def predict_all_markets(home_xg: float, away_xg: float) -> dict:
    MAX_GOALS = 10
    score_probs = {}
    for h in range(MAX_GOALS + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(MAX_GOALS + 1):
            p_a = poisson_prob(a, away_xg)
            score_probs[(h, a)] = p_h * p_a

    home_win = sum(p for (h, a), p in score_probs.items() if h > a)
    draw = sum(p for (h, a), p in score_probs.items() if h == a)
    away_win = sum(p for (h, a), p in score_probs.items() if h < a)

    total_dist = {}
    for (h, a), p in score_probs.items():
        t = h + a
        total_dist[t] = total_dist.get(t, 0) + p

    def over(line):
        return sum(p for t, p in total_dist.items() if t > line)

    over_15 = over(1.5)
    over_25 = over(2.5)
    over_35 = over(3.5)
    over_45 = over(4.5)

    p_home_scores = 1 - poisson_prob(0, home_xg)
    p_away_scores = 1 - poisson_prob(0, away_xg)
    btts_yes = p_home_scores * p_away_scores

    total_xg = home_xg + away_xg
    first_half_goal = 1 - math.exp(-0.45 * total_xg)
    handicap_home_1 = sum(p for (h, a), p in score_probs.items() if h - a >= 2)
    handicap_away_1 = sum(p for (h, a), p in score_probs.items() if a - h >= 2)

    main_probs = [home_win, draw, away_win, over_15, over_25, btts_yes]
    best = max(main_probs)
    confidence = max(0.0, min(1.0, (best - 0.33) / 0.67))

    return {
        "home_win": round(home_win, 3),
        "draw": round(draw, 3),
        "away_win": round(away_win, 3),
        "over_15": round(over_15, 3),
        "under_15": round(1 - over_15, 3),
        "over_25": round(over_25, 3),
        "under_25": round(1 - over_25, 3),
        "over_35": round(over_35, 3),
        "under_35": round(1 - over_35, 3),
        "over_45": round(over_45, 3),
        "under_45": round(1 - over_45, 3),
        "btts_yes": round(btts_yes, 3),
        "btts_no": round(1 - btts_yes, 3),
        "first_half_goal": round(first_half_goal, 3),
        "handicap_home_1": round(handicap_home_1, 3),
        "handicap_away_1": round(handicap_away_1, 3),
        "home_xg": home_xg,
        "away_xg": away_xg,
        "total_xg": round(total_xg, 2),
        "confidence": round(confidence, 2),
    }

def predict_extended_markets(home_xg: float, away_xg: float, home_win: float, draw: float, away_win: float) -> dict:
    """
    Calcule les probabilités pour 15 marchés de paris populaires.
    Prend en entrée les probabilités de base déjà calculées par predict_all_markets.
    """
    MAX_GOALS = 8  # Réduit pour la performance
    score_probs = {}
    for h in range(MAX_GOALS + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(MAX_GOALS + 1):
            p_a = poisson_prob(a, away_xg)
            score_probs[(h, a)] = p_h * p_a

    # 1. Double Chance
    dc_1x = home_win + draw
    dc_12 = home_win + away_win
    dc_x2 = draw + away_win

    # 2. Draw No Bet (remboursé si nul)
    dnb_home = home_win / (home_win + away_win) if (home_win + away_win) > 0 else 0
    dnb_away = away_win / (home_win + away_win) if (home_win + away_win) > 0 else 0

    # 3. Over/Under 0.5
    over_05 = 1 - score_probs.get((0, 0), 0)
    under_05 = score_probs.get((0, 0), 0)

    # 4. Distribution des totaux (pour over/under déjà existants)
    total_dist = {}
    for (h, a), p in score_probs.items():
        t = h + a
        total_dist[t] = total_dist.get(t, 0) + p

    def over(line):
        return sum(p for t, p in total_dist.items() if t > line)

    over_15 = over(1.5)
    over_25 = over(2.5)
    over_35 = over(3.5)
    over_45 = over(4.5)

    # 5. BTTS
    btts_yes = (1 - poisson_prob(0, home_xg)) * (1 - poisson_prob(0, away_xg))

    # 6. BTTS & Over 2.5
    btts_over_25 = sum(p for (h, a), p in score_probs.items()
                       if h > 0 and a > 0 and (h + a) > 2.5)

    # 7. BTTS & Under 3.5
    btts_under_35 = sum(p for (h, a), p in score_probs.items()
                        if h > 0 and a > 0 and (h + a) < 3.5)

    # 8. Handicap -1 (gagne par 2+ buts)
    handicap_home_minus1 = sum(p for (h, a), p in score_probs.items() if h - a >= 2)
    handicap_away_minus1 = sum(p for (h, a), p in score_probs.items() if a - h >= 2)

    # 9. Handicap +1 (perd par 1 max ou gagne)
    handicap_home_plus1 = sum(p for (h, a), p in score_probs.items() if h - a >= -1)
    handicap_away_plus1 = sum(p for (h, a), p in score_probs.items() if a - h >= -1)

    # 10. But en 1ère MT
    total_xg = home_xg + away_xg
    first_half_goal = 1 - math.exp(-0.45 * total_xg)

    # 11. Score exact (les 3 plus probables)
    top_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:3]
    exact_scores = [{"score": f"{h}-{a}", "prob": round(p, 3)} for (h, a), p in top_scores]

    # 12. Équipe marque (domicile / extérieur)
    home_scores = 1 - poisson_prob(0, home_xg)
    away_scores = 1 - poisson_prob(0, away_xg)

    return {
        "dc_1x": round(dc_1x, 3),
        "dc_12": round(dc_12, 3),
        "dc_x2": round(dc_x2, 3),
        "dnb_home": round(dnb_home, 3),
        "dnb_away": round(dnb_away, 3),
        "over_05": round(over_05, 3),
        "under_05": round(under_05, 3),
        "over_15": round(over_15, 3),
        "under_15": round(1 - over_15, 3),
        "over_25": round(over_25, 3),
        "under_25": round(1 - over_25, 3),
        "over_35": round(over_35, 3),
        "under_35": round(1 - over_35, 3),
        "over_45": round(over_45, 3),
        "under_45": round(1 - over_45, 3),
        "btts_yes": round(btts_yes, 3),
        "btts_no": round(1 - btts_yes, 3),
        "btts_over_25": round(btts_over_25, 3),
        "btts_under_35": round(btts_under_35, 3),
        "handicap_home_minus1": round(handicap_home_minus1, 3),
        "handicap_away_minus1": round(handicap_away_minus1, 3),
        "handicap_home_plus1": round(handicap_home_plus1, 3),
        "handicap_away_plus1": round(handicap_away_plus1, 3),
        "first_half_goal": round(first_half_goal, 3),
        "exact_scores": exact_scores,
        "home_scores": round(home_scores, 3),
        "away_scores": round(away_scores, 3),
    }

def generate_analysis(match: dict) -> str:
    home = match["home"]
    away = match["away"]
    league = match["league"]
    hw, d, aw = match["home_win"], match["draw"], match["away_win"]
    over_15, over_25, under_35 = match["over_15"], match["over_25"], match["under_35"]
    btts, fh = match["btts_yes"], match["first_half_goal"]
    hxg, axg, total_xg = match["home_xg"], match["away_xg"], match["total_xg"]

    markets = {
        "Victoire " + home: hw, "Match nul": d, "Victoire " + away: aw,
        "+1.5 buts": over_15, "+2.5 buts": over_25, "-3.5 buts": under_35,
        "Les 2 equipes marquent": btts, "But en 1ere MT": fh,
    }
    best_name, best_prob = max(markets.items(), key=lambda x: x[1])

    return "\n".join([
        home + " vs " + away + " (" + league + ")",
        "",
        "Buts attendus : " + str(total_xg) + " (dom " + str(hxg) + " - ext " + str(axg) + ")",
        "1X2 : " + str(round(hw * 100)) + "% / " + str(round(d * 100)) + "% / " + str(round(aw * 100)) + "%",
        "Total : +1.5 " + str(round(over_15 * 100)) + "% | +2.5 " + str(round(over_25 * 100)) + "% | -3.5 " + str(round(under_35 * 100)) + "%",
        "BTTS : " + str(round(btts * 100)) + "% | But 1MT : " + str(round(fh * 100)) + "%",
        "",
        "Pronostic recommande : " + best_name + " (" + str(round(best_prob * 100)) + "%)",
    ])


# ===== PIPELINE =====

async def fetch_competition_matches(code: str, date_from: str, date_to: str):
    url = BASE_URL + "/competitions/" + code + "/matches"
    params = {"dateFrom": date_from, "dateTo": date_to}
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.get(url, headers=HEADERS, params=params)
            increment_count()
            if r.status_code != 200:
                print("Erreur " + code + " : " + str(r.status_code))
                return []
            return r.json().get("matches", [])
        except Exception as e:
            print("Exception " + code + " : " + str(e))
            return []


async def daily_pipeline():
    print("=== Pipeline " + datetime.now().isoformat() + " ===")
    today = date.today()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=DAYS_AHEAD)).isoformat()

    all_matches = []
    for code in COMPETITIONS:
        matches = await fetch_competition_matches(code, date_from, date_to)
        for m in matches:
            m["_code"] = code
        all_matches.extend(matches)
        await asyncio.sleep(6)

    print(str(len(all_matches)) + " matchs recuperes")
    if not all_matches:
        return

    print("Recuperation des logos...")
    logos = {}
    for m in all_matches:
        try:
            home_team = m["homeTeam"]
            away_team = m["awayTeam"]
            home_name = home_team.get("name") or home_team.get("shortName", "?")
            away_name = away_team.get("name") or away_team.get("shortName", "?")
            if home_name not in logos:
                logos[home_name] = await get_team_logo(home_team)
            if away_name not in logos:
                logos[away_name] = await get_team_logo(away_team)
            await asyncio.sleep(0.5)
        except (KeyError, TypeError):
            continue
    print(str(len(logos)) + " logos recuperes")

    conn = db()
    inserted = 0
    for m in all_matches:
        try:
            code = m.get("_code", "")
            match_id = m["id"]
            league = COMPETITIONS.get(code, "Unknown")
            country = m.get("area", {}).get("name", "International")
            home = m["homeTeam"]["name"] or m["homeTeam"].get("shortName", "?")
            away = m["awayTeam"]["name"] or m["awayTeam"].get("shortName", "?")
            kickoff = m.get("utcDate")
            status = m.get("status", "SCHEDULED")
            home_goals = m.get("score", {}).get("fullTime", {}).get("home")
            away_goals = m.get("score", {}).get("fullTime", {}).get("away")

            home_xg, away_xg = calc_expected_goals(code)
            pred = predict_all_markets(home_xg, away_xg)
            ext = predict_extended_markets(home_xg, away_xg, pred["home_win"], pred["draw"], pred["away_win"])

            conn.execute(
                """
                INSERT OR REPLACE INTO matches
                (id, league, country, home, away, home_logo, away_logo,
                 kickoff, status, home_goals, away_goals,
                 home_win, draw, away_win, over_15, under_15, over_25, under_25,
                 over_35, under_35, over_45, under_45, btts_yes, btts_no,
                 first_half_goal, handicap_home_1, handicap_away_1,
                 home_xg, away_xg, total_xg, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (match_id, league, country, home, away,
                 logos.get(home, ""), logos.get(away, ""),
                 kickoff, status, home_goals, away_goals,
                 pred["home_win"], pred["draw"], pred["away_win"],
                 pred["over_15"], pred["under_15"], pred["over_25"], pred["under_25"],
                 pred["over_35"], pred["under_35"], pred["over_45"], pred["under_45"],
                 pred["btts_yes"], pred["btts_no"], pred["first_half_goal"],
                 pred["handicap_home_1"], pred["handicap_away_1"],
                 pred["home_xg"], pred["away_xg"], pred["total_xg"],
                 pred["confidence"], datetime.now().isoformat()),
            )
            inserted += 1
        except Exception as e:
            print("Erreur match " + str(m.get("id")) + ": " + str(e))

    conn.commit()
    conn.close()
    print(str(inserted) + " matchs enregistres")
    mark_free_access()


def mark_free_access():
    today = date.today().isoformat()
    conn = db()
    conn.execute("UPDATE matches SET free_access = 0 WHERE date(kickoff) = ?", (today,))
    conn.execute(
        "UPDATE matches SET free_access = 1 WHERE id IN ("
        "SELECT id FROM matches WHERE date(kickoff) = ? "
        "AND confidence IS NOT NULL ORDER BY confidence DESC LIMIT ?)",
        (today, FREE_MATCHES_PER_DAY),
    )
    conn.commit()
    conn.close()
    print("Top " + str(FREE_MATCHES_PER_DAY) + " matchs marques comme gratuits")


# ===== APP =====

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
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/")
def root():
    return {"status": "ok", "app": "SportIA Predict", "version": "2.2"}


@app.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}


@app.get("/quota")
def quota():
    used = get_today_count()
    return {"used": used, "remaining_today": max(0, 95 - used)}


@app.get("/matches/{day}")
def get_matches(day: str):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff)=? ORDER BY kickoff ASC", (day,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        m = dict(r)
        m["analysis"] = generate_analysis(m)
        result.append(m)
    return result


@app.get("/matches-week")
def matches_week():
    today = date.today()
    week_later = (today + timedelta(days=DAYS_AHEAD)).isoformat()
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff) BETWEEN ? AND ? ORDER BY kickoff ASC",
        (today.isoformat(), week_later),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        m = dict(r)
        m["analysis"] = generate_analysis(m)
        result.append(m)
    return result


@app.get("/predictions/{day}/free")
def get_free_predictions(day: str):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff)=? AND free_access=1 ORDER BY confidence DESC",
        (day,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        m = dict(r)
        m["analysis"] = generate_analysis(m)
        result.append(m)
    return result


@app.get("/predictions/{day}/premium")
def get_premium_predictions(day: str):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff)=? ORDER BY confidence DESC", (day,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        m = dict(r)
        m["analysis"] = generate_analysis(m)
        result.append(m)
    return result


@app.get("/matches/{match_id}/detail")
def match_detail(match_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Match introuvable")
    m = dict(row)
    # Convertit la chaîne JSON des scores exacts en liste
    if m.get("exact_scores"):
        try:
            import json
            m["exact_scores"] = json.loads(m["exact_scores"])
        except:
            m["exact_scores"] = []
    m["analysis"] = generate_analysis(m)
    return m

@app.get("/leagues")
def get_leagues():
    conn = db()
    rows = conn.execute("SELECT DISTINCT league FROM matches").fetchall()
    conn.close()
    return [r["league"] for r in rows]


# ===== SCORES EN DIRECT =====

_live_cache = {"day": None, "timestamp": None, "data": []}


@app.get("/live-scores/{day}")
async def get_live_scores(day: str, refresh: bool = False):
    """
    Retourne les matchs du jour avec leur statut + score.
    Cache de 3 minutes pour economiser le quota FD.org.
    """
    global _live_cache
    now = datetime.now()
    cache_valid = (
        _live_cache["day"] == day
        and _live_cache["timestamp"] is not None
        and (now - _live_cache["timestamp"]).total_seconds() < 180
    )
    if cache_valid and not refresh:
        return _live_cache["data"]

    all_results = []
    for code in COMPETITIONS.keys():
        try:
            url = f"{BASE_URL}/competitions/{code}/matches"
            params = {"dateFrom": day, "dateTo": day}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, headers=HEADERS, params=params)
                increment_count()
                if r.status_code != 200:
                    continue
                data = r.json()
                for m in data.get("matches", []):
                    status = m.get("status", "")
                    if status in ["IN_PLAY", "PAUSED", "FINISHED", "TIMED", "SCHEDULED"]:
                        all_results.append({
                            "id": m["id"],
                            "home": m["homeTeam"]["name"],
                            "away": m["awayTeam"]["name"],
                            "status": status,
                            "home_score": m.get("score", {}).get("fullTime", {}).get("home"),
                            "away_score": m.get("score", {}).get("fullTime", {}).get("away"),
                            "utc_date": m.get("utcDate"),
                        })
                await asyncio.sleep(6)
        except Exception as e:
            print("Live " + code + ": " + str(e))

    _live_cache = {"day": day, "timestamp": now, "data": all_results}
    return all_results

# ===== TICKETS DU JOUR =====

def _build_pick_for_match(m):
    """Choisit le meilleur pick pour un match (cote proche de 1.35)."""
    markets = [
        ("1", m["home_win"], m["home"]),
        ("X", m["draw"], "Match nul"),
        ("2", m["away_win"], m["away"]),
        ("+1.5", m["over_15"], "+1.5 buts"),
        ("+2.5", m["over_25"], "+2.5 buts"),
        ("-3.5", m["under_35"], "-3.5 buts"),
        ("-4.5", m["under_45"], "-4.5 buts"),
        ("BTTS", m["btts_yes"], "Les 2 equipes marquent"),
        ("1MT", m["first_half_goal"], "But en 1ere MT"),
    ]
    best = None
    best_dist = 999
    for label, prob, desc in markets:
        if prob < 0.50:
            continue
        cote = 1.0 / prob
        dist = abs(cote - 1.35)
        if dist < best_dist:
            best_dist = dist
            best = {
                "match_id": m["id"],
                "home": m["home"],
                "away": m["away"],
                "league": m["league"],
                "kickoff": m["kickoff"],
                "home_logo": m["home_logo"],
                "away_logo": m["away_logo"],
                "market": label,
                "description": desc,
                "proba": round(prob, 3),
                "cote": round(cote, 2),
            }
    return best


def _select_for_target(picks, target, min_n, max_n):
    """Selectionne le meilleur nombre de picks pour atteindre une cote cible."""
    if not picks:
        return []
    best_combo = []
    best_diff = float('inf')
    for n in range(min_n, min(max_n + 1, len(picks) + 1)):
        combo = picks[:n]
        cote = 1.0
        for p in combo:
            cote *= p["cote"]
        diff = abs(cote - target)
        if diff < best_diff:
            best_diff = diff
            best_combo = combo
    return best_combo


@app.get("/tickets/{day}")
def get_tickets(day: str):
    """Genere les 3 tickets du jour (safe, medium, risky)."""
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff)=? ORDER BY kickoff ASC",
        (day,),
    ).fetchall()
    conn.close()

    if not rows:
        return {"error": "Aucun match pour cette date"}

    # 1. Genere un pick par match
    all_picks = []
    for r in rows:
        m = dict(r)
        pick = _build_pick_for_match(m)
        if pick:
            all_picks.append(pick)

    if not all_picks:
        return {"error": "Aucun pick disponible"}

    # 2. Trie par cote croissante
    all_picks.sort(key=lambda x: x["cote"])

    # 3. Safe : 2 picks, cote ~2
    safe = _select_for_target(all_picks, 2.0, 2, 3)
    safe_ids = {p["match_id"] for p in safe}

    # 4. Medium : 12-15 picks, cote ~120
    remaining = [p for p in all_picks if p["match_id"] not in safe_ids]
    medium = _select_for_target(remaining, 120.0, 12, 15)
    medium_ids = {p["match_id"] for p in medium}

    # 5. Risky : 25-35 picks, cote ~1500
    remaining2 = [p for p in remaining if p["match_id"] not in medium_ids]
    risky = _select_for_target(remaining2, 1500.0, 25, 35)

    def _total_cote(picks):
        c = 1.0
        for p in picks:
            c *= p["cote"]
        return round(c, 2)

    return {
        "date": day,
        "safe": {
            "name": "Ticket Safe",
            "total_cote": _total_cote(safe),
            "count": len(safe),
            "picks": safe,
        },
        "medium": {
            "name": "Ticket Medium",
            "total_cote": _total_cote(medium),
            "count": len(medium),
            "picks": medium,
        },
        "risky": {
            "name": "Ticket Risky",
            "total_cote": _total_cote(risky),
            "count": len(risky),
            "picks": risky,
        },
    }
    

@app.post("/refresh")
async def manual_refresh():
    await daily_pipeline()
    return {"status": "refreshed", "days_ahead": DAYS_AHEAD}
