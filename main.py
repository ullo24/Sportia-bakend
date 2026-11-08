import os
import math
import json
import psycopg2
import psycopg2.extras
import asyncio
import httpx
import hashlib
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel


load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_KEY")
if not API_KEY:
    print("ATTENTION : FOOTBALL_DATA_KEY n'est pas definie !")

# ===== FOOTBALL-CHARTS.COM CONFIG =====
FC_API_KEY = os.getenv("FC_API_KEY")
FC_BASE_URL = "https://footballcharts-backend.onrender.com/api/v1"
FC_LEAGUES = {
    "SAU": "saudi1",
    "JPN": "japan1",
    "KOR": "korea1",
}


# ===== GOAL API CONFIG (Argentine + Chine) =====
GOAL_API_KEY = os.getenv("GOAL_API_KEY")
GOAL_API_BASE_URL = "https://api.goal-api.com/v1"
GOAL_API_LEAGUES = {
    "ARG": "cmr77dvtc0093rx0667jirsnv",
    "CHN": "cmr77dvlv0067rx06potai161",
    # 👇 Ajoute ces deux lignes pour les compétitions africaines
    "AFCON": "cmr77dvhf0015rx069i57rsbo",      # Coupe d'Afrique des Nations
    "AFCON_Q": "cmr77dvhg001srx060axumqos",    # Qualifications CAN
}

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY or ""}
# Configuration de la base de données
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("⚠️ ATTENTION : DATABASE_URL n'est pas définie. La base va planter.")

# Plus besoin de DB_PATH = "/tmp/sportia.db"

#DB_PATH = "/tmp/sportia.db"
_PIPELINE_RUNNING = False

# Cache pour les ETags Zafronix (URL -> ETag)
_ZAFRONIX_ETAG_CACHE = {}
# Zafronix
ZAFRONIX_API_KEY = os.getenv("ZAFRONIX_API_KEY")
ZAFRONIX_BASE_URL = "https://api.zafronix.com/uefa/europaleague/v1"
ZAFRONIX_BASE_URL_MLS = "https://api.zafronix.com/usa/mls/v1"
ZAFRONIX_BASE_URL_UECL = "https://api.zafronix.com/uefa/conferenceleague/v1"
# Ajouter après vos autres constantes Zafronix
ZAFRONIX_NATIONS_LEAGUE_URL = "https://api.zafronix.com/uefa/nationsleague/v1"
#ZAFRONIX_WC_QUAL_UEFA_URL = "https://api.zafronix.com/fifa/worldcup/qualifiers/uefa/v1"
#ZAFRONIX_WC_QUAL_CAF_URL = "https://api.zafronix.com/fifa/worldcup/qualifiers/caf/v1"
#ZAFRONIX_AFRICA_CUP_URL = "https://api.zafronix.com/caf/afcon/v1"
ZAFRONIX_LEAGUES = {
    "EL": "Europa League",
    "MLS": "Major League Soccer",
    "UECL": "Conference League",
}

COMPETITIONS = {
    "PL": "Premier League", "PD": "La Liga", "SA": "Serie A",
    "BL1": "Bundesliga", "FL1": "Ligue 1", "DED": "Eredivisie",
    "PPL": "Primeira Liga", "CL": "Champions League",
    "BSA": "Campeonato Brasileiro",
    "WC": "FIFA World Cup",
    "EC": "UEFA European Championship",
}

LEAGUE_AVG_GOALS = {
    "PL": 2.85, "PD": 2.65, "SA": 2.75, "BL1": 3.15, "FL1": 2.70,
    "DED": 3.20, "PPL": 2.55, "CL": 2.80, "EC": 2.60, "WC": 2.70,
    "BSA": 2.75,
    "SAU": 2.95, "JPN": 2.65, "KOR": 2.55,
    "ARG": 2.70, "CHN": 2.80,
    "MLS": 2.90,
    "WC": 2.60,
    "EC": 2.50,
}

DAYS_AHEAD = 7
HOME_ADVANTAGE = 1.18
_SQRT_HA = math.sqrt(HOME_ADVANTAGE)
RHO = -0.05
K_SHRINK = 10.0
FREE_MATCHES_PER_DAY = 2

LEAGUE_TOP_N = {
    "PL": 5, "PD": 4, "FL1": 4, "DED": 4, "BL1": 5, "PPL": 4,
    "BSA": 5,
}
# Top teams hardcodés pour les ligues sans standings football-data.org
TOP_TEAMS_HARDCODED = {
    "SAU": ["Al Hilal", "Al Ittihad", "Al Nassr", "Al Ahli", "Al Shabab"],
    "JPN": ["Kashima Antlers", "Vissel Kobe", "Urawa Reds", "Yokohama F. Marinos", "Sanfrecce Hiroshima"],
    "KOR": ["Ulsan HD", "Jeonbuk Motors", "Pohang Steelers", "FC Seoul", "Gangwon FC"],
    "ARG": ["River Plate", "Boca Juniors", "Racing Club", "Independiente", "Vélez Sársfield"],
    "MLS": ["Inter Miami", "LAFC", "Columbus Crew", "Philadelphia Union", "Seattle Sounders"],
}

_STANDINGS_CACHE = {}
MIGRATE_DB = False


# ===== APP SETUP =====

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


# ===== BASE DE DONNEES =====

