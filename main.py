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
            ht_home = m.get("score", {}).get("halfTime", {}).get("home")
            ht_away = m.get("score", {}).get("halfTime", {}).get("away")

            home_xg, away_xg = calc_expected_goals(code)
            pred = predict_all_markets(home_xg, away_xg)
            ext = predict_extended_markets(
                home_xg, away_xg,
                pred["home_win"], pred["draw"], pred["away_win"]
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO matches
                (id, league, country, home, away, home_logo, away_logo,
                 kickoff, status, home_goals, away_goals,ht_home_goals, ht_away_goals,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id, league, country, home, away,
                    logos.get(home, ""), logos.get(away, ""),
                    kickoff, status, home_goals, away_goals,ht_home, ht_away,
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
            medium = _build_ticket(medium_pool, 120.0, 10, 15)
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

@app.post("/refresh")
async def manual_refresh():
    await daily_pipeline()
    return {"status": "refreshed", "days_ahead": DAYS_AHEAD}
