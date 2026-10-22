ZAFRONIX_BASE_URL_MLS = "https://api.zafronix.com/usa/mls/v1"
import os
import math
import json
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

APISPORTS_KEY = os.getenv("APISPORTS_KEY")
APISPORTS_HOST = "v3.football.api-sports.io"

# IDs des compétitions européennes sur API-Football
API_FOOTBALL_LEAGUES = {
    "CL": 2,  # Champions League uniquement (EL et UECL passent par football-data.org)
}

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY or ""}
DB_PATH = "/tmp/sportia.db"
_PIPELINE_RUNNING = False

COMPETITIONS = {
    "PL": "Premier League", "PD": "La Liga", "SA": "Serie A",
    "BL1": "Bundesliga", "FL1": "Ligue 1", "DED": "Eredivisie",
    "PPL": "Primeira Liga", "CL": "Champions League",
    "EL": "Europa League",
}
LEAGUE_AVG_GOALS = {
    "PL": 2.85, "PD": 2.65, "SA": 2.75, "BL1": 3.15, "FL1": 2.70,
    "DED": 3.20, "PPL": 2.55, "CL": 2.80, "EC": 2.60, "WC": 2.70,
}

DAYS_AHEAD = 7
HOME_ADVANTAGE = 1.18
FREE_MATCHES_PER_DAY = 2
# Top teams par ligue pour le ticket semaine
LEAGUE_TOP_N = {
    "PL": 5,   # Premier League
    "PD": 4,   # La Liga
    "FL1": 4,  # Ligue 1
    "DED": 4,  # Eredivisie
    "BL1": 5,  # Bundesliga
    "PPL": 4,  # Liga Portugal
}

# Cache 24h des standings
_STANDINGS_CACHE = {}
MIGRATE_DB = False  # ⚠️ Passer a False apres le premier refresh reussi


# ===== BASE DE DONNEES =====

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if MIGRATE_DB:
        c.execute("DROP TABLE IF EXISTS matches")
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY,
            league TEXT, country TEXT,
            home TEXT, away TEXT,
            home_logo TEXT, away_logo TEXT,
            kickoff TEXT, status TEXT,
            home_goals INTEGER, away_goals INTEGER,
            ht_home_goals INTEGER, ht_away_goals INTEGER,
            home_win REAL, draw REAL, away_win REAL,
            over_15 REAL, under_15 REAL,
            over_25 REAL, under_25 REAL,
            over_35 REAL, under_35 REAL,
            over_45 REAL, under_45 REAL,
            btts_yes REAL, btts_no REAL,
            first_half_goal REAL,
            handicap_home_1 REAL, handicap_away_1 REAL,
            dc_1x REAL, dc_12 REAL, dc_x2 REAL,
            dnb_home REAL, dnb_away REAL,
            over_05 REAL, under_05 REAL,
            btts_over_25 REAL, btts_under_35 REAL,
            handicap_home_minus1 REAL, handicap_away_minus1 REAL,
            handicap_home_plus1 REAL, handicap_away_plus1 REAL,
            handicap_home_minus2 REAL, handicap_away_minus2 REAL,
            first_half_over_15 REAL,
            exact_scores TEXT,
            home_scores REAL, away_scores REAL,
            home_xg REAL, away_xg REAL, total_xg REAL,
            confidence REAL,
            free_access INTEGER DEFAULT 0,
            updated_at TEXT
        )
        
    """)
    c.execute("CREATE TABLE IF NOT EXISTS api_log (day TEXT PRIMARY KEY, count INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS team_logos (team TEXT PRIMARY KEY, logo TEXT)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
            team TEXT,
            league TEXT,
            matches_played INTEGER,
            wins INTEGER,
            draws INTEGER,
            losses INTEGER,
            goals_for INTEGER,
            goals_against INTEGER,
            goals_for_home INTEGER,
            goals_against_home INTEGER,
            goals_for_away INTEGER,
            goals_against_away INTEGER,
            points INTEGER,
            form TEXT,
            cached_at TEXT,
            PRIMARY KEY (team, league)
        )
    """)
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

def calc_expected_goals_v2(league_code: str, home_team: str, away_team: str):
    """Calcule les xG avec classement + stats + garde-fous."""
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)

    conn = db()
    league_name = COMPETITIONS.get(league_code, "")

    # Les competitions europeennes ont des equipes de plusieurs ligues
    # -> on autorise la recherche dans n'importe quelle ligue
    allow_any_league = league_code in ["CL", "EL", "UECL", "EC", "WC"]

    prefixes = ["FC ", "AC ", "SC ", "AS ", "SS ", "SSC ", "CF ", "RC ",
                "1. ", "SV ", "TSG ", "VfB ", "VfL ", "FK ", "SK ",
                "CD ", "GD ", "CA ", "Real ", "Sporting ", "Club ",
                "Atletico ", "Atlético ", "Olympique ", "Stade "]

    def _clean_name(n):
        cleaned = n
        for p in prefixes:
            cleaned = cleaned.replace(p, "")
        return cleaned.strip().lower()

    def _find_team_stats(team_name):
        # 1. Exact match dans la ligue specifique
        row = conn.execute(
            "SELECT * FROM team_stats WHERE team=? AND league=?",
            (team_name, league_name),
        ).fetchone()
        if row:
            return row

        # 2. Si competition europeenne : exact match dans n'importe quelle ligue
        if allow_any_league:
            row = conn.execute(
                "SELECT * FROM team_stats WHERE team=? LIMIT 1",
                (team_name,),
            ).fetchone()
            if row:
                return row

        cleaned = _clean_name(team_name)

        # 3. Prefix match dans la ligue specifique
        all_teams = conn.execute(
            "SELECT * FROM team_stats WHERE league=?", (league_name,)
        ).fetchall()
        for team_row in all_teams:
            if cleaned in _clean_name(team_row["team"]) or _clean_name(team_row["team"]) in cleaned:
                return team_row

        # 4. Prefix match dans n'importe quelle ligue (CL/EL)
        if allow_any_league:
            all_teams = conn.execute("SELECT * FROM team_stats").fetchall()
            for team_row in all_teams:
                if cleaned in _clean_name(team_row["team"]) or _clean_name(team_row["team"]) in cleaned:
                    return team_row

        return None

    home_stats = _find_team_stats(home_team)
    away_stats = _find_team_stats(away_team)
    conn.close()

    # === GARDE-FOU 1 : fallback si une equipe manque de stats ===
    home_ok = home_stats and home_stats["matches_played"] >= 3
    away_ok = away_stats and away_stats["matches_played"] >= 3

    if not home_ok or not away_ok:
        home_xg = (base / 2.0) * HOME_ADVANTAGE
        away_xg = base / 2.0
        return max(0.5, round(home_xg, 2)), max(0.5, round(away_xg, 2))

    home_mp = max(home_stats["matches_played"], 1)
    away_mp = max(away_stats["matches_played"], 1)

    # === FORMULE : points par match ===
    home_ppm = home_stats["points"] / home_mp
    away_ppm = away_stats["points"] / away_mp

    # === GARDE-FOU 2 : si peu de points, fallback ===
    if home_ppm + away_ppm < 0.5:
        home_xg = (base / 2.0) * HOME_ADVANTAGE
        away_xg = base / 2.0
        return max(0.5, round(home_xg, 2)), max(0.5, round(away_xg, 2))

    # === GARDE-FOU 3 : ratio max 3:1 entre les 2 equipes ===
    home_ppm = max(home_ppm, away_ppm * 0.33)
    away_ppm = max(away_ppm, home_ppm * 0.33)

    total_ppm = home_ppm + away_ppm
    home_ratio = home_ppm / total_ppm
    away_ratio = 1.0 - home_ratio

    home_xg = base * home_ratio * HOME_ADVANTAGE
    away_xg = base * away_ratio / HOME_ADVANTAGE

    # === Ajustement attaque/defense (25%) ===
    home_attack = home_stats["goals_for"] / home_mp
    home_defense = home_stats["goals_against"] / home_mp
    away_attack = away_stats["goals_for"] / away_mp
    away_defense = away_stats["goals_against"] / away_mp
    league_avg = base / 2.0

    home_attack_ratio = home_attack / league_avg if league_avg > 0 else 1.0
    away_attack_ratio = away_attack / league_avg if league_avg > 0 else 1.0
    home_defense_ratio = home_defense / league_avg if league_avg > 0 else 1.0
    away_defense_ratio = away_defense / league_avg if league_avg > 0 else 1.0

    home_attack_factor = (home_attack_ratio + 0.5) / (away_defense_ratio + 0.5)
    away_attack_factor = (away_attack_ratio + 0.5) / (home_defense_ratio + 0.5)

    home_xg *= (0.75 + 0.25 * home_attack_factor)
    away_xg *= (0.75 + 0.25 * away_attack_factor)

    # === FORME ===
    def form_factor(form_str):
        if not form_str:
            return 1.0
        wins = form_str.upper().count("W")
        draws = form_str.upper().count("D")
        total = len(form_str)
        if total == 0:
            return 1.0
        points = wins * 3 + draws
        max_points = total * 3
        ratio = points / max_points if max_points > 0 else 0.5
        return 0.90 + (ratio * 0.20)

    home_xg *= form_factor(home_stats["form"] or "")
    away_xg *= form_factor(away_stats["form"] or "")

    # === Plancher 0.6 ===
    home_xg = max(0.6, min(3.0, round(home_xg, 2)))
    away_xg = max(0.6, min(3.0, round(away_xg, 2)))

    total = home_xg + away_xg
    if total > 4.5:
        ratio = 4.5 / total
        home_xg = round(home_xg * ratio, 2)
        away_xg = round(away_xg * ratio, 2)

    return home_xg, away_xg
    
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