def init_db():
    conn = db()
    c = conn.cursor()
    
    # Table matches
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id BIGINT PRIMARY KEY,
            league TEXT, country TEXT,
            home TEXT, away TEXT,
            home_logo TEXT, away_logo TEXT,
            kickoff TEXT, status TEXT,
            home_goals INTEGER, away_goals INTEGER,
            ht_home_goals INTEGER, ht_away_goals INTEGER,
            home_win DOUBLE PRECISION, draw DOUBLE PRECISION, away_win DOUBLE PRECISION,
            over_15 DOUBLE PRECISION, under_15 DOUBLE PRECISION,
            over_25 DOUBLE PRECISION, under_25 DOUBLE PRECISION,
            over_35 DOUBLE PRECISION, under_35 DOUBLE PRECISION,
            over_45 DOUBLE PRECISION, under_45 DOUBLE PRECISION,
            btts_yes DOUBLE PRECISION, btts_no DOUBLE PRECISION,
            first_half_goal DOUBLE PRECISION,
            handicap_home_1 DOUBLE PRECISION, handicap_away_1 DOUBLE PRECISION,
            dc_1x DOUBLE PRECISION, dc_12 DOUBLE PRECISION, dc_x2 DOUBLE PRECISION,
            dnb_home DOUBLE PRECISION, dnb_away DOUBLE PRECISION,
            over_05 DOUBLE PRECISION, under_05 DOUBLE PRECISION,
            btts_over_25 DOUBLE PRECISION, btts_under_35 DOUBLE PRECISION,
            handicap_home_minus1 DOUBLE PRECISION, handicap_away_minus1 DOUBLE PRECISION,
            handicap_home_plus1 DOUBLE PRECISION, handicap_away_plus1 DOUBLE PRECISION,
            handicap_home_minus2 DOUBLE PRECISION, handicap_away_minus2 DOUBLE PRECISION,
            first_half_over_15 DOUBLE PRECISION,
            exact_scores TEXT,
            home_scores DOUBLE PRECISION, away_scores DOUBLE PRECISION,
            home_xg DOUBLE PRECISION, away_xg DOUBLE PRECISION, total_xg DOUBLE PRECISION,
            confidence DOUBLE PRECISION,
            free_access INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    
    # Table api_log
    c.execute("CREATE TABLE IF NOT EXISTS api_log (day TEXT PRIMARY KEY, count INTEGER)")
    
    # Table team_logos
    c.execute("CREATE TABLE IF NOT EXISTS team_logos (team TEXT PRIMARY KEY, logo TEXT)")
    
    # Table team_stats
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
            team TEXT,
            league TEXT,
            matches_played INTEGER, wins INTEGER, draws INTEGER, losses INTEGER,
            goals_for INTEGER, goals_against INTEGER,
            goals_for_home INTEGER, goals_against_home INTEGER,
            goals_for_away INTEGER, goals_against_away INTEGER,
            points INTEGER, form TEXT, cached_at TEXT,
            PRIMARY KEY (team, league)
        )
    """)
    conn.commit()
    c.close()
    conn.close()

def db():
    # On utilise RealDictCursor pour que les résultats se comportent comme des dictionnaires
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def increment_count():
    today = date.today().isoformat()
    conn = db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO api_log (day, count) VALUES (%s, 1) "
        "ON CONFLICT(day) DO UPDATE SET count = api_log.count + 1",
        (today,),
    )
    conn.commit()
    c.close()
    conn.close()

def get_today_count() -> int:
    today = date.today().isoformat()
    conn = db()
    c = conn.cursor()
    c.execute("SELECT count FROM api_log WHERE day=%s", (today,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row["count"] if row else 0

# ===== LOGOS =====

_TEAM_NAME_PREFIXES = [
    "FC ", "AC ", "SC ", "AS ", "SS ", "SSC ", "CF ", "RC ",
    "1. ", "SV ", "TSG ", "VfB ", "VfL ", "FK ", "SK ",
    "CD ", "GD ", "CA ", "Real ", "Sporting ", "Club ",
    "Atletico ", "Atlético ", "Olympique ", "Stade ",
    "Al ", "Al-", "Club ", "Deportivo ", "Atletico ",
]


def _clean_team_name(name: str) -> str:
    cleaned = name
    for p in _TEAM_NAME_PREFIXES:
        cleaned = cleaned.replace(p, "")
    return cleaned.strip()


async def _lookup_logo_thesportsdb(team_name: str) -> str:
    url = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
    variants = [team_name, _clean_team_name(team_name)]
    seen = set()
    variants = [v for v in variants if v and not (v.lower() in seen or seen.add(v.lower()))]

    for variant in variants:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(url, params={"t": variant})
                if "application/json" not in r.headers.get("content-type", ""):
                    continue
                data = r.json()
                teams = data.get("teams") or []
                for t in teams:
                    team_logo = t.get("strTeamBadge") or t.get("strTeamLogo")
                    if team_logo:
                        return team_logo
        except Exception as e:
            print(f"Erreur logo {variant}: {e}")
    return ""


async def get_team_logo(team_data: dict, force_lookup: bool = False) -> str:
    team_name = team_data.get("name") or team_data.get("shortName", "")
    if not team_name:
        return ""

    # 1. Vérifier dans la base (avec curseur)
    conn = db()
    c = conn.cursor()
    c.execute("SELECT logo FROM team_logos WHERE team=%s", (team_name,))
    row = c.fetchone()
    c.close()
    conn.close()
    
    if row and row["logo"]:
        return row["logo"]

    # 2. Utiliser le crest de l'API si disponible
    crest = team_data.get("crest")
    if crest and not force_lookup:
        if not crest.endswith('.svg'):
            crest = crest.rsplit('.', 1)[0] + '.svg'
        
        conn = db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO team_logos (team, logo) VALUES (%s, %s) "
            "ON CONFLICT (team) DO UPDATE SET logo = EXCLUDED.logo",
            (team_name, crest),
        )
        conn.commit()
        c.close()
        conn.close()
        return crest

    # 3. Chercher via TheSportsDB
    logo = await _lookup_logo_thesportsdb(team_name)
    if logo:
        conn = db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO team_logos (team, logo) VALUES (%s, %s) "
            "ON CONFLICT (team) DO UPDATE SET logo = EXCLUDED.logo",
            (team_name, logo),
        )
        conn.commit()
        c.close()
        conn.close()
        return logo

    return ""

# ===== MODELE POISSON =====

def poisson_prob(k: int, lam: float) -> float:
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _tau(h, a, lh, la, rho=RHO):
    if h == 0 and a == 0: return 1 - lh * la * rho
    if h == 0 and a == 1: return 1 + lh * rho
    if h == 1 and a == 0: return 1 + la * rho
    if h == 1 and a == 1: return 1 - rho
    return 1.0


def _form_factor(form_str):
    if not form_str: return 1.0
    w = form_str.upper().count('W')
    d = form_str.upper().count('D')
    t = len(form_str)
    if t == 0: return 1.0
    r = (w * 3 + d) / (t * 3) if t * 3 > 0 else 0.5
    return 0.90 + (r * 0.20)

def compute_stats_from_history(team_name: str, n_matches: int = 40) -> dict:
    """Calcule les vraies stats pondérées par le temps (Time Decay)."""
    conn = db()
    c = conn.cursor()
    
    c.execute("""
        SELECT home, away, home_goals, away_goals, kickoff 
        FROM matches 
        WHERE (home = %s OR away = %s) AND status = 'FINISHED' 
        ORDER BY kickoff DESC LIMIT %s
    """, (team_name, team_name, n_matches))
    
    rows = c.fetchall()
    c.close()
    conn.close()

    if not rows or len(rows) < 3:
        return None

    import math
    from datetime import datetime

    stats = {
        "matches_played": len(rows),
        "points": 0,
        "weight_sum": 0,
        "weighted_gf": 0, "weighted_ga": 0,
        "weighted_gf_home": 0, "weighted_ga_home": 0,
        "weighted_gf_away": 0, "weighted_ga_away": 0,
        "wins": 0, "draws": 0, "losses": 0,
        "form_list": []
    }

    # Demi-vie de 60 jours (un match de 60 jours compte 2x moins qu'un match d'aujourd'hui)
    HALF_LIFE_DAYS = 60.0
    decay_rate = math.log(2) / HALF_LIFE_DAYS

    now = datetime.now()

    for r in rows:
        # Calcul du poids en fonction de l'âge du match
        match_date = datetime.fromisoformat(r["kickoff"].replace("Z", "+00:00")).replace(tzinfo=None)
        days_ago = (now - match_date).days
        if days_ago < 0: days_ago = 0
        
        weight = math.exp(-decay_rate * days_ago)
        stats["weight_sum"] += weight

        is_home = (r["home"] == team_name)
        team_gf = r["home_goals"] if is_home else r["away_goals"]
        team_ga = r["away_goals"] if is_home else r["home_goals"]
        
        # On pondère les buts
        stats["weighted_gf"] += team_gf * weight
        stats["weighted_ga"] += team_ga * weight
        
        if is_home:
            stats["weighted_gf_home"] += team_gf * weight
            stats["weighted_ga_home"] += team_ga * weight
        else:
            stats["weighted_gf_away"] += team_gf * weight
            stats["weighted_ga_away"] += team_ga * weight

        # Forme et points (on garde les 5 derniers)
        if len(stats["form_list"]) < 5:
            if team_gf > team_ga:
                stats["form_list"].append("W")
            elif team_gf == team_ga:
                stats["form_list"].append("D")
            else:
                stats["form_list"].append("L")
                
        if team_gf > team_ga: stats["wins"] += 1
        elif team_gf == team_ga: stats["draws"] += 1
        else: stats["losses"] += 1

    stats["form"] = "".join(stats["form_list"][::-1]) # Du plus ancien au plus récent
    
    # Nombre de matchs réels à domicile/extérieur (pour le Shrinkage)
    stats["n_home"] = sum(1 for r in rows if r["home"] == team_name)
    stats["n_away"] = sum(1 for r in rows if r["away"] == team_name)

    return stats

def calc_expected_goals_v2e(league_code: str, home_team: str, away_team: str):
    """v2e : Poisson + Dixon-Coles + Shrinkage + Time Decay."""
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)
    
    hs = compute_stats_from_history(home_team)
    as_ = compute_stats_from_history(away_team)
    
    if (not hs or not as_ or hs["matches_played"] < 3 or as_["matches_played"] < 3):
        return ((base / 2.0) * _SQRT_HA, (base / 2.0) / _SQRT_HA)

    la_h = (base / 2.0) * _SQRT_HA
    la_a = (base / 2.0) / _SQRT_HA
    K = 10.0
    
    # 1. Calcul des moyennes pondérées (en utilisant weight_sum)
    # Pour éviter la division par zéro si jamais
    w_home = max(hs["weight_sum"], 0.1)
    w_away = max(as_["weight_sum"], 0.1)
    
    # Attaque domicile de l'équipe A (buts pondérés / poids total)
    att_home = hs["weighted_gf_home"] / w_home if hs["n_home"] > 0 else (hs["weighted_gf"] / w_home)
    def_away = as_["weighted_ga_away"] / w_away if as_["n_away"] > 0 else (as_["weighted_ga"] / w_away)
    
    # Attaque extérieur de l'équipe B
    att_away = as_["weighted_gf_away"] / w_away if as_["n_away"] > 0 else (as_["weighted_gf"] / w_away)
    def_home = hs["weighted_ga_home"] / w_home if hs["n_home"] > 0 else (hs["weighted_ga"] / w_home)
    
    # 2. Application du Shrinkage Bayesien
    att_home_shrunk = (att_home * hs["n_home"] + K * la_h) / (hs["n_home"] + K)
    def_away_shrunk = (def_away * as_["n_away"] + K * la_h) / (as_["n_away"] + K)
    att_away_shrunk = (att_away * as_["n_away"] + K * la_a) / (as_["n_away"] + K)
    def_home_shrunk = (def_home * hs["n_home"] + K * la_a) / (hs["n_home"] + K)

    # 3. Calcul final
    hx = (att_home_shrunk * def_away_shrunk) / la_h
    ax = (att_away_shrunk * def_home_shrunk) / la_a
    
    # 4. Forme
    hx *= _form_factor(hs["form"] or "")
    ax *= _form_factor(as_["form"] or "")
    
    # 5. Limites
    hx = max(0.6, min(3.0, round(hx, 2)))
    ax = max(0.6, min(3.0, round(ax, 2)))
    
    tot = hx + ax
    if tot > 4.5:
        r = 4.5 / tot
        hx = round(hx * r, 2)
        ax = round(ax * r, 2)
        
    return hx, ax

def predict_all_markets(home_xg: float, away_xg: float) -> dict:
    MAX_GOALS = 10
    score_probs = {}
    total_prob = 0.0
    for h in range(MAX_GOALS + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(MAX_GOALS + 1):
            p_a = poisson_prob(a, away_xg)
            p = p_h * p_a * _tau(h, a, home_xg, away_xg)
            score_probs[(h, a)] = p
            total_prob += p
    if total_prob > 0:
        for k in score_probs:
            score_probs[k] /= total_prob

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


# ===== FOOTBALL-CHARTS FETCH =====

async def fetch_footballcharts_fixtures(league_key: str, date_from: str, date_to: str):
    """Récupère les fixtures via football-charts.com (clé 'matches' dans la réponse)."""
    season = date.today().year
    if date.today().month < 7:
        season -= 1
    url = f"{FC_BASE_URL}/leagues/{league_key}/fixtures/"
    params = {"season": season}
    headers = {}
    if FC_API_KEY:
        headers["Authorization"] = f"Bearer {FC_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code != 200:
                print(f"Erreur Football-Charts {league_key}: HTTP {r.status_code} - {r.text[:200]}")
                return []
            data = r.json()
            # ✅ CORRECTION : les fixtures sont dans data["matches"]
            fixtures = []
            if isinstance(data, dict):
                fixtures = data.get("matches") or data.get("fixtures") or data.get("data") or []
            elif isinstance(data, list):
                fixtures = data
            if not fixtures:
                note = data.get("note") if isinstance(data, dict) else None
                print(f"Football-Charts {league_key}: aucun match ({note or 'liste vide'})")
                return []
            filtered = []
            for f in fixtures:
                kickoff = (
                    f.get("match_date") or f.get("kickoff_utc") or f.get("kickoff")
                    or f.get("date") or f.get("datetime")
                )
                if kickoff and isinstance(kickoff, str):
                    d = kickoff[:10]
                    if date_from <= d <= date_to:
                        filtered.append(f)
            print(f"Football-Charts {league_key}: {len(fixtures)} bruts, {len(filtered)} dans la fenetre")
            return filtered
    except Exception as e:
        print(f"Exception Football-Charts {league_key}: {e}")
        return []

def convert_footballcharts_to_internal(fixtures: list, league_code: str, league_name: str) -> list:
    import hashlib
    converted = []
    for f in fixtures:
        try:
            home = (f.get("home") or f.get("home_team") or f.get("homeTeam") or f.get("home_name") or "?")
            away = (f.get("away") or f.get("away_team") or f.get("awayTeam") or f.get("away_name") or "?")
            if isinstance(home, dict): home = home.get("name", "?")
            if isinstance(away, dict): away = away.get("name", "?")
                
            # 👈 AJOUT DE match_date ICI
            kickoff = (f.get("match_date") or f.get("kickoff_utc") or f.get("kickoff") or f.get("date") or f.get("datetime") or f.get("start_time"))
            
            if not kickoff: 
                continue
                
            if isinstance(kickoff, str) and "T" not in kickoff:
                kickoff = kickoff + "T00:00:00"
                
            slug = f.get("slug") or f.get("id") or f"{league_code}-{home}-{away}-{kickoff[:10]}"
            
            hash_obj = hashlib.md5(str(slug).encode())
            numeric_hash = int(hash_obj.hexdigest(), 16) % (10**10)
            match_id = 2_000_000_000 + numeric_hash
            
            internal_match = {
                "id": match_id,
                "homeTeam": {"name": home, "crest": None},
                "awayTeam": {"name": away, "crest": None},
                "utcDate": kickoff,
                "status": "SCHEDULED",
                "score": {"fullTime": {"home": None, "away": None}},
                "league": {"name": league_name, "country": "International"},
                "_code": league_code,
            }
            converted.append(internal_match)
        except Exception as e:
            print(f"Erreur conversion Football-Charts {f.get('slug')}: {e}")
    return converted

# ===== GOAL API FETCH =====

async def fetch_goal_api_fixtures(league_id: str, date_from: str, date_to: str):
    if not GOAL_API_KEY:
        print("GOAL_API_KEY non definie")
        return []
    url = f"{GOAL_API_BASE_URL}/leagues/{league_id}/fixtures"
    headers = {"Authorization": f"Bearer {GOAL_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                print(f"Erreur GOAL API {league_id}: HTTP {r.status_code} - {r.text[:200]}")
                return []
            data = r.json()
            if not data.get("success"):
                print(f"Erreur GOAL API {league_id}: {data.get('message', 'unknown')}")
                return []
            fixtures = data.get("data", [])
            if isinstance(fixtures, dict):
                fixtures = fixtures.get("fixtures", [])
            filtered = []
            for f in fixtures:
                kickoff = f.get("kickoffUtc") or f.get("matchDate")
                if kickoff and isinstance(kickoff, str):
                    d = kickoff[:10]
                    if date_from <= d <= date_to:
                        filtered.append(f)
                else:
                    filtered.append(f)
            print(f"GOAL API {league_id}: {len(fixtures)} bruts, {len(filtered)} dans la fenetre")
            return filtered
    except Exception as e:
        print(f"Exception GOAL API {league_id}: {e}")
        return []


def convert_goal_api_to_internal(fixtures: list, league_code: str, league_name: str) -> list:
    """Convertit le format GOAL API vers le format interne."""
    import hashlib  # 👈 On s'assure que hashlib est importé ici
    
    converted = []
    for f in fixtures:
        try:
            home = f.get("homeTeamName") or f.get("homeTeam", {}).get("name") or "?"
            away = f.get("awayTeamName") or f.get("awayTeam", {}).get("name") or "?"
            kickoff = f.get("kickoffUtc") or f.get("matchDate")
            
            if not kickoff:
                continue
                
            if isinstance(kickoff, str) and "T" not in kickoff:
                kickoff = kickoff + "T00:00:00"
                
            status_raw = (f.get("matchStatus") or "SCHEDULED").upper()
            if status_raw in ["LIVE", "IN_PLAY", "1H", "2H", "HT"]:
                status = "IN_PLAY"
            elif status_raw in ["FINISHED", "FT"]:
                status = "FINISHED"
            else:
                status = "SCHEDULED"
                
            # 👈 LA LIGNE QUI MANQUAIT EST ICI :
            slug = f.get("id") or f"{league_code}-{home}-{away}-{kickoff[:10]}"
            
            # Le hachage déterministe pour éviter les doublons à chaque redémarrage
            hash_obj = hashlib.md5(str(slug).encode())
            numeric_hash = int(hash_obj.hexdigest(), 16) % (10**10)
            match_id = 3_000_000_000 + numeric_hash
            
            internal_match = {
                "id": match_id,
                "homeTeam": {"name": home, "crest": None},
                "awayTeam": {"name": away, "crest": None},
                "utcDate": kickoff,
                "status": status,
                "score": {
                    "fullTime": {
                        "home": f.get("homeScore"),
                        "away": f.get("awayScore"),
                    }
                },
                "league": {"name": league_name, "country": "International"},
                "_code": league_code,
            }
            converted.append(internal_match)
        except Exception as e:
            print(f"Erreur conversion GOAL API {f.get('id')}: {e}")
            
    return converted

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
        
async def _fetch_zafronix_with_etag(url: str, headers: dict, params: dict, competition_name: str) -> list:
    """Fonction générique pour appeler Zafronix avec gestion du cache ETag."""
    if not ZAFRONIX_API_KEY:
        return []

    # On ajoute la clé API aux headers
    headers["X-API-Key"] = ZAFRONIX_API_KEY

    # 👈 On vérifie si on a un ETag en cache pour cette URL
    cached_etag = _ZAFRONIX_ETAG_CACHE.get(url)
    if cached_etag:
        headers["If-None-Match"] = cached_etag

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, params=params)

            # 👈 Si 304, les données n'ont pas changé : 0 quota consommé !
            if r.status_code == 304:
                print(f"Zafronix {competition_name} : 304 Not Modified (quota économisé)")
                return []

            if r.status_code != 200:
                print(f"Erreur Zafronix {competition_name} : {r.status_code}")
                return []

            # 👈 On sauvegarde le nouvel ETag pour la prochaine fois
            new_etag = r.headers.get("ETag")
            if new_etag:
                _ZAFRONIX_ETAG_CACHE[url] = new_etag

            data = r.json()
            # Zafronix renvoie parfois les données dans "matches", "data", ou directement
            events = data.get("matches") or data.get("data") or data
            if not isinstance(events, list):
                events = []
                
            return events
    except Exception as e:
        print(f"Exception Zafronix {competition_name} : {e}")
        return []

async def fetch_zafronix_international(base_url: str, season: int, date_from: str, date_to: str, competition_name: str):
    """Fonction générique pour récupérer les matchs Zafronix avec gestion des ETags."""
    if not ZAFRONIX_API_KEY:
        print(f"ZAFRONIX_API_KEY non definie pour {competition_name}")
        return []

    url = f"{base_url}/matches"
    params = {"season": season} # ou "year" selon l'API
    headers = {"X-API-Key": ZAFRONIX_API_KEY}

    # 👈 On regarde si on a déjà un ETag pour cette URL
    cached_etag = _ZAFRONIX_ETAG_CACHE.get(url)
    if cached_etag:
        headers["If-None-Match"] = cached_etag

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers, params=params)

            # 👈 Si la réponse est 304, les données n'ont pas changé
            if r.status_code == 304:
                print(f"Zafronix {competition_name} : 304 Not Modified (quota économisé)")
                return [] # On retourne une liste vide, le pipeline continuera avec les autres sources

            if r.status_code != 200:
                print(f"Erreur Zafronix {competition_name} : {r.status_code}")
                return []

            # 👈 On stocke le nouvel ETag pour la prochaine fois
            new_etag = r.headers.get("ETag")
            if new_etag:
                _ZAFRONIX_ETAG_CACHE[url] = new_etag

            data = r.json()
            events = data.get("matches") or data.get("data") or data
            filtered = []
            for ev in events:
                ev_date = ev.get("date") or ev.get("utcDate") or ""
                if ev_date and date_from <= ev_date[:10] <= date_to:
                    filtered.append(ev)
            print(f"Zafronix {competition_name} : {len(events)} matchs recus, {len(filtered)} dans la fenetre")
            return filtered
    except Exception as e:
        print(f"Exception Zafronix {competition_name} : {e}")
        return []

async def fetch_zafronix_europa_league(season: int, date_from: str, date_to: str):
    url = f"{ZAFRONIX_BASE_URL}/matches"
    params = {"season": season}
    events = await _fetch_zafronix_with_etag(url, {}, params, "Europa League")
    
    filtered = []
    for ev in events:
        ev_date = ev.get("date") or ev.get("utcDate") or ""
        if ev_date and date_from <= ev_date[:10] <= date_to:
            filtered.append(ev)
    print(f"Zafronix EL : {len(events)} matchs recus, {len(filtered)} dans la fenetre")
    return filtered

async def fetch_zafronix_conference_league(season: int, date_from: str, date_to: str):
    url = f"{ZAFRONIX_BASE_URL_UECL}/matches"
    params = {"season": season}
    events = await _fetch_zafronix_with_etag(url, {}, params, "Conference League")
    
    filtered = []
    for ev in events:
        ev_date = ev.get("date") or ev.get("utcDate") or ""
        if ev_date and date_from <= ev_date[:10] <= date_to:
            filtered.append(ev)
    print(f"Zafronix UECL : {len(events)} matchs recus, {len(filtered)} dans la fenetre")
    return filtered

async def fetch_zafronix_mls(season: int, date_from: str, date_to: str):
    url = f"{ZAFRONIX_BASE_URL_MLS}/matches"
    params = {"season": season}
    events = await _fetch_zafronix_with_etag(url, {}, params, "MLS")
    
    filtered = []
    for ev in events:
        ev_date = ev.get("date") or ev.get("utcDate") or ""
        if ev_date and date_from <= ev_date[:10] <= date_to:
            filtered.append(ev)
    print(f"Zafronix MLS : {len(events)} matchs recus, {len(filtered)} dans la fenetre")
    return filtered

async def fetch_zafronix_nations_league(season: int, date_from: str, date_to: str):
    url = f"{ZAFRONIX_NATIONS_LEAGUE_URL}/matches"
    # 👈 Attention : pour la Nations League, le paramètre est "year" (comme vu précédemment)
    params = {"year": season} 
    events = await _fetch_zafronix_with_etag(url, {}, params, "Nations League")
    
    filtered = []
    for ev in events:
        ev_date = ev.get("date") or ev.get("utcDate") or ""
        if ev_date and date_from <= ev_date[:10] <= date_to:
            filtered.append(ev)
    print(f"Zafronix Nations League : {len(events)} matchs recus, {len(filtered)} dans la fenetre")
    return filtered
                
def convert_zafronix_to_internal(events: list, league_code: str, league_name: str) -> list:
    converted = []
    for ev in events:
        try:
            raw_id = ev.get("id", 0)
            if isinstance(raw_id, str):
                import re
                digits = re.findall(r"\d+", raw_id)
                numeric = int(digits[-1]) if digits else 0
            else:
                numeric = int(raw_id) if raw_id else 0
            match_id = 1_000_000_000 + numeric

            status_raw = (ev.get("status") or "").upper()
            if isinstance(status_raw, dict):
                status_raw = (status_raw.get("short") or "").upper()
            if status_raw in ["FINISHED", "FT", "AET", "PEN"]:
                status = "FINISHED"
            elif status_raw in ["LIVE", "IN_PLAY", "1H", "2H", "HT"]:
                status = "IN_PLAY"
            else:
                status = "SCHEDULED"

            home_team = ev.get("homeTeam") or ev.get("home") or {}
            away_team = ev.get("awayTeam") or ev.get("away") or {}

            if isinstance(home_team, str):
                home_name = home_team
                home_crest = None
            else:
                home_name = home_team.get("name") or home_team.get("shortName") or "?"
                home_crest = home_team.get("crest") or home_team.get("logo")

            if isinstance(away_team, str):
                away_name = away_team
                away_crest = None
            else:
                away_name = away_team.get("name") or away_team.get("shortName") or "?"
                away_crest = away_team.get("crest") or away_team.get("logo")

            score = ev.get("score") or {}
            if isinstance(score, dict):
                full_time = score.get("fullTime") or score
                home_goals = full_time.get("home")
                away_goals = full_time.get("away")
            else:
                home_goals = None
                away_goals = None

            kickoff = ev.get("utcDate") or ev.get("date") or ev.get("dateEvent")
            time_str = (
                ev.get("time")
                or ev.get("strTime")
                or ev.get("startTime")
                or ev.get("kickoffTime")
                or ev.get("eventTime")
            )
            if kickoff and "T" not in kickoff and time_str:
                kickoff = f"{kickoff}T{time_str}"
            if kickoff and "T" not in kickoff:
                kickoff = f"{kickoff}T00:00:00"
            internal_match = {
                "id": match_id,
                "homeTeam": {"name": home_name, "crest": home_crest},
                "awayTeam": {"name": away_name, "crest": away_crest},
                "utcDate": kickoff,
                "status": status,
                "score": {"fullTime": {"home": home_goals, "away": away_goals}},
                "league": {"name": league_name, "country": "International"},
                "_code": league_code,
            }
            converted.append(internal_match)
        except Exception as e:
            print(f"Erreur conversion Zafronix {ev.get('id')}: {e}")
    return converted


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

        # ✅ CORRECTION : definir season AVANT les appels Zafronix
        season = today.year
        if today.month < 7:
            season -= 1

        all_matches = []

        # === football-data.org ===
        for code in COMPETITIONS:
            matches = await fetch_competition_matches(code, date_from, date_to)
            for m in matches:
                m["_code"] = code
            all_matches.extend(matches)
            await asyncio.sleep(7)

        # === Football-Charts.com (SAU, JPN, KOR) ===
        for code, league_key in FC_LEAGUES.items():
            league_name = {
                "SAU": "Saudi Pro League",
                "JPN": "J1 League",
                "KOR": "K League 1",
            }.get(code, code)
            try:
                fixtures = await fetch_footballcharts_fixtures(league_key, date_from, date_to)
                converted = convert_footballcharts_to_internal(fixtures, code, league_name)
                all_matches.extend(converted)
                print(f"Football-Charts {code}: {len(converted)} matchs")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erreur Football-Charts {code}: {e}")

        # === GOAL API (ARG, CHN) ===
        for code, league_id in GOAL_API_LEAGUES.items():
            league_name = {
                "ARG": "Liga Profesional Argentina",
                "CHN": "Chinese Super League",
            }.get(code, code)
            try:
                fixtures = await fetch_goal_api_fixtures(league_id, date_from, date_to)
                converted = convert_goal_api_to_internal(fixtures, code, league_name)
                all_matches.extend(converted)
                print(f"GOAL API {code}: {len(converted)} matchs")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erreur GOAL API {code}: {e}")

        # === Zafronix : EL, UECL, MLS ===
        if ZAFRONIX_API_KEY:
            try:
                zaf_events = await fetch_zafronix_europa_league(season, date_from, date_to)
                converted = convert_zafronix_to_internal(zaf_events, "EL", "Europa League")
                all_matches.extend(converted)
                print(f"Zafronix EL: {len(converted)} matchs")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erreur Zafronix EL: {e}")

        if ZAFRONIX_API_KEY:
            try:
                uecl_events = await fetch_zafronix_conference_league(season, date_from, date_to)
                converted = convert_zafronix_to_internal(uecl_events, "UECL", "Conference League")
                all_matches.extend(converted)
                print(f"Zafronix UECL: {len(converted)} matchs")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erreur Zafronix UECL: {e}")

                # === Zafronix : Compétitions Internationales ===
        if ZAFRONIX_API_KEY:
            try:
                nl_events = await fetch_zafronix_nations_league(season, date_from, date_to)
                converted = convert_zafronix_to_internal(nl_events, "UNL", "UEFA Nations League")
                all_matches.extend(converted)
                print(f"Zafronix Nations League: {len(converted)} matchs")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erreur Zafronix Nations League: {e}")

            
        if ZAFRONIX_API_KEY:
            try:
                mls_season = today.year
                mls_events = await fetch_zafronix_mls(mls_season, date_from, date_to)
                converted = convert_zafronix_to_internal(mls_events, "MLS", "Major League Soccer")
                all_matches.extend(converted)
                print(f"Zafronix MLS: {len(converted)} matchs")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erreur Zafronix MLS: {e}")

        # === Stats équipes (football-data.org uniquement) ===
        print("Recuperation des stats d'equipes...")
        for code, league_name in COMPETITIONS.items():
            try:
                await fetch_team_stats(code, league_name)
                await asyncio.sleep(12)
            except Exception as e:
                print(f"Erreur stats {code}: {e}")

        # === Logos ===
        print("Recuperation des logos...")
        logos = {}
        for m in all_matches:
            try:
                code = m.get("_code", "")
                home_team = m["homeTeam"]
                away_team = m["awayTeam"]
                home_name = home_team.get("name") or home_team.get("shortName", "?")
                away_name = away_team.get("name") or away_team.get("shortName", "?")
                force = code in ["MLS", "SAU", "JPN", "KOR", "ARG", "CHN"]
                if home_name not in logos:
                    logos[home_name] = await get_team_logo(home_team, force_lookup=force)
                if away_name not in logos:
                    logos[away_name] = await get_team_logo(away_team, force_lookup=force)
                await asyncio.sleep(0.5)
            except (KeyError, TypeError):
                continue
        print(str(len(logos)) + " logos recuperes")

        # === Insertion en base ===
        conn = db()
        c = conn.cursor()  # 👈 1. On crée le curseur ici
        inserted = 0
        for m in all_matches:
            try:
                code = m.get("_code", "")
                match_id = m["id"]
                league = COMPETITIONS.get(code, ZAFRONIX_LEAGUES.get(code, "Unknown"))
                if code in FC_LEAGUES:
                    league = {"SAU": "Saudi Pro League", "JPN": "J1 League", "KOR": "K League 1"}.get(code, code)
                if code in GOAL_API_LEAGUES:
                    league = {"ARG": "Liga Profesional Argentina", "CHN": "Chinese Super League"}.get(code, code)
                
                country = m.get("area", {}).get("name", "International")
                home = m["homeTeam"]["name"] or m["homeTeam"].get("shortName", "?")
                away = m["awayTeam"]["name"] or m["awayTeam"].get("shortName", "?")
                kickoff = m.get("utcDate")
                status = m.get("status", "SCHEDULED")
                home_goals = m.get("score", {}).get("fullTime", {}).get("home")
                away_goals = m.get("score", {}).get("fullTime", {}).get("away")
                ht_home = m.get("score", {}).get("halfTime", {}).get("home")
                ht_away = m.get("score", {}).get("halfTime", {}).get("away")

                home_xg, away_xg = calc_expected_goals_v2e(code, home, away)
                pred = predict_all_markets(home_xg, away_xg)
                ext = predict_extended_markets(
                    home_xg, away_xg,
                    pred["home_win"], pred["draw"], pred["away_win"]
                )

                # 👈 2. On utilise c.execute et la syntaxe PostgreSQL
                c.execute(
                    """
                    INSERT INTO matches
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        league = EXCLUDED.league, country = EXCLUDED.country,
                        home = EXCLUDED.home, away = EXCLUDED.away,
                        home_logo = EXCLUDED.home_logo, away_logo = EXCLUDED.away_logo,
                        kickoff = EXCLUDED.kickoff, status = EXCLUDED.status,
                        home_goals = EXCLUDED.home_goals, away_goals = EXCLUDED.away_goals,
                        home_win = EXCLUDED.home_win, draw = EXCLUDED.draw, away_win = EXCLUDED.away_win,
                        confidence = EXCLUDED.confidence, updated_at = EXCLUDED.updated_at
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
        c.close()       # 👈 3. On ferme le curseur
        conn.close()    # 👈 4. On ferme la connexion
        print(str(inserted) + " matchs enregistres")
        mark_free_access()
    finally:
        _PIPELINE_RUNNING = False
        print("=== Pipeline termine ===")


