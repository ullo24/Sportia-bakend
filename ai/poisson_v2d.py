# ai/poisson_v2d.py
# Réécriture propre de la formule xG.
# Remplace ppm + facteur empirique par la formule standard :
#   lambda_home = attack_home * defense_away / league_avg_home
#   lambda_away = attack_away * defense_home / league_avg_away
# avec shrinkage bayésien (K=5) sur les taux.
# Splits dom/ext utilisés automatiquement via le shrinkage.
import math

HOME_ADVANTAGE = 1.18
LEAGUE_AVG_GOALS = {
    "PL": 2.85, "PD": 2.65, "SA": 2.75, "BL1": 3.15, "FL1": 2.70,
    "DED": 3.20, "PPL": 2.55, "CL": 2.80, "EC": 2.60, "WC": 2.70,
    "EL": 2.60, "UECL": 2.60, "MLS": 2.80,
}
_SQRT_HA = math.sqrt(HOME_ADVANTAGE)
RHO = -0.10
K_SHRINK = 5.0


def poisson_prob(k, lam):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _tau(h, a, lh, la, rho=RHO):
    if h == 0 and a == 0: return 1 - lh * la * rho
    if h == 0 and a == 1: return 1 + lh * rho
    if h == 1 and a == 0: return 1 + la * rho
    if h == 1 and a == 1: return 1 - rho
    return 1.0


def _form_factor(form_str):
    if not form_str: return 1.0
    w = form_str.upper().count("W")
    d = form_str.upper().count("D")
    t = len(form_str)
    if t == 0: return 1.0
    r = (w * 3 + d) / (t * 3) if t * 3 > 0 else 0.5
    return 0.90 + (r * 0.20)


def calc_expected_goals_v2d(league_code, home_stats, away_stats):
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)

    if (not home_stats or not away_stats
            or home_stats["matches_played"] < 3
            or away_stats["matches_played"] < 3):
        return ((base / 2.0) * _SQRT_HA, (base / 2.0) / _SQRT_HA)

    league_avg_home = (base / 2.0) * _SQRT_HA
    league_avg_away = (base / 2.0) / _SQRT_HA

    attack_home = (home_stats["goals_for_home"] + K_SHRINK * league_avg_home) \
                  / (home_stats["n_home"] + K_SHRINK)
    defense_home = (home_stats["goals_against_home"] + K_SHRINK * league_avg_away) \
                   / (home_stats["n_home"] + K_SHRINK)
    attack_away = (away_stats["goals_for_away"] + K_SHRINK * league_avg_away) \
                  / (away_stats["n_away"] + K_SHRINK)
    defense_away = (away_stats["goals_against_away"] + K_SHRINK * league_avg_home) \
                   / (away_stats["n_away"] + K_SHRINK)

    home_xg = attack_home * defense_away / league_avg_home
    away_xg = attack_away * defense_home / league_avg_away

    home_xg *= _form_factor(home_stats["form"] or "")
    away_xg *= _form_factor(away_stats["form"] or "")

    home_xg = max(0.6, min(3.0, round(home_xg, 2)))
    away_xg = max(0.6, min(3.0, round(away_xg, 2)))
    total = home_xg + away_xg
    if total > 4.5:
        r = 4.5 / total
        home_xg = round(home_xg * r, 2)
        away_xg = round(away_xg * r, 2)

    return home_xg, away_xg


def compute_1x2(home_xg, away_xg, max_goals=10, rho=RHO):
    home_win = draw = away_win = 0.0
    total_prob = 0.0
    for h in range(max_goals + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(max_goals + 1):
            p = p_h * poisson_prob(a, away_xg) * _tau(h, a, home_xg, away_xg, rho)
            total_prob += p
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
    return home_win / total_prob, draw / total_prob, away_win / total_prob


def predict_match_v2d(home_stats, away_stats, league_code, **kwargs):
    home_xg, away_xg = calc_expected_goals_v2d(league_code, home_stats, away_stats)
    ph, pd, pa = compute_1x2(home_xg, away_xg)
    probs = (ph, pd, pa)
    pick = "HDA"[int(max(range(3), key=lambda i: probs[i]))]
    return {"probs": probs, "pick": pick, "xg": (home_xg, away_xg)}