def predict_extended_markets(home_xg, away_xg, home_win, draw, away_win):
    MAX_GOALS = 8
    score_probs = {}
    for h in range(MAX_GOALS + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(MAX_GOALS + 1):
            p_a = poisson_prob(a, away_xg)
            score_probs[(h, a)] = p_h * p_a

    dc_1x = home_win + draw
    dc_12 = home_win + away_win
    dc_x2 = draw + away_win

    dnb_home = home_win / (home_win + away_win) if (home_win + away_win) > 0 else 0
    dnb_away = away_win / (home_win + away_win) if (home_win + away_win) > 0 else 0

    over_05 = 1 - score_probs.get((0, 0), 0)
    under_05 = score_probs.get((0, 0), 0)

    btts_yes = (1 - poisson_prob(0, home_xg)) * (1 - poisson_prob(0, away_xg))

    btts_over_25 = 0.0
    btts_under_35 = 0.0
    for (h, a), p in score_probs.items():
        if h > 0 and a > 0:
            if (h + a) > 2.5:
                btts_over_25 += p
            if (h + a) < 3.5:
                btts_under_35 += p

    handicap_home_minus1 = sum(p for (h, a), p in score_probs.items() if h - a >= 2)
    handicap_away_minus1 = sum(p for (h, a), p in score_probs.items() if a - h >= 2)
    handicap_home_plus1 = sum(p for (h, a), p in score_probs.items() if h - a >= -1)
    handicap_away_plus1 = sum(p for (h, a), p in score_probs.items() if a - h >= -1)
    handicap_home_minus2 = sum(p for (h, a), p in score_probs.items() if h - a >= 3)
    handicap_away_minus2 = sum(p for (h, a), p in score_probs.items() if a - h >= 3)

    total_xg = home_xg + away_xg
    first_half_goal = 1 - math.exp(-0.45 * total_xg)

    # Over 1.5 buts en 1ere MT (45% des buts en 1ere MT)
    h_xg_1mt = home_xg * 0.45
    a_xg_1mt = away_xg * 0.45
    p_h_0_1mt = math.exp(-h_xg_1mt)
    p_h_1_1mt = h_xg_1mt * math.exp(-h_xg_1mt)
    p_a_0_1mt = math.exp(-a_xg_1mt)
    p_a_1_1mt = a_xg_1mt * math.exp(-a_xg_1mt)
    prob_under_15_1mt = (p_h_0_1mt + p_h_1_1mt) * (p_a_0_1mt + p_a_1_1mt)
    first_half_over_15 = 1 - prob_under_15_1mt

    top_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:3]
    exact_scores = [{"score": str(h) + "-" + str(a), "prob": round(p, 3)} for (h, a), p in top_scores]

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
        "btts_over_25": round(btts_over_25, 3),
        "btts_under_35": round(btts_under_35, 3),
        "handicap_home_minus1": round(handicap_home_minus1, 3),
        "handicap_away_minus1": round(handicap_away_minus1, 3),
        "handicap_home_plus1": round(handicap_home_plus1, 3),
        "handicap_away_plus1": round(handicap_away_plus1, 3),
        "handicap_home_minus2": round(handicap_home_minus2, 3),
        "handicap_away_minus2": round(handicap_away_minus2, 3),
        "first_half_goal": round(first_half_goal, 3),
        "first_half_over_15": round(first_half_over_15, 3),
        "exact_scores": json.dumps(exact_scores),
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

async def fetch_apisports_matches(league_id: int, season: int, date_from: str, date_to: str):
    """Récupère les matchs d'une compétition via API-Sports."""
    url = f"https://{APISPORTS_HOST}/fixtures"
    headers = {"x-apisports-key": APISPORTS_KEY}
    params = {"league": league_id, "season": season, "from": date_from, "to": date_to}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code != 200:
                print(f"Erreur API-Sports {league_id}: {r.status_code}")
                return []
            return r.json().get("response", [])
    except Exception as e:
        print(f"Exception API-Sports {league_id}: {e}")
        return []

THESPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

async def fetch_thesportsdb_europa_league(season: str, date_from: str, date_to: str):
    """
    Recupere les matchs de l'Europa League via TheSportsDB (gratuit).
    season au format '2025-2026'.
    """
    url = f"{THESPORTSDB_BASE}/eventsseason.php"
    params = {"id": 4481, "s": season}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                print(f"Erreur TheSportsDB EL : {r.status_code}")
                return []
            data = r.json()
            events = data.get("events") or []
            # Filtre par date
            filtered = []
            for ev in events:
                ev_date = ev.get("dateEvent")
                if ev_date and date_from <= ev_date <= date_to:
                    filtered.append(ev)
            return filtered
    except Exception as e:
        print(f"Exception TheSportsDB EL : {e}")
        return []