def mark_free_access():
    today = date.today().isoformat()
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE matches SET free_access = 0 WHERE SUBSTRING(kickoff, 1, 10) = %s", (today,))
    c.execute(
        "UPDATE matches SET free_access = 1 WHERE id IN ("
        "SELECT id FROM matches WHERE SUBSTRING(kickoff, 1, 10) = %s "
        "AND confidence IS NOT NULL ORDER BY confidence DESC LIMIT %s)",
        (today, FREE_MATCHES_PER_DAY),
    )
    conn.commit()
    c.close()
    conn.close()
    print("Top " + str(FREE_MATCHES_PER_DAY) + " matchs marques comme gratuits")


async def fetch_top_teams(code: str, top_n: int):
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
    # 1. Vérification du cache (avec curseur)
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as c, MAX(cached_at) as last FROM team_stats WHERE league=%s",
        (league_name,),
    )
    row = c.fetchone()
    c.close()
    conn.close()

    if row and row["c"] > 0 and row["last"]:
        try:
            age = (datetime.now() - datetime.fromisoformat(row["last"])).total_seconds()
            if age < 86400:
                print(f"Stats {league_name} en cache ({row['c']} equipes)")
                return
        except Exception:
            pass

    # 2. Appel API
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
                c = conn.cursor()
                now = datetime.now().isoformat()
                
                # 3. Insertion/Mise à jour dans la base
                for row_team in table:
                    team_name = row_team.get("team", {}).get("name", "")
                    if not team_name:
                        continue
                    
                    # La requête PostgreSQL avec ON CONFLICT pour remplacer INSERT OR REPLACE
                    c.execute("""
                        INSERT INTO team_stats
                        (team, league, matches_played, wins, draws, losses,
                         goals_for, goals_against, goals_for_home, goals_against_home,
                         goals_for_away, goals_against_away, points, form, cached_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (team, league) DO UPDATE SET
                            matches_played = EXCLUDED.matches_played,
                            wins = EXCLUDED.wins,
                            draws = EXCLUDED.draws,
                            losses = EXCLUDED.losses,
                            goals_for = EXCLUDED.goals_for,
                            goals_against = EXCLUDED.goals_against,
                            goals_for_home = EXCLUDED.goals_for_home,
                            goals_against_home = EXCLUDED.goals_against_home,
                            goals_for_away = EXCLUDED.goals_for_away,
                            goals_against_away = EXCLUDED.goals_against_away,
                            points = EXCLUDED.points,
                            form = EXCLUDED.form,
                            cached_at = EXCLUDED.cached_at
                    """, (
                        team_name, league_name,
                        row_team.get("playedGames", 0),
                        row_team.get("won", 0),
                        row_team.get("draw", 0),
                        row_team.get("lost", 0),
                        row_team.get("goalsFor", 0),
                        row_team.get("goalsAgainst", 0),
                        row_team.get("goalsFor", 0) // 2,
                        row_team.get("goalsAgainst", 0) // 2,
                        row_team.get("goalsFor", 0) - row_team.get("goalsFor", 0) // 2,
                        row_team.get("goalsAgainst", 0) - row_team.get("goalsAgainst", 0) // 2,
                        row_team.get("points", 0),
                        row_team.get("form", "") or "",
                        now,
                    ))
                
                conn.commit()
                c.close()
                conn.close()
                print(f"Stats {league_name} : {len(table)} equipes mises a jour")
                return
    except Exception as e:
        print(f"Exception standings {code} : {e}")

