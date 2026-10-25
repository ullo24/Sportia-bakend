#!/usr/bin/env python3
"""Intègre le moteur v2e dans main.py."""

with open("main.py", "r") as f:
    c = f.read()

# 1. Constantes après HOME_ADVANTAGE
old = "HOME_ADVANTAGE = 1.18\n"
new = ("HOME_ADVANTAGE = 1.18\n"
       "_SQRT_HA = math.sqrt(HOME_ADVANTAGE)\n"
       "RHO = -0.05\n"
       "K_SHRINK = 10.0\n")
c = c.replace(old, new, 1)

# 2. _tau + _form_factor après poisson_prob
old = ("def poisson_prob(k: int, lam: float) -> float:\n"
       "    return (lam ** k) * math.exp(-lam) / math.factorial(k)\n")
new = ("def poisson_prob(k: int, lam: float) -> float:\n"
       "    return (lam ** k) * math.exp(-lam) / math.factorial(k)\n"
       "\n\n"
       "def _tau(h, a, lh, la, rho=RHO):\n"
       "    if h == 0 and a == 0: return 1 - lh * la * rho\n"
       "    if h == 0 and a == 1: return 1 + lh * rho\n"
       "    if h == 1 and a == 0: return 1 + la * rho\n"
       "    if h == 1 and a == 1: return 1 - rho\n"
       "    return 1.0\n"
       "\n\n"
       "def _form_factor(form_str):\n"
       "    if not form_str: return 1.0\n"
       "    w = form_str.upper().count('W')\n"
       "    d = form_str.upper().count('D')\n"
       "    t = len(form_str)\n"
       "    if t == 0: return 1.0\n"
       "    r = (w * 3 + d) / (t * 3) if t * 3 > 0 else 0.5\n"
       "    return 0.90 + (r * 0.20)\n")
c = c.replace(old, new, 1)

# 3. calc_expected_goals_v2e avant predict_all_markets
marker = "def predict_all_markets"
idx = c.find(marker)
if idx == -1: raise SystemExit("marker predict_all_markets introuvable")

v2e_func = '''def calc_expected_goals_v2e(league_code: str, home_team: str, away_team: str):
    """v2e : Poisson + Dixon-Coles + shrinkage bayesien (K=10, rho=-0.05)."""
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)
    conn = db()
    league_name = COMPETITIONS.get(league_code, "")
    allow_any_league = league_code in ["CL", "EL", "UECL", "EC", "WC"]
    prefixes = ["FC ", "AC ", "SC ", "AS ", "SS ", "SSC ", "CF ", "RC ",
                "1. ", "SV ", "TSG ", "VfB ", "VfL ", "FK ", "SK ",
                "CD ", "GD ", "CA ", "Real ", "Sporting ", "Club ",
                "Atletico ", "Atletico ", "Olympique ", "Stade "]
    def _clean(n):
        for p in prefixes: n = n.replace(p, "")
        return n.strip().lower()
    def _find(team_name):
        r = conn.execute("SELECT * FROM team_stats WHERE team=? AND league=?",
                         (team_name, league_name)).fetchone()
        if r: return r
        if allow_any_league:
            r = conn.execute("SELECT * FROM team_stats WHERE team=? LIMIT 1",
                             (team_name,)).fetchone()
            if r: return r
        cleaned = _clean(team_name)
        for tr in conn.execute("SELECT * FROM team_stats WHERE league=?",
                               (league_name,)).fetchall():
            if cleaned in _clean(tr["team"]) or _clean(tr["team"]) in cleaned:
                return tr
        if allow_any_league:
            for tr in conn.execute("SELECT * FROM team_stats").fetchall():
                if cleaned in _clean(tr["team"]) or _clean(tr["team"]) in cleaned:
                    return tr
        return None
    hs = _find(home_team)
    as_ = _find(away_team)
    conn.close()
    if (not hs or not as_ or hs["matches_played"] < 3
            or as_["matches_played"] < 3):
        return ((base / 2.0) * _SQRT_HA, (base / 2.0) / _SQRT_HA)
    la_h = (base / 2.0) * _SQRT_HA
    la_a = (base / 2.0) / _SQRT_HA
    ah = (hs["goals_for"] + K_SHRINK * la_h) / (hs["matches_played"] + K_SHRINK)
    dh = (hs["goals_against"] + K_SHRINK * la_a) / (hs["matches_played"] + K_SHRINK)
    aa = (as_["goals_for"] + K_SHRINK * la_a) / (as_["matches_played"] + K_SHRINK)
    da = (as_["goals_against"] + K_SHRINK * la_h) / (as_["matches_played"] + K_SHRINK)
    hx = ah * da / la_h
    ax = aa * dh / la_a
    hx *= _form_factor(hs["form"] or "")
    ax *= _form_factor(as_["form"] or "")
    hx = max(0.6, min(3.0, round(hx, 2)))
    ax = max(0.6, min(3.0, round(ax, 2)))
    tot = hx + ax
    if tot > 4.5:
        r = 4.5 / tot
        hx = round(hx * r, 2); ax = round(ax * r, 2)
    return hx, ax


'''
c = c[:idx] + v2e_func + c[idx:]

# 4. Appel ligne 811
old_call = "home_xg, away_xg = calc_expected_goals_v2(code, home, away)"
new_call = "home_xg, away_xg = calc_expected_goals_v2e(code, home, away)"
c = c.replace(old_call, new_call, 1)

# 5. predict_all_markets : Dixon-Coles + renormalisation
old_pam = (
    "def predict_all_markets(home_xg: float, away_xg: float) -> dict:\n"
    "    MAX_GOALS = 10\n"
    "    score_probs = {}\n"
    "    for h in range(MAX_GOALS + 1):\n"
    "        p_h = poisson_prob(h, home_xg)\n"
    "        for a in range(MAX_GOALS + 1):\n"
    "            p_a = poisson_prob(a, away_xg)\n"
    "            score_probs[(h, a)] = p_h * p_a\n"
)
new_pam = (
    "def predict_all_markets(home_xg: float, away_xg: float) -> dict:\n"
    "    MAX_GOALS = 10\n"
    "    score_probs = {}\n"
    "    total_prob = 0.0\n"
    "    for h in range(MAX_GOALS + 1):\n"
    "        p_h = poisson_prob(h, home_xg)\n"
    "        for a in range(MAX_GOALS + 1):\n"
    "            p_a = poisson_prob(a, away_xg)\n"
    "            p = p_h * p_a * _tau(h, a, home_xg, away_xg)\n"
    "            score_probs[(h, a)] = p\n"
    "            total_prob += p\n"
    "    if total_prob > 0:\n"
    "        for k in score_probs:\n"
    "            score_probs[k] /= total_prob\n"
)
c = c.replace(old_pam, new_pam, 1)

with open("main.py", "w") as f:
    f.write(c)

print("OK: main.py patche")