async def fetch_zafronix_mls(season: int, date_from: str, date_to: str):
    """
    Recupere les matchs de la MLS via Zafronix.
    L'endpoint renvoie toute la saison, on filtre par date cote Python.
    """
    if not ZAFRONIX_API_KEY:
        print("ZAFRONIX_API_KEY non definie")
        return []

    url = f"{ZAFRONIX_BASE_URL_MLS}/matches"
    headers = {"X-API-Key": ZAFRONIX_API_KEY}
    params = {"season": season}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code != 200:
                print(f"Erreur Zafronix MLS : {r.status_code}")
                return []

            data = r.json()
            events = data.get("matches") or data.get("data") or data

            filtered = []
            for ev in events:
                ev_date = ev.get("date") or ev.get("utcDate") or ""
                if ev_date and date_from <= ev_date[:10] <= date_to:
                    filtered.append(ev)

            print(f"Zafronix MLS : {len(events)} matchs recus, {len(filtered)} dans la fenetre")
            return filtered

    except Exception as e:
        print(f"Exception Zafronix MLS : {e}")
        return []

async def daily_pipeline():
    global _PIPELINE_RUNNING
    if _PIPELINE_RUNNING:
        print("=== Pipeline deja en cours, SKIP ===")
        return
    _PIPELINE_RUNNING = True
    try:
        print(f"=== Pipeline {datetime.now().isoformat()} ===")
        today = date.today()
        date_from = today.isoformat()
        date_to = (today + timedelta(days=DAYS_AHEAD)).isoformat()

        all_matches = []
        for code in COMPETITIONS:
            matches = await fetch_competition_matches(code, date_from, date_to)
            for m in matches:
                m["_code"] = code
            all_matches.extend(matches)
            await asyncio.sleep(7)

        # API-Sports (Champions League etc.)
        season = today.year
        if today.month < 7:
            season -= 1
        for code, league_id in API_FOOTBALL_LEAGUES.items():
            league_name = COMPETITIONS.get(code, code)
            try:
                api_matches = await fetch_apisports_matches(league_id, season, date_from, date_to)
                converted = convert_apisports_to_internal(api_matches, code, league_name)
                all_matches.extend(converted)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"Erreur API-Sports {code}: {e}")