# ===== EVALUATION DES PICKS =====

def _evaluate_pick(pick, match):
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


# ===== TICKETS HELPERS =====

_MARKET_GROUP = {
    "1": "home", "DNB D": "home", "H-1 D": "home", "H+1 D": "home",
    "Dom. marque": "home",
    "X": "draw",
    "1X": "no_away", "X2": "no_home", "12": "no_draw",
    "2": "away", "DNB E": "away", "H-1 E": "away", "H+1 E": "away",
    "Ext. marque": "away",
    "+0.5": "over", "+1.5": "over", "+2.5": "over", "+3.5": "over",
    "-2.5": "under", "-3.5": "under", "-4.5": "under",
    "BTTS": "btts", "BTTS+2.5": "btts", "BTTS-3.5": "btts",
    "1MT": "first_half",
}


def _calc_total_cote(picks):
    c = 1.0
    for p in picks:
        c *= p["cote"]
    return round(c, 2)


def _all_picks_for_match(m):
    """Un pick par marché, filtres assouplis pour ne rater aucun match."""
    markets = [
        ("1", m.get("home_win"), m["home"]),
        ("X", m.get("draw"), "Match nul"),
        ("2", m.get("away_win"), m["away"]),
        ("+0.5", m.get("over_05"), "Over 0.5 but"),
        ("+1.5", m.get("over_15"), "+1.5 buts"),
        ("+2.5", m.get("over_25"), "+2.5 buts"),
        ("+3.5", m.get("over_35"), "+3.5 buts"),
        ("-2.5", m.get("under_25"), "-2.5 buts"),
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
        
        # 👈 LE FILTRE EST MAINTENANT TRÈS LARGE (de 10% à 99%)
        if prob < 0.10 or prob > 0.99:
            continue
            
        cote = 1.0 / prob
        if cote < 1.01 or cote > 5.00:
            continue
            
        picks.append({
            "match_id": m["id"], "home": m["home"], "away": m["away"],
            "league": m["league"], "kickoff": m["kickoff"],
            "home_logo": m["home_logo"], "away_logo": m["away_logo"],
            "market": label, "description": desc,
            "proba": round(prob, 4), "cote": round(cote, 2),
            "group": _MARKET_GROUP.get(label, "other"),
            "confidence": m.get("confidence") or 0.5,
        })
    return picks

def _build_ticket_optimized(pool, target_cote, min_n, max_n,
                             min_proba=0.50, max_per_market=2,
                             max_per_group=3):
    if not pool:
        return []

    # 👈 1. Assouplissement : Accepter la CL même si proba < min_proba
    filtered = [p for p in pool if p["proba"] >= min_proba or p.get("league") == "Champions League"]
    
    if len(filtered) < min_n:
        filtered = sorted(pool, key=lambda p: -p["proba"])[:max(max_n * 3, 15)]
    if len(filtered) < min_n:
        return []

    best_combo = None
    best_diff = float('inf')

    for n in range(min_n, min(max_n, len(filtered)) + 1):
        ideal_per_pick = target_cote ** (1.0 / n)
        
        # 👈 2. Priorisation : Mettre la CL en premier dans le tri
        candidates = sorted(
            filtered,
            key=lambda p: (
                p.get("league") != "Champions League",  # False (0) passe avant True (1)
                abs(p["cote"] - ideal_per_pick), 
                -p["proba"]
            )
        )
        
        combo = []
        used_matches = set()
        market_count = {}
        group_count = {}
        
        for p in candidates:
            if len(combo) >= n:
                break
            if p["match_id"] in used_matches:
                continue
            mk = p["market"]
            if market_count.get(mk, 0) >= max_per_market:
                continue
            gr = p.get("group", "other")
            if group_count.get(gr, 0) >= max_per_group:
                continue
                
            combo.append(p)
            used_matches.add(p["match_id"])
            market_count[mk] = market_count.get(mk, 0) + 1
            group_count[gr] = group_count.get(gr, 0) + 1
            
        if len(combo) < min_n:
            continue
            
        cote = _calc_total_cote(combo)
        diff = abs(cote - target_cote)
        joint = 1.0
        for p in combo:
            joint *= p["proba"]
        score = diff
        if joint < 1.0 / (target_cote * 10):
            score += 1000
        if score < best_diff:
            best_diff = score
            best_combo = combo
            
    return best_combo or []

def _summarize_ticket(picks):
    if not picks:
        return {"total_cote": 1.0, "count": 0,
                "joint_prob": 0.0, "joint_prob_pct": 0.0, "picks": []}
    total_cote = _calc_total_cote(picks)
    joint = 1.0
    for p in picks:
        joint *= p["proba"]
    return {
        "total_cote": total_cote,
        "count": len(picks),
        "joint_prob": round(joint, 6),
        "joint_prob_pct": round(joint * 100, 2),
        "picks": picks,
    }


def _calc_risky_pick(m):
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
    if hw >= 0.75:
        candidates.append(("1", m["home"], hw, 1.0 / hw))
    if aw >= 0.75:
        candidates.append(("2", m["away"], aw, 1.0 / aw))
    if home_xg < 1.3 and away_xg < 1.3 and hw < 0.40 and aw < 0.40 and d >= 0.28:
        candidates.append(("X", "Match nul", d, 1.0 / d))
    if hw > 0.70 and home_xg > 1.9 and away_xg < 1.0 and hcp2_home > 0.28:
        candidates.append(("H-2 D", "Handicap -2 " + m["home"], hcp2_home, 1.0 / hcp2_home))
    if aw > 0.70 and away_xg > 1.9 and home_xg < 1.0 and hcp2_away > 0.28:
        candidates.append(("H-2 E", "Handicap -2 " + m["away"], hcp2_away, 1.0 / hcp2_away))
    if 0.62 <= over_25 <= 0.72:
        candidates.append(("+2.5", "+2.5 buts", over_25, 1.0 / over_25))
    if 0.55 <= btts <= 0.77:
        candidates.append(("BTTS", "Les 2 equipes marquent", btts, 1.0 / btts))
    if total_xg > 3.8 and over_35 > 0.50:
        candidates.append(("+3.5", "+3.5 buts", over_35, 1.0 / over_35))
    if fh_goal >= 0.65:
        candidates.append(("1MT", "But en 1ere MT", fh_goal, 1.0 / fh_goal))
    if total_xg > 3.8 and fh_over_15 >= 0.45:
        candidates.append(("+1.5 1MT", "+1.5 buts 1ere MT", fh_over_15, 1.0 / fh_over_15))
    if total_xg < 2.3 and under_25 > 0.55:
        candidates.append(("-2.5", "-2.5 buts", under_25, 1.0 / under_25))

    if not candidates:
        return None
    best = min(candidates, key=lambda x: abs(x[3] - 2.0))
    return {
        "match_id": m["id"], "home": m["home"], "away": m["away"],
        "league": m["league"], "kickoff": m["kickoff"],
        "home_logo": m["home_logo"], "away_logo": m["away_logo"],
        "market": best[0], "description": best[1],
        "proba": round(best[2], 3), "cote": round(best[3], 2),
    }

def _pick_best_for_match(picks_for_match, min_cote=1.2, max_cote=1.6):
    """
    Choisit le meilleur pick d'un match dans la plage de cote cible (1.2-1.6).
    - Priorité : picks dans la plage, triés par confiance décroissante
    - Fallback : pick avec cote la plus proche de 1.4 si aucun dans la plage
    """
    if not picks_for_match:
        return None

    # 1. Candidates dans la plage cible
    candidates = [
        p for p in picks_for_match
        if min_cote <= p["cote"] <= max_cote
    ]

    if candidates:
        # Prendre le plus haute confiance, puis cote la plus proche de 1.4
        candidates.sort(
            key=lambda p: (-p.get("confidence", 0), abs(p["cote"] - 1.4))
        )
        return candidates[0]

    # 2. Fallback : le pick le plus proche de 1.4
    sorted_all = sorted(
        picks_for_match,
        key=lambda p: abs(p["cote"] - 1.4)
    )
    return sorted_all[0] if sorted_all else None

def _build_weekly_ticket(all_picks):
    """
    Construit un ticket semaine avec TOUS les matchs éligibles.
    - Prend tous les matchs des Top Teams (aucune limite par ligue).
    - Pénalise les marchés déjà utilisés pour garantir la diversité.
    """
    if not all_picks:
        return []

    # 1. Regrouper les picks par match unique
    by_match = {}
    for p in all_picks:
        # Au lieu de garder l'heure exacte, on garde juste la date
        match_key = (p["home"].strip().lower(), p["away"].strip().lower(), p["kickoff"][:10])
        by_match.setdefault(match_key, []).append(p)

    selected = []
    market_counts = {}

    # 2. Parcourir TOUS les matchs
    for match_key, picks_for_match in by_match.items():
        
        best_pick = None
        best_score = -1.0

        for p in picks_for_match:
            cote = p.get("cote", 1.0)
            if cote < 1.15:  # On évite juste les paris vraiment trop bas (ex: 1.05)
                continue
                
            mk = p.get("market", "other")
            count = market_counts.get(mk, 0)
            
            # Plus un marché est utilisé, plus son score baisse.
            # Cela force l'algorithme à choisir un autre marché (ex: BTTS au lieu de -4.5)
            score = p.get("proba", 0) - (count * 0.05)
            
            if score > best_score:
                best_score = score
                best_pick = p

        # Si aucun pick n'a passé le filtre de cote, on prend le plus probable
        if not best_pick and picks_for_match:
            best_pick = max(picks_for_match, key=lambda x: x.get("proba", 0))

        if best_pick:
            selected.append(best_pick)
            mk = best_pick.get("market", "other")
            market_counts[mk] = market_counts.get(mk, 0) + 1

    return selected

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


# ===== ROUTES =====

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
    c = conn.cursor()
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) = %s ORDER BY kickoff ASC", (day,)
    )
    rows = c.fetchall()
    c.close()
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
    
    # 1. Création du curseur
    c = conn.cursor()
    
    # 2. Requête PostgreSQL : SUBSTRING au lieu de date(), et %s au lieu de ?
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) BETWEEN %s AND %s ORDER BY kickoff ASC",
        (today.isoformat(), week_later),
    )
    
    # 3. On récupère les résultats depuis le curseur
    rows = c.fetchall()
    
    # 4. On ferme le curseur et la connexion
    c.close()
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
    
    # 👈 1. Créer le curseur
    c = conn.cursor()
    
    # 👈 2. Utiliser c.execute au lieu de conn.execute
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) = %s AND free_access=1 ORDER BY confidence DESC",
        (day,),
    )
    # 👈 3. Récupérer les résultats depuis le curseur
    rows = c.fetchall()
    
    # 👈 4. Fermer le curseur et la connexion
    c.close()
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
    
    # 👈 1. Création du curseur
    c = conn.cursor()
    
    # 👈 2. Utilisation du curseur (c.execute)
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) = %s ORDER BY confidence DESC", (day,)
    )
    
    # 👈 3. Récupération des données
    rows = c.fetchall()
    
    # 👈 4. Fermeture
    c.close()
    conn.close()
    
    result = []
    for r in rows:
        m = dict(r)
        m["analysis"] = generate_analysis(m)
        result.append(m)
    return result

def compute_h2h(home_team: str, away_team: str, before_date: str, limit: int = 5):
    """Calcule les 5 dernières confrontations directes avant la date du match."""
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT home, away, home_goals, away_goals, kickoff
        FROM matches
        WHERE ((home = %s AND away = %s) OR (home = %s AND away = %s))
          AND status = 'FINISHED'
          AND kickoff < %s
        ORDER BY kickoff DESC
        LIMIT %s
    """, (home_team, away_team, away_team, home_team, before_date, limit))
    rows = c.fetchall()
    c.close()
    conn.close()
    return [dict(r) for r in rows]
    
def compute_standings_at_date(league: str, before_date: str, home_team: str, away_team: str):
    """Calcule le classement de la ligue avant la date du match (uniquement pour la saison en cours)."""
    from datetime import datetime
    
    conn = db()
    c = conn.cursor()
    
    # 1. Déterminer le début de la saison (ex: si le match est en mars 2026, la saison a commencé en juillet 2025)
    dt = datetime.fromisoformat(before_date.replace("Z", "+00:00"))
    if dt.month >= 7:
        season_start = f"{dt.year}-07-01T00:00:00"
    else:
        season_start = f"{dt.year - 1}-07-01T00:00:00"
    
    def get_team_standing(team, target_league=None):
        if not target_league:
            c.execute("""
                SELECT league, COUNT(*) as cnt FROM matches 
                WHERE (home = %s OR away = %s) AND status = 'FINISHED' 
                AND kickoff >= %s AND kickoff < %s
                GROUP BY league ORDER BY cnt DESC LIMIT 1
            """, (team, team, season_start, before_date))
            row = c.fetchone()
            if not row: return None
            target_league = row["league"]
        
        # 👇 On ajoute la condition kickoff >= season_start pour ne prendre que la saison en cours
        c.execute("""
            SELECT home, away, home_goals, away_goals FROM matches
            WHERE league = %s AND status = 'FINISHED' 
            AND kickoff >= %s AND kickoff < %s
        """, (target_league, season_start, before_date))
        matches = c.fetchall()
        
        if not matches: return None
        
        stats = {}
        for m in matches:
            h, a = m["home"], m["away"]
            hg, ag = m["home_goals"], m["away_goals"]
            for t in [h, a]:
                if t not in stats:
                    stats[t] = {"team": t, "played": 0, "gf": 0, "ga": 0, "pts": 0}
            stats[h]["played"] += 1; stats[a]["played"] += 1
            stats[h]["gf"] += hg; stats[h]["ga"] += ag
            stats[a]["gf"] += ag; stats[a]["ga"] += hg
            if hg > ag: stats[h]["pts"] += 3
            elif hg < ag: stats[a]["pts"] += 3
            else: stats[h]["pts"] += 1; stats[a]["pts"] += 1
        
        sorted_teams = sorted(stats.values(), key=lambda x: (-x["pts"], -(x["gf"] - x["ga"]), -x["gf"]))
        for i, t in enumerate(sorted_teams):
            if t["team"] == team:
                t["position"] = i + 1
                t["gd"] = t["gf"] - t["ga"]
                t["league"] = target_league
                return t
        return None
    
    result = []
    cup_names = ["Champions League", "Europa League", "Conference League", "UEFA Champions League", "UEFA Europa League", "UEFA Conference League"]
    
    if league in cup_names:
        for team in [home_team, away_team]:
            s = get_team_standing(team)
            if s: result.append(s)
    else:
        for team in [home_team, away_team]:
            s = get_team_standing(team, target_league=league)
            if s: result.append(s)
    
    c.close()
    conn.close()
    return result

@app.get("/matches/{match_id}/detail")
def match_detail(match_id: int):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE id=%s", (match_id,))
    row = c.fetchone()
    c.close()
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
    
    # 👇 NOUVEAU : Calcul du H2H et du Classement
    try:
        m["h2h"] = compute_h2h(m["home"], m["away"], m["kickoff"])
        m["standings"] = compute_standings_at_date(m["league"], m["kickoff"], m["home"], m["away"])
    except Exception as e:
        print(f"Erreur calcul stats détaillées : {e}")
        m["h2h"] = []
        m["standings"] = []
        
    return m

@app.get("/leagues")
def get_leagues():
    conn = db()
    
    # 👈 1. Création du curseur
    c = conn.cursor()
    
    # 👈 2. Utilisation du curseur
    c.execute("SELECT DISTINCT league FROM matches")
    rows = c.fetchall()
    
    # 👈 3. Fermeture
    c.close()
    conn.close()
    
    return [r["league"] for r in rows]
    
@app.get("/tickets/{day}")
def get_tickets(day: str):
    try:
        conn = db()
        
        # 👈 CORRECTION ICI : Utilisation du curseur
        c = conn.cursor()
        c.execute(
            "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) = %s ORDER BY kickoff ASC",
            (day,),
        )
        rows = c.fetchall()
        c.close()
        conn.close()

        if not rows:
            return {"error": "Aucun match pour cette date", "date": day}

        all_picks = []
        for r in rows:
            m = dict(r)
            try:
                all_picks.extend(_all_picks_for_match(m))
            except Exception as e:
                print(f"Erreur picks match {m.get('id')}: {e}")

        if not all_picks:
            return {"error": "Aucun pick disponible", "date": day}

                # 👈 Petite fonction utilitaire pour identifier la CL
        def is_cl(p):
            return p.get("league") == "Champions League"

        # === SAFE ===
        safe_pool = [p for p in all_picks if p.get("confidence", 0) >= 0.70 or is_cl(p)]
        safe = _build_ticket_optimized(
            safe_pool,
            target_cote=2.5,
            min_n=2, max_n=3,
            min_proba=0.55,
            max_per_market=2,
            max_per_group=2,
        )
        safe_ids = {p["match_id"] for p in safe}

        # === MEDIUM SHORT ===
        medium_short_pool = [
            p for p in all_picks
            if p["match_id"] not in safe_ids
            and (p.get("confidence", 0) >= 0.55 or is_cl(p))
        ]
        medium_short = _build_ticket_optimized(
            medium_short_pool,
            target_cote=55.0,
            min_n=5, max_n=8,
            min_proba=0.45,
            max_per_market=2,
            max_per_group=3,
        )
        medium_short_ids = {p["match_id"] for p in medium_short}

        # === MEDIUM LONG ===
        medium_long_pool = [
            p for p in all_picks
            if p["match_id"] not in safe_ids
            and p["match_id"] not in medium_short_ids
            and (p.get("confidence", 0) >= 0.50 or is_cl(p))
        ]
        medium_long = _build_ticket_optimized(
            medium_long_pool,
            target_cote=125.0,
            min_n=7, max_n=10,
            min_proba=0.40,
            max_per_market=3,
            max_per_group=4,
        )
        medium_long_ids = {p["match_id"] for p in medium_long}

        # === RISKY ===
        risky_pool = [
            p for p in all_picks
            if p["match_id"] not in safe_ids
            and p["match_id"] not in medium_short_ids
            and p["match_id"] not in medium_long_ids
            and (p.get("confidence", 0) >= 0.35 or is_cl(p))
        ]
        risky = _build_ticket_optimized(
            risky_pool,
            target_cote=1000.0,
            min_n=10, max_n=15,
            min_proba=0.28,
            max_per_market=4,
            max_per_group=6,
        )
        match_map = {dict(r)["id"]: dict(r) for r in rows}

        def enrich(picks):
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

        safe = enrich(safe)
        medium_short = enrich(medium_short)
        medium_long = enrich(medium_long)
        risky = enrich(risky)

        return {
            "date": day,
            "safe":         {"name": "Ticket Safe",         **_summarize_ticket(safe)},
            "medium":       {"name": "Ticket Medium Short", **_summarize_ticket(medium_short)},
            "medium_short": {"name": "Ticket Medium Short", **_summarize_ticket(medium_short)},
            "medium_long":  {"name": "Ticket Medium Long",  **_summarize_ticket(medium_long)},
            "risky":        {"name": "Ticket Risky",        **_summarize_ticket(risky)},
        }
    except Exception as e:
        print(f"Erreur get_tickets: {e}")
        import traceback; traceback.print_exc()
        return {
            "error": f"Erreur interne: {str(e)}",
            "date": day,
            "safe":         {"name": "Ticket Safe",         "total_cote": 1.0, "count": 0, "picks": []},
            "medium":       {"name": "Ticket Medium Short", "total_cote": 1.0, "count": 0, "picks": []},
            "medium_short": {"name": "Ticket Medium Short", "total_cote": 1.0, "count": 0, "picks": []},
            "medium_long":  {"name": "Ticket Medium Long",  "total_cote": 1.0, "count": 0, "picks": []},
            "risky":        {"name": "Ticket Risky",        "total_cote": 1.0, "count": 0, "picks": []},
        }

@app.get("/predictions/won/{day}")
def get_won_predictions(day: str):
    conn = db()
    
    # 👈 1. Création du curseur
    c = conn.cursor()
    
    # 👈 2. Utilisation du curseur (c.execute)
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) = %s AND status='FINISHED' ORDER BY kickoff ASC",
        (day,),
    )
    
    # 👈 3. Récupération des données
    rows = c.fetchall()
    
    # 👈 4. Fermeture du curseur et de la connexion
    c.close()
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
    
    # 👈 1. Création du curseur
    c = conn.cursor()
    
    # 👈 2. Requête PostgreSQL (SUBSTRING + %s)
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) BETWEEN %s AND %s "
        "AND status='FINISHED' ORDER BY kickoff DESC",
        (week_ago, today.isoformat()),
    )
    
    # 👈 3. Récupération
    rows = c.fetchall()
    
    # 👈 4. Fermeture
    c.close()
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

@app.get("/tickets-week")
async def get_tickets_week():
    """Ticket semaine : TOUS les matchs des top teams, sans limite."""
    today = date.today()
    week_later = (today + timedelta(days=7)).isoformat()

    # 1. Top teams football-data.org
    top_teams_by_league = {}
    for code, top_n in LEAGUE_TOP_N.items():
        teams = await fetch_top_teams(code, top_n)
        top_teams_by_league[code] = set(teams)

    # 2. Top teams hardcodés pour les nouvelles ligues
    for code, teams in TOP_TEAMS_HARDCODED.items():
        top_teams_by_league[code] = set(teams)

    if not any(top_teams_by_league.values()):
        return {"error": "Standings indisponibles"}

    # 3. Matchs de la semaine
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) BETWEEN %s AND %s ORDER BY kickoff ASC",
        (today.isoformat(), week_later),
    )
    rows = c.fetchall()
    c.close()
    conn.close()

    if not rows:
        return {"error": "Aucun match cette semaine"}

    # 4. Filtrer : match avec au moins une top team
    eligible = []
    league_name_to_code = {name: c for c, name in COMPETITIONS.items()}
    league_name_to_code.update({
        "Saudi Pro League": "SAU",
        "J1 League": "JPN",
        "K League 1": "KOR",
        "Liga Profesional Argentina": "ARG",
        "Major League Soccer": "MLS",
    })

    for r in rows:
        m = dict(r)
        status = m.get("status", "")
        if status not in ["SCHEDULED", "TIMED"]:
            continue
            
        league_name = m.get("league", "")
        
        # 👇 LE BLOC MANQUANT EST ICI 👇
        # On inclut TOUTES les coupes d'Europe sans condition de Top Teams
        if league_name in ["Champions League", "Europa League", "Conference League"]:
            m["_code"] = league_name
            m["_home_top"] = True
            m["_away_top"] = True
            eligible.append(m)
            continue
        # 👆 FIN DU BLOC MANQUANT 👆

        code = league_name_to_code.get(league_name)
        if not code or code not in top_teams_by_league:
            continue
            
        top_teams = top_teams_by_league[code]
        home = m.get("home", "")
        away = m.get("away", "")
        home_top = any(t in home or home in t for t in top_teams)
        away_top = any(t in away or away in t for t in top_teams)
        
        if not home_top and not away_top:
            continue
            
        m["_code"] = code
        m["_home_top"] = home_top
        m["_away_top"] = away_top
        eligible.append(m)

    if not eligible:
        return {"error": "Aucun match avec equipe top cette semaine"}

    # 5. Collecter TOUS les picks des matchs éligibles
    all_picks = []
    for m in eligible:
        try:
            picks = _all_picks_for_match(m)
            for p in picks:
                p["_code"] = m.get("_code")
            all_picks.extend(picks)
        except Exception as e:
            print(f"Erreur picks match {m.get('id')}: {e}")

    if not all_picks:
        return {"error": "Aucun pick trouve"}

    # 6. Filtrer par confiance (garder les meilleurs picks)
    best_picks = [p for p in all_picks if p.get("confidence", 0) >= 0.60]
    if len(best_picks) < 10:
        # Fallback progressif si pas assez de picks
        best_picks = [p for p in all_picks if p.get("confidence", 0) >= 0.60]
    if len(best_picks) < 5:
        best_picks = all_picks

    print(f"Ticket semaine : {len(best_picks)} picks retenus "
          f"(seuil confidence applique)")

    # 7. Construire le ticket (1 pick par match, cote 1.2-1.6)
    selected = _build_weekly_ticket(best_picks)    
    # 8. Enrichir avec évaluation
    match_map = {m["id"]: m for m in eligible}
    for p in selected:
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

    # 9. Statistiques
    joint = 1.0
    for p in selected:
        joint *= p["proba"]

    markets_used = {}
    leagues_used = {}
    for p in selected:
        mk = p.get("market", "?")
        markets_used[mk] = markets_used.get(mk, 0) + 1
        lg = p.get("league", "?")
        leagues_used[lg] = leagues_used.get(lg, 0) + 1

    return {
        "week_start": today.isoformat(),
        "week_end": week_later,
        "total_eligible_matches": len(eligible),
        "total_picks": len(selected),
        "total_cote": _calc_total_cote(selected),
        "joint_prob_pct": round(joint * 100, 4),
        "picks": selected,
        "markets_used": markets_used,
        "leagues_used": leagues_used,
        "top_teams": {code: list(teams) for code, teams in top_teams_by_league.items()},
    }

@app.get("/tickets-week-value")
async def get_tickets_week_value():
    """Ticket semaine 'Value' : 10-15 meilleurs picks, cote cible ~300."""
    today = date.today()
    week_later = (today + timedelta(days=7)).isoformat()

    # 1. Récupération des Top Teams (comme pour le ticket complet)
    top_teams_by_league = {}
    for code, top_n in LEAGUE_TOP_N.items():
        teams = await fetch_top_teams(code, top_n)
        top_teams_by_league[code] = set(teams)
    for code, teams in TOP_TEAMS_HARDCODED.items():
        top_teams_by_league[code] = set(teams)

    # 2. Récupération des matchs de la semaine
    conn = db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM matches WHERE SUBSTRING(kickoff, 1, 10) BETWEEN %s AND %s ORDER BY kickoff ASC",
        (today.isoformat(), week_later),
    )
    rows = c.fetchall()
    c.close()
    conn.close()

    if not rows:
        return {"error": "Aucun match cette semaine"}

    # 3. Filtrage des matchs éligibles (Top Teams + Coupes d'Europe)
    eligible = []
    league_name_to_code = {name: c for c, name in COMPETITIONS.items()}
    league_name_to_code.update({
        "Saudi Pro League": "SAU", "J1 League": "JPN", "K League 1": "KOR",
        "Liga Profesional Argentina": "ARG", "Major League Soccer": "MLS",
    })

    for r in rows:
        m = dict(r)
        if m.get("status") not in ["SCHEDULED", "TIMED"]:
            continue
        league_name = m.get("league", "")
        
        if league_name in ["Champions League", "Europa League", "Conference League"]:
            m["_code"] = league_name
            eligible.append(m)
            continue
            
        code = league_name_to_code.get(league_name)
        if not code or code not in top_teams_by_league:
            continue
        top_teams = top_teams_by_league[code]
        home = m.get("home", "")
        away = m.get("away", "")
        if not (any(t in home or home in t for t in top_teams) or any(t in away or away in t for t in top_teams)):
            continue
            
        m["_code"] = code
        eligible.append(m)

    if not eligible:
        return {"error": "Aucun match avec equipe top cette semaine"}

    # 4. Collecte et dédoublonnage de TOUS les picks possibles
    all_picks = []
    seen_picks = set()
    for m in eligible:
        try:
            picks = _all_picks_for_match(m)
            for p in picks:
                # Clé unique pour éviter les doublons dus aux redémarrages de l'API
                key = (p["home"].lower(), p["away"].lower(), p["kickoff"][:10], p["market"])
                if key not in seen_picks:
                    seen_picks.add(key)
                    all_picks.append(p)
        except Exception as e:
            print(f"Erreur picks match {m.get('id')}: {e}")

    # 5. Construction du ticket "Value" via la fonction intelligente
    # On cherche une cote de 300 avec max 15 picks, en privilégiant les probas > 50%
    value_selected = _build_ticket_optimized(
        all_picks,
        target_cote=300.0,
        min_n=10, max_n=15,
        min_proba=0.50,
        max_per_market=3,
        max_per_group=5
    )

    # Sécurité : si l'algo n'a pas trouvé assez de picks, on prend les meilleurs dispos
    if len(value_selected) < 5:
        all_picks.sort(key=lambda x: -x.get("proba", 0))
        value_selected = all_picks[:12]

    # 6. Enrichissement et formatage
    match_map = {m["id"]: m for m in eligible}
    for p in value_selected:
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
                p["reason"] = ""
                p["current_score"] = None

    joint = 1.0
    for p in value_selected:
        joint *= p["proba"]
        
    markets_used = {}
    for p in value_selected:
        mk = p.get("market", "?")
        markets_used[mk] = markets_used.get(mk, 0) + 1

    return {
        "week_start": today.isoformat(),
        "week_end": week_later,
        "total_picks": len(value_selected),
        "total_cote": _calc_total_cote(value_selected),
        "joint_prob_pct": round(joint * 100, 2),
        "picks": value_selected,
        "markets_used": markets_used,
    }

@app.post("/admin/import-history")
async def import_history(background_tasks: BackgroundTasks):
    """Télécharge l'historique (2024-2025) et l'insère dans PostgreSQL en arrière-plan."""
    background_tasks.add_task(run_history_import)
    return {"status": "started", "message": "L'importation tourne en arrière-plan. Vérifie les logs Render."}

async def run_history_import():
    print("=== DÉBUT DE L'IMPORTATION HISTORIQUE ===")
    
    # On va chercher la saison 2024-2025 (ou 2025 si tu préfères)
    seasons = [2024, 2025, 2026] 
    total_inserted = 0

    for season in seasons:
        for code, name in COMPETITIONS.items():
            # On ignore la Ligue des Champions pour l'historique pour gagner du temps
            if code == "CL":
                continue
                
            print(f"Téléchargement de l'historique : {name} ({season})...")
            date_from = f"{season}-07-01"
            date_to = f"{season+1}-06-30"
            
            url = BASE_URL + "/competitions/" + code + "/matches"
            params = {"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED"}
            
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(url, headers=HEADERS, params=params)
                    if r.status_code != 200:
                        print(f"Erreur {code} : HTTP {r.status_code}")
                        continue
                    
                    matches = r.json().get("matches", [])
                    print(f"  -> {len(matches)} matchs trouvés.")
                    
                    if not matches:
                        continue

                    conn = db()
                    c = conn.cursor()
                    
                    for m in matches:
                        try:
                            home = m["homeTeam"]["name"]
                            away = m["awayTeam"]["name"]
                            hg = m["score"]["fullTime"]["home"]
                            ag = m["score"]["fullTime"]["away"]
                            
                            if hg is None or ag is None:
                                continue

                            # On insère avec le statut FINISHED
                            c.execute("""
                                INSERT INTO matches 
                                (id, league, country, home, away, kickoff, status, home_goals, away_goals, updated_at)
                                VALUES (%s, %s, %s, %s, %s, %s, 'FINISHED', %s, %s, NOW())
                                ON CONFLICT (id) DO NOTHING
                            """, (
                                m["id"], name, m.get("area", {}).get("name", "International"),
                                home, away, m["utcDate"], hg, ag
                            ))
                            total_inserted += 1
                        except Exception as e:
                            pass
                    
                    conn.commit()
                    c.close()
                    conn.close()
                    
            except Exception as e:
                print(f"Exception {code} : {e}")
            
            # Pause pour respecter la limite de 10 requêtes/minute de football-data.org
            await asyncio.sleep(7)

    print(f"=== IMPORTATION TERMINÉE : {total_inserted} matchs ajoutés en base ===")

@app.post("/refresh")
async def manual_refresh():
    await daily_pipeline()
    return {"status": "refreshed", "days_ahead": DAYS_AHEAD}

@app.post("/admin/clean-upcoming")
async def clean_upcoming():
    try:
        conn = db()
        c = conn.cursor()
        # 👈 On supprime UNIQUEMENT les matchs qui ne sont pas encore terminés
        c.execute("DELETE FROM matches WHERE status IN ('SCHEDULED', 'TIMED', 'IN_PLAY', 'PAUSED')")
        deleted = c.rowcount
        conn.commit()
        c.close()
        conn.close()
        return {"status": "success", "message": f"{deleted} matchs à venir ont été supprimés. Les matchs FINISHED sont intacts."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ===== CHATBOT IA =====
class PickExplainRequest(BaseModel):
    match_id: int
    current_market: str
    user_question: str = "Pourquoi ce pick a-t-il été choisi ?"

@app.post("/api/pick/explain")
async def explain_pick(req: PickExplainRequest):
    try: # 👈 TRY PRINCIPAL (ouvert ici)
        # 1. Récupérer le match en base
        conn = db()
        c = conn.cursor()
        c.execute("SELECT * FROM matches WHERE id=%s", (req.match_id,))
        row = c.fetchone()
        c.close()
        conn.close()

        if not row:
            return {"error": "Match non trouvé"}

        m = dict(row)
        
        # 2. Préparer le contexte pour l'IA
        context = f"""
        Match: {m['home']} vs {m['away']} ({m['league']})
        Buts attendus (xG): {m['home_xg']} pour {m['home']}, {m['away_xg']} pour {m['away']}
        Probabilités 1X2: {m['home_win']*100:.1f}% / {m['draw']*100:.1f}% / {m['away_win']*100:.1f}%
        Le pari actuel est: {req.current_market}
        """

        system_prompt = """Tu es un analyste sportif expert. Ton but est d'expliquer de manière pédagogue et concise pourquoi un modèle mathématique a choisi un pari.
        L'utilisateur peut te demander une alternative plus sûre. Si c'est le cas, tu dois proposer un autre marché parmi ceux disponibles.
        Tu dois impérativement répondre en JSON avec le format suivant :
        {
            "explanation": "Ton explication ici...",
            "alternative_market": "Le code du marché (ex: 1X) ou null",
            "alternative_description": "Description (ex: Double Chance 1X) ou null",
            "alternative_proba": 0.75
        }"""

        user_prompt = f"Contexte du match : {context}\n\nQuestion de l'utilisateur : {req.user_question}"

        # 3. Appel à l'IA avec Fallback (Gemini -> Groq)
        GEMINI_API_KEY = os.getenv("LLM_API_KEY")
        GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
        
        ai_text = None
        last_error = ""

        # --- TENTATIVE 1 : GEMINI 3.8 FLASH ---
        try:
            print("🤖 Tentative avec Gemini 3.8 Flash...")
            url_gemini = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
            headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(url_gemini, headers=headers, json=payload)
                res_data = res.json()
                if "candidates" in res_data:
                    ai_text = res_data['candidates'][0]['content']['parts'][0]['text']
                else:
                    last_error = f"Gemini: {res_data.get('error', {}).get('message', 'Erreur inconnue')}"
        except Exception as e:
            last_error = f"Gemini Exception: {str(e)}"

        # --- TENTATIVE 2 : GROQ (FALLBACK) ---
        if not ai_text and GROQ_API_KEY:
            try:
                print("🤖 Échec Gemini, tentative avec Groq...")
                url_groq = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "openai/gpt-oss-120b",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    res = await client.post(url_groq, headers=headers, json=payload)
                    res_data = res.json()
                    if "choices" in res_data:
                        ai_text = res_data['choices'][0]['message']['content']
                    else:
                        last_error += f" | Groq: {res_data.get('error', {}).get('message', 'Erreur inconnue')}"
            except Exception as e:
                last_error += f" | Groq Exception: {str(e)}"

        # --- VÉRIFICATION FINALE ---
        if not ai_text:
            print(f"🚨 Échec total de l'IA. Erreurs : {last_error}")
            return {"error": "L'IA est momentanément indisponible. Veuillez réessayer."}

        # Nettoyage et parsing du JSON
        ai_text = ai_text.replace("```json", "").replace("```", "").strip()
        ai_json = json.loads(ai_text)
        
        return ai_json

    except Exception as e: # 👈 C'EST CE BLOC QUI MANQUAIT À LA FIN
        print(f"Erreur générale IA : {e}")
        return {"error": "Une erreur interne est survenue lors de l'analyse."}

# ===== IMPORTATION HISTORIQUE (LIGUES SPÉCIFIQUES) =====

# Clés et saisons exactes vérifiées via /api/v1/leagues/
FC_LEAGUES_TO_IMPORT = {
    # --- Asie ---
    "JPN": {"key": "japan1", "seasons": ["2026", "2025"]},
    "KOR": {"key": "korea1", "seasons": ["2026", "2025"]},
    "CHN": {"key": "china", "seasons": ["2026", "2025"]},
    "SAU": {"key": "saudi1", "seasons": ["2026-2027", "2025-2026"]},
    
    # --- Amériques ---
    "BRA": {"key": "brazil1", "seasons": ["2026", "2025"]},
    "MLS": {"key": "usa1", "seasons": ["2026", "2025"]},
}

@app.post("/admin/import-history-fc")
async def import_history_fc(background_tasks: BackgroundTasks):
    """Importe l'historique des ligues spécifiques via Football-Charts."""
    background_tasks.add_task(run_fc_history_import)
    return {"status": "started", "message": "L'importation tourne en arrière-plan. Vérifie les logs Render."}