# Dans daily_pipeline, après l'appel a l'Europa League :
if ZAFRONIX_API_KEY:
    try:
        mls_season = today.year  # La MLS est une saison annuelle (ex: 2026)
        mls_events = await fetch_zafronix_mls(mls_season, date_from, date_to)
        converted = convert_zafronix_to_internal(mls_events, "MLS", "Major League Soccer")
        all_matches.extend(converted)
        await asyncio.sleep(1)
    except Exception as e:
        print(f"Erreur Zafronix MLS: {e}")
        # Pause avant les standings (limite 10/min)
        await asyncio.sleep(10)

        print("Recuperation des stats d'equipes...")
        for code, league_name in COMPETITIONS.items():
            try:
                await fetch_team_stats(code, league_name)
                await asyncio.sleep(7)
            except Exception as e:
                print(f"Erreur stats {code}: {e}")

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
                ht_home = m.get("score", {}).get("halfTime", {}).get("home")
                ht_away = m.get("score", {}).get("halfTime", {}).get("away")

                home_xg, away_xg = calc_expected_goals_v2(code, home, away)
                pred = predict_all_markets(home_xg, away_xg)
                ext = predict_extended_markets(
                    home_xg, away_xg,
                    pred["home_win"], pred["draw"], pred["away_win"]
                )

                conn.execute(
                    """
                    INSERT OR REPLACE INTO matches
                    (id, league, country, home, away, home_logo, away_logo,
                     kickoff, status, home_goals, away_goals,
                     ht_home_goals, ht_away_goals,
                     home_win, draw, away_win, over_15, under_15, over_25, under_25,
                     over_35, under_35, over_45, under_45, btts_yes, btts_no,
                     first_half_goal, handicap_home_1, handicap_away_1,
                     dc_1x, dc_12, dc_x2, dnb_home, dnb_away,
                     over_05, under_05, btts_over_25, btts_under_35,
                     handicap_home_minus1, handicap_away_minus1,
                     handicap_home_plus1, handicap_away_plus1,
                     handicap_home_minus2, handicap_away_minus2,
                     first_half_over_15,
                     exact_scores, home_scores, away_scores,
                     home_xg, away_xg, total_xg, confidence, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match_id, league, country, home, away,
                        logos.get(home, ""), logos.get(away, ""),
                        kickoff, status, home_goals, away_goals,
                        ht_home, ht_away,
                        pred["home_win"], pred["draw"], pred["away_win"],
                        pred["over_15"], pred["under_15"],
                        pred["over_25"], pred["under_25"],
                        pred["over_35"], pred["under_35"],
                        pred["over_45"], pred["under_45"],
                        pred["btts_yes"], pred["btts_no"],
                        pred["first_half_goal"],
                        pred["handicap_home_1"], pred["handicap_away_1"],
                        ext["dc_1x"], ext["dc_12"], ext["dc_x2"],
                        ext["dnb_home"], ext["dnb_away"],
                        ext["over_05"], ext["under_05"],
                        ext["btts_over_25"], ext["btts_under_35"],
                        ext["handicap_home_minus1"], ext["handicap_away_minus1"],
                        ext["handicap_home_plus1"], ext["handicap_away_plus1"],
                        ext["handicap_home_minus2"], ext["handicap_away_minus2"],
                        ext["first_half_over_15"],
                        ext["exact_scores"], ext["home_scores"], ext["away_scores"],
                        pred["home_xg"], pred["away_xg"], pred["total_xg"],
                        pred["confidence"],
                        datetime.now().isoformat(),
                    ),
                )
                inserted += 1
            except Exception as e:
                print("Erreur match " + str(m.get("id")) + ": " + str(e))

        conn.commit()
        conn.close()
        print(str(inserted) + " matchs enregistres")
        mark_free_access()
    finally:
        _PIPELINE_RUNNING = False
        print("=== Pipeline termine ===")
    
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


# ===== TICKETS =====

def _all_picks_for_match(m):
    markets = [
        ("1", m.get("home_win"), m["home"]),
        ("X", m.get("draw"), "Match nul"),
        ("2", m.get("away_win"), m["away"]),
        ("+0.5", m.get("over_05"), "Over 0.5 but"),
        ("+1.5", m.get("over_15"), "+1.5 buts"),
        ("+2.5", m.get("over_25"), "+2.5 buts"),
        ("-3.5", m.get("under_35"), "-3.5 buts"),
        ("-4.5", m.get("under_45"), "-4.5 buts"),
        ("BTTS", m.get("btts_yes"), "Les 2 equipes marquent"),
        ("1MT", m.get("first_half_goal"), "But en 1ere MT"),
        ("1X", m.get("dc_1x"), "Double Chance 1X"),
        ("12", m.get("dc_12"), "Double Chance 12"),
        ("X2", m.get("dc_x2"), "Double Chance X2"),
        ("DNB D", m.get("dnb_home"), "Draw No Bet Domicile"),
        ("DNB E", m.get("dnb_away"), "Draw No Bet Exterieur"),
        ("BTTS+2.5", m.get("btts_over_25"), "BTTS & Over 2.5"),
        ("BTTS-3.5", m.get("btts_under_35"), "BTTS & Under 3.5"),
        ("H-1 D", m.get("handicap_home_minus1"), "Handicap -1 Domicile"),
        ("H-1 E", m.get("handicap_away_minus1"), "Handicap -1 Exterieur"),
        ("H+1 D", m.get("handicap_home_plus1"), "Handicap +1 Domicile"),
        ("H+1 E", m.get("handicap_away_plus1"), "Handicap +1 Exterieur"),
        ("Dom. marque", m.get("home_scores"), "Domicile marque"),
        ("Ext. marque", m.get("away_scores"), "Exterieur marque"),
    ]
    picks = []
    for label, prob, desc in markets:
        if prob is None:
            continue
        if prob < 0.40 or prob > 0.85:
            continue
        cote = 1.0 / prob
        if cote < 1.20 or cote > 2.50:
            continue
        picks.append({
            "match_id": m["id"], "home": m["home"], "away": m["away"],
            "league": m["league"], "kickoff": m["kickoff"],
            "home_logo": m["home_logo"], "away_logo": m["away_logo"],
            "market": label, "description": desc,
            "proba": round(prob, 3), "cote": round(cote, 2),
        })
    return picks


def _calc_total_cote(picks):
    c = 1.0
    for p in picks:
        c *= p["cote"]
    return round(c, 2)


def _build_ticket(pool, target_cote, min_n, max_n):
    if not pool:
        return []
    best = []
    best_diff = float('inf')
    for n in range(min_n, max_n + 1):
        if n > len(pool):
            break
        avg_needed = target_cote ** (1.0 / n)
        sorted_pool = sorted(pool, key=lambda p: abs(p["cote"] - avg_needed))
        combo = []
        used = set()
        for p in sorted_pool:
            if p["match_id"] in used:
                continue
            combo.append(p)
            used.add(p["match_id"])
            if len(combo) >= n:
                break
        if len(combo) < n:
            continue
        cote = _calc_total_cote(combo)
        diff = abs(cote - target_cote)
        if diff < best_diff:
            best_diff = diff
            best = combo
    return best

def convert_apisports_to_internal(api_matches: list, league_code: str, league_name: str) -> list:
    """Convertit le format API-Sports vers le format interne (football-data.org)."""
    converted = []
    for match in api_matches:
        try:
            fixture = match.get("fixture", {})
            teams = match.get("teams", {})
            status_short = fixture.get("status", {}).get("short", "NS")
            # On ne garde que les matchs à venir ou en cours
            if status_short not in ["NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P"]:
                continue
            internal_match = {
                "id": fixture.get("id"),
                "homeTeam": {
                    "name": teams.get("home", {}).get("name"),
                    "crest": teams.get("home", {}).get("logo"),
                },
                "awayTeam": {
                    "name": teams.get("away", {}).get("name"),
                    "crest": teams.get("away", {}).get("logo"),
                },
                "utcDate": fixture.get("date"),
                "status": "SCHEDULED" if status_short in ["NS", "TBD"] else "IN_PLAY",
                "score": {"fullTime": {"home": None, "away": None}},
                "league": {"name": league_name, "country": "Europe"},
                "_code": league_code,
            }
            converted.append(internal_match)
        except Exception as e:
            print(f"Erreur conversion match {match.get('fixture', {}).get('id')}: {e}")
    return converted

def convert_thesportsdb_to_internal(events: list, league_code: str, league_name: str) -> list:
    """Convertit le format TheSportsDB vers le format interne (football-data.org)."""
    converted = []
    for ev in events:
        try:
            # Statut
            status_str = (ev.get("strStatus") or "").upper()
            if status_str in ["FT", "AET", "PEN", "FINISHED"]:
                status = "FINISHED"
            elif status_str in ["1H", "2H", "HT", "LIVE"]:
                status = "IN_PLAY"
            else:
                status = "SCHEDULED"

            home_team = ev.get("strHomeTeam") or "?"
            away_team = ev.get("strAwayTeam") or "?"
            home_score = ev.get("intHomeScore")
            away_score = ev.get("intAwayScore")

            # Date au format ISO
            date_str = ev.get("dateEvent")
            time_str = ev.get("strTime") or "00:00:00"
            kickoff = f"{date_str}T{time_str}Z" if date_str else None

            internal_match = {
                "id": int(ev.get("idEvent", 0)),
                "homeTeam": {"name": home_team, "crest": ev.get("strHomeTeamBadge")},
                "awayTeam": {"name": away_team, "crest": ev.get("strAwayTeamBadge")},
                "utcDate": kickoff,
                "status": status,
                "score": {
                    "fullTime": {"home": int(home_score) if home_score else None,
                                 "away": int(away_score) if away_score else None}
                },
                "league": {"name": league_name, "country": "Europe"},
                "_code": league_code,
            }
            converted.append(internal_match)
        except Exception as e:
            print(f"Erreur conversion TheSportsDB {ev.get('idEvent')}: {e}")
    return converted

async def fetch_top_teams(code: str, top_n: int):
    """Recupere les N premiers noms d'equipes d'un championnat (cache 24h)."""
    cached = _STANDINGS_CACHE.get(code)
    if cached:
        age = (datetime.now() - cached["timestamp"]).total_seconds()
        if age < 86400:
            return cached["top_teams"]

    url = BASE_URL + "/competitions/" + code + "/standings"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=HEADERS)
            increment_count()
            if r.status_code != 200:
                print("Erreur standings " + code + " : " + str(r.status_code))
                return []
            data = r.json()
            standings = data.get("standings", [])
            for s in standings:
                if s.get("type") == "TOTAL":
                    table = s.get("table", [])
                    top_teams = []
                    for row in table[:top_n]:
                        team_name = row.get("team", {}).get("name", "")
                        if team_name:
                            top_teams.append(team_name)
                    _STANDINGS_CACHE[code] = {
                        "timestamp": datetime.now(),
                        "top_teams": top_teams,
                    }
                    print("Top " + str(top_n) + " " + code + " : " + str(top_teams))
                    return top_teams
    except Exception as e:
        print("Exception standings " + code + " : " + str(e))
    return []

async def fetch_team_stats(code: str, league_name: str):
    """Recupere les stats de toutes les equipes d'un championnat (cache 24h)."""
    # Cache check
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) as c, MAX(cached_at) as last FROM team_stats WHERE league=?",
        (league_name,),
    ).fetchone()
    conn.close()

    if row and row["c"] > 0 and row["last"]:
        try:
            age = (datetime.now() - datetime.fromisoformat(row["last"])).total_seconds()
            if age < 86400:
                print(f"Stats {league_name} en cache ({row['c']} equipes)")
                return
        except Exception:
            pass

    # Fetch API
    url = BASE_URL + "/competitions/" + code + "/standings"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=HEADERS)
            increment_count()
            if r.status_code != 200:
                print(f"Erreur standings {code} : {r.status_code}")
                return
            data = r.json()
            standings = data.get("standings", [])
            for s in standings:
                if s.get("type") != "TOTAL":
                    continue
                table = s.get("table", [])
                conn = db()
                now = datetime.now().isoformat()
                for row_team in table:
                    team_name = row_team.get("team", {}).get("name", "")
                    if not team_name:
                        continue
                    conn.execute("""
                        INSERT OR REPLACE INTO team_stats
                        (team, league, matches_played, wins, draws, losses,
                         goals_for, goals_against, goals_for_home, goals_against_home,
                         goals_for_away, goals_against_away, points, form, cached_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        team_name, league_name,
                        row_team.get("playedGames", 0),
                        row_team.get("won", 0),
                        row_team.get("draw", 0),
                        row_team.get("lost", 0),
                        row_team.get("goalsFor", 0),
                        row_team.get("goalsAgainst", 0),
                        row_team.get("goalsFor", 0) // 2,   # estimation domicile
                        row_team.get("goalsAgainst", 0) // 2,
                        row_team.get("goalsFor", 0) - row_team.get("goalsFor", 0) // 2,
                        row_team.get("goalsAgainst", 0) - row_team.get("goalsAgainst", 0) // 2,
                        row_team.get("points", 0),
                        row_team.get("form", "") or "",
                        now,
                    ))
                conn.commit()
                conn.close()
                print(f"Stats {league_name} : {len(table)} equipes mises a jour")
                return
    except Exception as e:
        print(f"Exception standings {code} : {e}")
    
def _evaluate_pick(pick, match):
    """Evalue un pick selon l'etat actuel du match."""
    market = pick.get("market", "")
    status = match.get("status", "")
    hg = match.get("home_goals")
    ag = match.get("away_goals")
    ht_hg = match.get("ht_home_goals")
    ht_ag = match.get("ht_away_goals")

    if status in ["SCHEDULED", "TIMED"]:
        return {"result": "pending", "reason": "Match pas encore commence", "current_score": None}

    if status in ["IN_PLAY", "PAUSED"]:
        score_txt = str(hg) + "-" + str(ag) if hg is not None and ag is not None else "0-0"
        return {"result": "pending", "reason": "En cours " + score_txt, "current_score": score_txt}

    if status != "FINISHED":
        return {"result": "pending", "reason": "Statut inconnu", "current_score": None}

    if hg is None or ag is None:
        return {"result": "pending", "reason": "Score indisponible", "current_score": None}

    total = hg + ag
    won = False
    reason = ""

    if market == "1":
        won = hg > ag
        reason = str(hg) + "-" + str(ag) + (" victoire dom." if won else " defaite dom.")
    elif market == "X":
        won = hg == ag
        reason = "Score " + str(hg) + "-" + str(ag) + (" nul" if won else " pas nul")
    elif market == "2":
        won = hg < ag
        reason = str(hg) + "-" + str(ag) + (" victoire ext." if won else " defaite ext.")
    elif market == "+0.5":
        won = total > 0
        reason = str(total) + " but(s) au total"
    elif market == "+1.5":
        won = total > 1
        reason = str(total) + " but(s) au total (min 2)"
    elif market == "+2.5":
        won = total > 2
        reason = str(total) + " but(s) au total (min 3)"
    elif market == "+3.5":
        won = total > 3
        reason = str(total) + " but(s) au total (min 4)"
    elif market == "-2.5":
        won = total < 3
        reason = str(total) + " but(s) au total (max 2)"
    elif market == "-3.5":
        won = total < 4
        reason = str(total) + " but(s) au total (max 3)"
    elif market == "-4.5":
        won = total < 5
        reason = str(total) + " but(s) au total (max 4)"
    elif market == "BTTS":
        won = hg > 0 and ag > 0
        reason = "Score " + str(hg) + "-" + str(ag) + (" les 2 marquent" if won else " pas les 2")
    elif market == "1MT":
        if ht_hg is None or ht_ag is None:
            return {"result": "pending", "reason": "Mi-temps indisponible", "current_score": str(hg) + "-" + str(ag)}
        won = (ht_hg + ht_ag) > 0
        reason = "Mi-temps " + str(ht_hg) + "-" + str(ht_ag) + (" but oui" if won else " 0-0")
    elif market == "+1.5 1MT":
        if ht_hg is None or ht_ag is None:
            return {"result": "pending", "reason": "Mi-temps indisponible", "current_score": str(hg) + "-" + str(ag)}
        won = (ht_hg + ht_ag) > 1
        reason = "Mi-temps " + str(ht_hg) + "-" + str(ht_ag) + " (" + str(ht_hg + ht_ag) + " buts)"
    elif market == "1X":
        won = hg >= ag
        reason = "Score " + str(hg) + "-" + str(ag) + (" dom. ou nul" if won else " defaite dom.")
    elif market == "12":
        won = hg != ag
        reason = "Score " + str(hg) + "-" + str(ag) + (" pas nul" if won else " match nul")
    elif market == "X2":
        won = hg <= ag
        reason = "Score " + str(hg) + "-" + str(ag) + (" ext. ou nul" if won else " victoire dom.")
    elif market == "DNB D":
        won = hg > ag
        reason = "Score " + str(hg) + "-" + str(ag)
    elif market == "DNB E":
        won = hg < ag
        reason = "Score " + str(hg) + "-" + str(ag)
    elif market == "H-1 D":
        won = hg - ag >= 2
        reason = "Ecart " + str(hg - ag) + " (min 2)"
    elif market == "H-1 E":
        won = ag - hg >= 2
        reason = "Ecart " + str(ag - hg) + " (min 2)"
    elif market == "H-2 D":
        won = hg - ag >= 3
        reason = "Ecart " + str(hg - ag) + " (min 3)"
    elif market == "H-2 E":
        won = ag - hg >= 3
        reason = "Ecart " + str(ag - hg) + " (min 3)"
    elif market == "H+1 D":
        won = hg - ag >= -1
        reason = "Ecart " + str(hg - ag) + " (min -1)"
    elif market == "H+1 E":
        won = ag - hg >= -1
        reason = "Ecart " + str(ag - hg) + " (min -1)"
    elif market == "Dom. marque":
        won = hg > 0
        reason = "Dom. " + str(hg) + " but(s)"
    elif market == "Ext. marque":
        won = ag > 0
        reason = "Ext. " + str(ag) + " but(s)"
    else:
        return {"result": "pending", "reason": "Marche non evaluable", "current_score": str(hg) + "-" + str(ag)}

    return {
        "result": "won" if won else "lost",
        "reason": reason,
        "current_score": str(hg) + "-" + str(ag),
    }
    
def _calc_risky_pick(m):
    """Choisit le pick risky selon criteres metier, en preferant la cible ~1.80-2.20."""
    hw = m.get("home_win") or 0
    d = m.get("draw") or 0
    aw = m.get("away_win") or 0
    over_25 = m.get("over_25") or 0
    over_35 = m.get("over_35") or 0
    under_25 = m.get("under_25") or 0
    btts = m.get("btts_yes") or 0
    fh_goal = m.get("first_half_goal") or 0
    fh_over_15 = m.get("first_half_over_15") or 0
    hcp2_home = m.get("handicap_home_minus2") or 0
    hcp2_away = m.get("handicap_away_minus2") or 0
    home_xg = m.get("home_xg") or 0
    away_xg = m.get("away_xg") or 0
    total_xg = m.get("total_xg") or 0

    candidates = []

    # 1. V1 ou V2 si proba >= 75%
    if hw >= 0.75:
        candidates.append(("1", m["home"], hw, 1.0 / hw))
    if aw >= 0.75:
        candidates.append(("2", m["away"], aw, 1.0 / aw))

    # 2. X si les 2 equipes faibles en attaque
    if home_xg < 1.3 and away_xg < 1.3 and hw < 0.40 and aw < 0.40 and d >= 0.28:
        candidates.append(("X", "Match nul", d, 1.0 / d))

    # 3. Handicap -2 si favori largement superieur
    if hw > 0.70 and home_xg > 1.9 and away_xg < 1.0 and hcp2_home > 0.28:
        candidates.append(("H-2 D", "Handicap -2 " + m["home"], hcp2_home, 1.0 / hcp2_home))
    if aw > 0.70 and away_xg > 1.9 and home_xg < 1.0 and hcp2_away > 0.28:
        candidates.append(("H-2 E", "Handicap -2 " + m["away"], hcp2_away, 1.0 / hcp2_away))

    # 4. +2.5 buts si cote 1.4-1.6
    if 0.62 <= over_25 <= 0.72:
        candidates.append(("+2.5", "+2.5 buts", over_25, 1.0 / over_25))

    # 5. BTTS si cote 1.3-1.8
    if 0.55 <= btts <= 0.77:
        candidates.append(("BTTS", "Les 2 equipes marquent", btts, 1.0 / btts))

    # 6. +3.5 buts SEULEMENT si 2 attaques fortes (plus strict)
    if total_xg > 3.8 and over_35 > 0.50:
        candidates.append(("+3.5", "+3.5 buts", over_35, 1.0 / over_35))

    # 7. But en 1ere MT si probable
    if fh_goal >= 0.65:
        candidates.append(("1MT", "But en 1ere MT", fh_goal, 1.0 / fh_goal))

    # 8. +1.5 1ere MT SEULEMENT si match tres offensif (plus strict qu'avant)
    if total_xg > 3.8 and fh_over_15 >= 0.45:
        candidates.append(("+1.5 1MT", "+1.5 buts 1ere MT", fh_over_15, 1.0 / fh_over_15))

    # 9. -2.5 buts si match ferme
    if total_xg < 2.3 and under_25 > 0.55:
        candidates.append(("-2.5", "-2.5 buts", under_25, 1.0 / under_25))

    if not candidates:
        return None

    # Prend la cote la PLUS PROCHE de 2.0 (compromis risque/gain)
    best = min(candidates, key=lambda x: abs(x[3] - 2.0))

    return {
        "match_id": m["id"], "home": m["home"], "away": m["away"],
        "league": m["league"], "kickoff": m["kickoff"],
        "home_logo": m["home_logo"], "away_logo": m["away_logo"],
        "market": best[0], "description": best[1],
        "proba": round(best[2], 3), "cote": round(best[3], 2),
    }

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
    return {"status": "ok", "app": "SportIA Predict", "version": "3.0"}


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
    if m.get("exact_scores"):
        try:
            m["exact_scores"] = json.loads(m["exact_scores"])
        except Exception:
            m["exact_scores"] = []
    m["analysis"] = generate_analysis(m)
    return m


@app.get("/leagues")
def get_leagues():
    conn = db()
    rows = conn.execute("SELECT DISTINCT league FROM matches").fetchall()
    conn.close()
    return [r["league"] for r in rows]


@app.get("/tickets/{day}")
def get_tickets(day: str):
    """Genere les 3 tickets avec evaluation gagne/perdu/en attente."""
    try:
        conn = db()
        rows = conn.execute(
            "SELECT * FROM matches WHERE date(kickoff)=? ORDER BY kickoff ASC", (day,)
        ).fetchall()
        conn.close()

        if not rows:
            return {"error": "Aucun match pour cette date", "date": day}

        # Collecte des picks
        all_picks = []
        for r in rows:
            m = dict(r)
            try:
                all_picks.extend(_all_picks_for_match(m))
            except Exception:
                pass

        if not all_picks:
            return {"error": "Aucun pick disponible", "date": day}

        # SAFE
        try:
            safe = _build_ticket(all_picks, 2.0, 2, 3)
            if safe is None or not isinstance(safe, list):
                safe = []
        except Exception:
            safe = []

        safe_ids = {p["match_id"] for p in safe}

        # MEDIUM
        try:
            medium_pool = [p for p in all_picks if p["match_id"] not in safe_ids]
            medium = _build_ticket(medium_pool, 120.0, 4, 15)
            if medium is None or not isinstance(medium, list):
                medium = []
        except Exception:
            medium = []

        # RISKY
        risky_list = []
        try:
            risky_picks = []
            used_ids = set()
            market_count = {}
            MAX_PER_MARKET = 3

            for r in rows:
                m = dict(r)
                try:
                    pick = _calc_risky_pick(m)
                except Exception:
                    pick = None
                if not pick:
                    continue
                mk = pick["market"]
                if market_count.get(mk, 0) >= MAX_PER_MARKET:
                    continue
                risky_picks.append(pick)
                used_ids.add(m["id"])
                market_count[mk] = market_count.get(mk, 0) + 1

            if len(risky_picks) < 8:
                for r in rows:
                    m = dict(r)
                    if m["id"] in used_ids:
                        continue
                    best_pick = None
                    best_dist = 999
                    for label, prob, desc in [
                        ("+2.5", m.get("over_25"), "+2.5 buts"),
                        ("+3.5", m.get("over_35"), "+3.5 buts"),
                        ("BTTS", m.get("btts_yes"), "Les 2 equipes marquent"),
                        ("1MT", m.get("first_half_goal"), "But en 1ere MT"),
                        ("-2.5", m.get("under_25"), "-2.5 buts"),
                        ("+1.5 1MT", m.get("first_half_over_15"), "+1.5 1ere MT"),
                    ]:
                        if not prob:
                            continue
                        try:
                            cote = 1.0 / prob
                        except Exception:
                            continue
                        if cote < 1.30 or cote > 3.5:
                            continue
                        if market_count.get(label, 0) >= MAX_PER_MARKET:
                            continue
                        dist = abs(cote - 2.0)
                        if dist < best_dist:
                            best_dist = dist
                            best_pick = {
                                "match_id": m["id"], "home": m["home"], "away": m["away"],
                                "league": m["league"], "kickoff": m["kickoff"],
                                "home_logo": m["home_logo"], "away_logo": m["away_logo"],
                                "market": label, "description": desc,
                                "proba": round(prob, 3), "cote": round(cote, 2),
                            }
                    if best_pick:
                        risky_picks.append(best_pick)
                        used_ids.add(m["id"])
                        mk = best_pick["market"]
                        market_count[mk] = market_count.get(mk, 0) + 1

            if len(risky_picks) < 3:
                for r in rows:
                    m = dict(r)
                    if m["id"] in used_ids:
                        continue
                    prob = m.get("over_15")
                    if prob:
                        risky_picks.append({
                            "match_id": m["id"], "home": m["home"], "away": m["away"],
                            "league": m["league"], "kickoff": m["kickoff"],
                            "home_logo": m["home_logo"], "away_logo": m["away_logo"],
                            "market": "+1.5", "description": "+1.5 buts",
                            "proba": round(prob, 3), "cote": round(1.0 / prob, 2),
                        })
                        used_ids.add(m["id"])

            risky_result = _build_ticket(risky_picks, 1500.0, 3, 20)
            if risky_result is None or not isinstance(risky_result, list):
                risky_result = risky_picks[:15] if risky_picks else []
            risky_list = risky_result
        except Exception as e:
            print(f"Erreur risky: {e}")
            risky_list = []

        # === ENRICHISSEMENT : evaluation de chaque pick ===
        match_map = {dict(r)["id"]: dict(r) for r in rows}

        def enrich_picks(picks):
            for p in picks:
                match = match_map.get(p["match_id"])
                if match:
                    try:
                        ev = _evaluate_pick(p, match)
                        p["result"] = ev["result"]
                        p["reason"] = ev["reason"]
                        p["current_score"] = ev["current_score"]
                        p["match_status"] = match.get("status")
                        p["kickoff"] = match.get("kickoff")
                    except Exception:
                        p["result"] = "pending"
                        p["reason"] = "Erreur evaluation"
                        p["current_score"] = None
                else:
                    p["result"] = "pending"
                    p["reason"] = "Match introuvable"
                    p["current_score"] = None
            return picks

        safe = enrich_picks(safe)
        medium = enrich_picks(medium)
        risky_list = enrich_picks(risky_list)

        def safe_cote(lst):
            try:
                return _calc_total_cote(lst) if lst else 1.0
            except Exception:
                return 1.0

        return {
            "date": day,
            "safe": {
                "name": "Ticket Safe",
                "total_cote": safe_cote(safe),
                "count": len(safe),
                "picks": safe,
            },
            "medium": {
                "name": "Ticket Medium",
                "total_cote": safe_cote(medium),
                "count": len(medium),
                "picks": medium,
            },
            "risky": {
                "name": "Ticket Risky",
                "total_cote": safe_cote(risky_list),
                "count": len(risky_list),
                "picks": risky_list,
            },
        }
    except Exception as e:
        print(f"Erreur get_tickets: {e}")
        return {
            "error": f"Erreur interne: {str(e)}",
            "date": day,
            "safe": {"name": "Ticket Safe", "total_cote": 1.0, "count": 0, "picks": []},
            "medium": {"name": "Ticket Medium", "total_cote": 1.0, "count": 0, "picks": []},
            "risky": {"name": "Ticket Risky", "total_cote": 1.0, "count": 0, "picks": []},
        }
# ===== PREDICTIONS JUSTES =====

def _check_won_markets(m):
    if m.get("status") != "FINISHED":
        return []
    hg = m.get("home_goals")
    ag = m.get("away_goals")
    if hg is None or ag is None:
        return []
    total = hg + ag
    won = []

    def add(label, desc, prob):
        if prob is None or prob < 0.55:
            return
        won.append({
            "market": label, "description": desc,
            "proba": round(prob, 3),
            "cote": round(1.0 / prob, 2) if prob > 0 else None,
        })

    if hg > ag:
        add("1", m["home"], m.get("home_win", 0))
    elif hg == ag:
        add("X", "Match nul", m.get("draw", 0))
    else:
        add("2", m["away"], m.get("away_win", 0))
    if total > 0.5:
        add("+0.5", "Over 0.5 but", m.get("over_05", 0))
    if total > 1.5:
        add("+1.5", "+1.5 buts", m.get("over_15", 0))
    if total > 2.5:
        add("+2.5", "+2.5 buts", m.get("over_25", 0))
    if total < 3.5:
        add("-3.5", "-3.5 buts", m.get("under_35", 0))
    if total < 4.5:
        add("-4.5", "-4.5 buts", m.get("under_45", 0))
    if hg > 0 and ag > 0:
        add("BTTS", "Les 2 marquent", m.get("btts_yes", 0))
        if total > 2.5:
            add("BTTS+2.5", "BTTS & Over 2.5", m.get("btts_over_25", 0))
        if total < 3.5:
            add("BTTS-3.5", "BTTS & Under 3.5", m.get("btts_under_35", 0))
    if hg >= ag:
        add("1X", "Double Chance 1X", m.get("dc_1x", 0))
    if hg != ag:
        add("12", "Double Chance 12", m.get("dc_12", 0))
    if hg <= ag:
        add("X2", "Double Chance X2", m.get("dc_x2", 0))
    if hg > ag:
        add("DNB D", "Draw No Bet Domicile", m.get("dnb_home", 0))
    elif hg < ag:
        add("DNB E", "Draw No Bet Exterieur", m.get("dnb_away", 0))
    if hg - ag >= 2:
        add("H-1 D", "Handicap -1 Domicile", m.get("handicap_home_minus1", 0))
    if ag - hg >= 2:
        add("H-1 E", "Handicap -1 Exterieur", m.get("handicap_away_minus1", 0))
    if hg - ag >= -1:
        add("H+1 D", "Handicap +1 Domicile", m.get("handicap_home_plus1", 0))
    if ag - hg >= -1:
        add("H+1 E", "Handicap +1 Exterieur", m.get("handicap_away_plus1", 0))
    if hg > 0:
        add("Dom. marque", "Domicile marque", m.get("home_scores", 0))
    if ag > 0:
        add("Ext. marque", "Exterieur marque", m.get("away_scores", 0))
    return won


@app.get("/predictions/won/{day}")
def get_won_predictions(day: str):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff)=? AND status='FINISHED' ORDER BY kickoff ASC",
        (day,),
    ).fetchall()
    conn.close()
    result = []
    total_won = 0
    for r in rows:
        m = dict(r)
        won = _check_won_markets(m)
        if won:
            total_won += len(won)
            result.append({
                "id": m["id"], "home": m["home"], "away": m["away"],
                "home_logo": m["home_logo"], "away_logo": m["away_logo"],
                "league": m["league"], "kickoff": m["kickoff"],
                "home_goals": m["home_goals"], "away_goals": m["away_goals"],
                "won_markets": won, "count": len(won),
            })
    return {
        "date": day, "total_finished": len(rows),
        "total_won_predictions": total_won, "matches": result,
    }


@app.get("/predictions/won-week")
def get_won_predictions_week():
    today = date.today()
    week_ago = (today - timedelta(days=7)).isoformat()
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff) BETWEEN ? AND ? "
        "AND status='FINISHED' ORDER BY kickoff DESC",
        (week_ago, today.isoformat()),
    ).fetchall()
    conn.close()
    by_day = {}
    total_won = 0
    for r in rows:
        m = dict(r)
        won = _check_won_markets(m)
        if won:
            total_won += len(won)
            day_key = m["kickoff"][:10]
            by_day.setdefault(day_key, []).append({
                "id": m["id"], "home": m["home"], "away": m["away"],
                "home_logo": m["home_logo"], "away_logo": m["away_logo"],
                "league": m["league"], "kickoff": m["kickoff"],
                "home_goals": m["home_goals"], "away_goals": m["away_goals"],
                "won_markets": won, "count": len(won),
            })
    return {
        "total_won_predictions": total_won,
        "total_finished": len(rows), "days": by_day,
    }


# ===== SCORES EN DIRECT =====

@app.get("/live-scores/{day}")
async def get_live_scores(day: str, refresh: bool = False):
    all_results = []
    for code in COMPETITIONS.keys():
        try:
            url = BASE_URL + "/competitions/" + code + "/matches"
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
    return all_results