async def run_fc_history_import():
    print("=== DÉBUT DE L'IMPORTATION HISTORIQUE (FOOTBALL-CHARTS) ===")
    total_inserted = 0
    
    # 👇 LA BOUCLE EST CORRIGÉE ICI
    for code, league_info in FC_LEAGUES_TO_IMPORT.items():
        league_key = league_info["key"]
        seasons_to_try = league_info["seasons"]
        
        for season in seasons_to_try:
            print(f"Téléchargement de l'historique : {league_key} ({season})...")
            
            url = f"{FC_BASE_URL}/leagues/{league_key}/results/"
            params = {"season": season}
            headers = {}
            if FC_API_KEY:
                headers["Authorization"] = f"Bearer {FC_API_KEY}"

            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(url, headers=headers, params=params)
                    if r.status_code != 200:
                        print(f"  -> Erreur HTTP {r.status_code} pour {league_key} ({season})")
                        continue
                    
                    data = r.json()
                    # La réponse peut être une liste directe ou un objet avec "matches"
                    matches = data if isinstance(data, list) else data.get("matches", [])
                    if not matches:
                        print(f"  -> Aucun match trouvé pour {league_key} ({season})")
                        continue

                    print(f"  -> {len(matches)} matchs trouvés.")
                    
                    conn = db()
                    c = conn.cursor()
                    
                    for m in matches:
                        try:
                            # Extraction des champs
                            home = m.get("home_team") or m.get("homeTeam") or "?"
                            away = m.get("away_team") or m.get("awayTeam") or "?"
                            
                            # Gestion des scores "2:1" ou "2-1"
                            ft = m.get("ft_result") or m.get("score", {})
                            hg = None
                            ag = None
                            
                            if isinstance(ft, dict):
                                hg = ft.get("home") or ft.get("home_goals")
                                ag = ft.get("away") or ft.get("away_goals")
                            else:
                                # L'API renvoie souvent le score avec deux-points (ex: "2:1")
                                score_str = str(ft).replace("-", ":").strip()
                                parts = score_str.split(":")
                                if len(parts) >= 2:
                                    if parts[0].strip().isdigit() and parts[1].strip().isdigit():
                                        hg = int(parts[0].strip())
                                        ag = int(parts[1].strip())

                            if hg is None or ag is None:
                                continue

                            kickoff = m.get("match_date") or m.get("date") or m.get("kickoff_utc")
                            if not kickoff:
                                continue
                            if isinstance(kickoff, str) and "T" not in kickoff:
                                kickoff = kickoff + "T00:00:00"

                            # ID unique pour éviter les doublons
                            slug = m.get("slug") or f"{league_key}-{home}-{away}-{kickoff[:10]}"
                            hash_obj = hashlib.md5(str(slug).encode())
                            numeric_hash = int(hash_obj.hexdigest(), 16) % (10**10)
                            match_id = 4_000_000_000 + numeric_hash

                            # Insertion dans PostgreSQL
                            c.execute("""
                                INSERT INTO matches 
                                (id, league, country, home, away, kickoff, status, home_goals, away_goals, updated_at)
                                VALUES (%s, %s, %s, %s, %s, %s, 'FINISHED', %s, %s, NOW())
                                ON CONFLICT (id) DO NOTHING
                            """, (
                                match_id, league_key, "International", 
                                home, away, kickoff, hg, ag
                            ))
                            total_inserted += 1
                        except Exception as e:
                            print(f"    Erreur sur le match {m.get('id')}: {e}")
                    
                    conn.commit()
                    c.close()
                    conn.close()
                    
            except Exception as e:
                print(f"  -> Exception pour {league_key} ({season}): {e}")
            
            # Pause pour respecter le quota (200 req/jour)
            await asyncio.sleep(5)

    print(f"=== IMPORTATION TERMINÉE : {total_inserted} matchs ajoutés en base ===")

@app.post("/admin/fix-league-names")
async def fix_league_names():
    try:
        conn = db()
        c = conn.cursor()
        
        # Dictionnaire de correspondance (clé API -> Nom Propre)
        mapping = {
            "japan1": "J1 League",
            "korea1": "K League 1",
            "china": "Chinese Super League",
            "saudi1": "Saudi Pro League",
            "brazil1": "Campeonato Brasileiro",
            "usa1": "Major League Soccer"
        }
        
        total_updated = 0
        for key, name in mapping.items():
            c.execute("UPDATE matches SET league = %s WHERE league = %s", (name, key))
            total_updated += c.rowcount
            
        conn.commit()
        c.close()
        conn.close()
        return {"status": "success", "message": f"{total_updated} matchs mis à jour avec les bons noms de ligues."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