# Force redeploy 2026-10-18 22:00

@app.get("/tickets-week")
async def get_tickets_week():
    """Ticket semaine : 1 pick par match eligible (top equipes)."""
    today = date.today()
    week_later = (today + timedelta(days=7)).isoformat()

    # 1. Top equipes
    top_teams_by_league = {}
    for code, top_n in LEAGUE_TOP_N.items():
        teams = await fetch_top_teams(code, top_n)
        top_teams_by_league[code] = set(teams)

    if not any(top_teams_by_league.values()):
        return {"error": "Standings indisponibles"}

    # 2. Matchs de la semaine
    conn = db()
    rows = conn.execute(
        "SELECT * FROM matches WHERE date(kickoff) BETWEEN ? AND ? ORDER BY kickoff ASC",
        (today.isoformat(), week_later),
    ).fetchall()
    conn.close()

    if not rows:
        return {"error": "Aucun match cette semaine"}

    # 3. Filtre : au moins une equipe top + match a venir
    eligible = []
    for r in rows:
        m = dict(r)
        status = m.get("status", "")
        if status not in ["SCHEDULED", "TIMED"]:
            continue
        league_name = m.get("league", "")
        code = None
        for c, name in COMPETITIONS.items():
            if name == league_name:
                code = c
                break
        if not code or code not in top_teams_by_league:
            continue
        top_teams = top_teams_by_league[code]
        home_top = m.get("home", "") in top_teams
        away_top = m.get("away", "") in top_teams
        if not home_top and not away_top:
            continue
        m["_code"] = code
        m["_home_top"] = home_top
        m["_away_top"] = away_top
        eligible.append(m)

    if not eligible:
        return {"error": "Aucun match avec equipe top cette semaine"}

    # 4. UN PICK PAR MATCH ELIGIBLE (minimum garanti)
    week_picks = []
    used_ids = set()
    market_count = {}
    MAX_PER_MARKET = 5  # plus permissif pour couvrir plus de matchs

    for m in eligible:
        pick = None

        # === Tentative 1 : _calc_risky_pick (logique risky) ===
        try:
            risky_pick = _calc_risky_pick(m)
            if risky_pick and risky_pick["cote"] <= 1.85:
                pick = risky_pick
        except Exception:
            pass

        # === Tentative 2 : fallback marches varies (cote 1.30-1.75) ===
        if not pick:
            best_pick = None
            best_dist = 999
            for label, prob, desc in [
                ("+1.5", m.get("over_15"), "+1.5 buts"),
                ("+2.5", m.get("over_25"), "+2.5 buts"),
                ("+3.5", m.get("over_35"), "+3.5 buts"),
                ("-2.5", m.get("under_25"), "-2.5 buts"),
                ("-3.5", m.get("under_35"), "-3.5 buts"),
                ("BTTS", m.get("btts_yes"), "Les 2 equipes marquent"),
                ("1MT", m.get("first_half_goal"), "But en 1ere MT"),
                ("+1.5 1MT", m.get("first_half_over_15"), "+1.5 1ere MT"),
                ("1X", m.get("dc_1x"), "Double Chance 1X"),
                ("12", m.get("dc_12"), "Double Chance 12"),
                ("X2", m.get("dc_x2"), "Double Chance X2"),
                ("DNB D", m.get("dnb_home"), "Draw No Bet Domicile"),
                ("DNB E", m.get("dnb_away"), "Draw No Bet Exterieur"),
                ("H+1 D", m.get("handicap_home_plus1"), "Handicap +1 Domicile"),
                ("H+1 E", m.get("handicap_away_plus1"), "Handicap +1 Exterieur"),
                ("Dom. marque", m.get("home_scores"), "Domicile marque"),
                ("Ext. marque", m.get("away_scores"), "Exterieur marque"),
            ]:
                if not prob:
                    continue
                try:
                    cote = 1.0 / prob
                except Exception:
                    continue
                if cote < 1.20 or cote > 1.80:
                    continue
                # Bonus pour les marches pas encore satures
                saturation = market_count.get(label, 0)
                if saturation >= MAX_PER_MARKET:
                    continue
                # Cible ~1.50 avec penalite si marche sature
                dist = abs(cote - 1.50) + (saturation * 0.1)
                if dist < best_dist:
                    best_dist = dist
                    best_pick = {
                        "match_id": m["id"], "home": m["home"], "away": m["away"],
                        "league": m["league"], "kickoff": m["kickoff"],
                        "home_logo": m["home_logo"], "away_logo": m["away_logo"],
                        "market": label, "description": desc,
                        "proba": round(prob, 3), "cote": round(cote, 2),
                    }
            pick = best_pick

        # === Tentative 3 : dernier recours, n'importe quel marche safe ===
        if not pick:
            for label, prob, desc in [
                ("+1.5", m.get("over_15"), "+1.5 buts"),
                ("1X", m.get("dc_1x"), "Double Chance 1X"),
                ("Dom. marque", m.get("home_scores"), "Domicile marque"),
                ("Ext. marque", m.get("away_scores"), "Exterieur marque"),
            ]:
                if not prob:
                    continue
                try:
                    cote = 1.0 / prob
                except Exception:
                    continue
                if cote < 1.10 or cote > 2.10:
                    continue
                pick = {
                    "match_id": m["id"], "home": m["home"], "away": m["away"],
                    "league": m["league"], "kickoff": m["kickoff"],
                    "home_logo": m["home_logo"], "away_logo": m["away_logo"],
                    "market": label, "description": desc,
                    "proba": round(prob, 3), "cote": round(cote, 2),
                }
                break

        if pick:
            week_picks.append(pick)
            used_ids.add(m["id"])
            mk = pick["market"]
            market_count[mk] = market_count.get(mk, 0) + 1

    if not week_picks:
        return {"error": "Aucun pick trouve"}

    # 5. Enrichit avec evaluation
    match_map = {dict(r)["id"]: dict(r) for r in rows}
    for p in week_picks:
        match = match_map.get(p["match_id"])
        if match:
            try:
                ev = _evaluate_pick(p, match)
                p["result"] = ev["result"]
                p["reason"] = ev["reason"]
                p["current_score"] = ev["current_score"]
                p["match_status"] = match.get("status")
            except Exception:
                p["result"] = "pending"
                p["reason"] = "Erreur evaluation"
                p["current_score"] = None
        else:
            p["result"] = "pending"
            p["reason"] = "Match introuvable"
            p["current_score"] = None

    return {
        "week_start": today.isoformat(),
        "week_end": week_later,
        "total_eligible_matches": len(eligible),
        "total_picks": len(week_picks),
        "total_cote": _calc_total_cote(week_picks) if week_picks else 1.0,
        "picks": week_picks,
        "markets_used": dict(market_count),
        "top_teams": {code: list(teams) for code, teams in top_teams_by_league.items()},
    }

@app.post("/refresh")
async def manual_refresh():
    await daily_pipeline()
    return {"status": "refreshed", "days_ahead": DAYS_AHEAD}
