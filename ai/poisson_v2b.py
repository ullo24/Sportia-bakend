# ai/poisson_v2b.py
# Identique à v2a SAUF le calcul attack/defense qui utilise les splits
# domicile/extérieur quand disponibles (fallback sur global si < 3 matchs).
import math

HOME_ADVANTAGE = 1.18
LEAGUE_AVG_GOALS = {
    "PL": 2.85, "PD": 2.65, "SA": 2.75, "BL1": 3.15, "FL1": 2.70,
    "DED": 3.20, "PPL": 2.55, "CL": 2.80, "EC": 2.60, "WC": 2.70,
    "EL": 2.60, "UECL": 2.60, "MLS": 2.80,
}
_SQRT_HA = math.sqrt(HOME_ADVANTAGE)


def poisson_prob(k, lam):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _rate(num, den, fallback_num, fallback_den, min_n=3):
    """Utilise le taux split si assez d'échantillon, sinon fallback global."""
    if den >= min_n:
        return num / den
    return fallback_num / max(fallback_den, 1)


def calc_expected_goals_v2b(league_code, home_stats, away_stats):
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)

    home_ok = home_stats and home_stats["matches_played"] >= 3
    away_ok = away_stats and away_stats["matches_played"] >= 3

    if not home_ok or not away_ok:
        home_xg = (base / 2.0) * _SQRT_HA
        away_xg = (base / 2.0) / _SQRT_HA
        return max(0.5, round(home_xg, 2)), max(0.5, round(away_xg, 2))

    home_mp = max(home_stats["matches_played"], 1)
    away_mp = max(away_stats["matches_played"], 1)
    home_ppm = home_stats["points"] / home_mp
    away_ppm = away_stats["points"] / away_mp

    if home_ppm + away_ppm < 0.5:
        home_xg = (base / 2.0) * _SQRT_HA
        away_xg = (base / 2.0) / _SQRT_HA
        return max(0.5, round(home_xg, 2)), max(0.5, round(away_xg, 2))

    home_ppm = max(home_ppm, away_ppm * 0.33)
    away_ppm = max(away_ppm, home_ppm * 0.33)
    total_ppm = home_ppm + away_ppm
    home_ratio = home_ppm / total_ppm
    away_ratio = 1.0 - home_ratio

    home_xg = base * home_ratio * _SQRT_HA
    away_xg = base * away_ratio / _SQRT_HA

    # ⭐ SEUL CHANGEMENT : taux attack/defense calculés sur splits dom/ext
    home_attack = _rate(home_stats["goals_for_home"], home_stats["n_home"],
                        home_stats["goals_for"], home_stats["matches_played"])
    home_defense = _rate(home_stats["goals_against_home"], home_stats["n_home"],
                         home_stats["goals_against"], home_stats["matches_played"])
    away_attack = _rate(away_stats["goals_for_away"], away_stats["n_away"],
                        away_stats["goals_for"], away_stats["matches_played"])
    away_defense = _rate(away_stats["goals_against_away"], away_stats["n_away"],
                         away_stats["goals_against"], away_stats["matches_played"])

    league_avg_home = base / 2.0 * _SQRT_HA
    league_avg_away = base / 2.0 / _SQRT_HA

    home_attack_ratio = home_attack / league_avg_home if league_avg_home > 0 else 1.0
    away_defense_ratio = away_defense / league_avg_home if league_avg_home > 0 else 1.0
    away_attack_ratio = away_attack / league_avg_away if league_avg_away > 0 else 1.0
    home_defense_ratio = home_defense / league_avg_away if league_avg_away > 0 else 1.0

    home_attack_factor = (home_attack_ratio + 0.5) / (away_defense_ratio + 0.5)
    away_attack_factor = (away_attack_ratio + 0.5) / (home_defense_ratio + 0.5)

    home_xg *= (0.75 + 0.25 * home_attack_factor)
    away_xg *= (0.75 + 0.25 * away_attack_factor)

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

    home_xg = max(0.6, min(3.0, round(home_xg, 2)))
    away_xg = max(0.6, min(3.0, round(away_xg, 2)))

    total = home_xg + away_xg
    if total > 4.5:
        ratio = 4.5 / total
        home_xg = round(home_xg * ratio, 2)
        away_xg = round(away_xg * ratio, 2)

    return home_xg, away_xg


def compute_1x2(home_xg, away_xg, max_goals=10):
    home_win = draw = away_win = 0.0
    for h in range(max_goals + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(max_goals + 1):
            p = p_h * poisson_prob(a, away_xg)
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
    total = home_win + draw + away_win
    return home_win / total, draw / total, away_win / total


def predict_match_v2b(home_stats, away_stats, league_code, **kwargs):
    home_xg, away_xg = calc_expected_goals_v2b(league_code, home_stats, away_stats)
    ph, pd, pa = compute_1x2(home_xg, away_xg)
    probs = (ph, pd, pa)
    pick = "HDA"[int(max(range(3), key=lambda i: probs[i]))]
    return {"probs": probs, "pick": pick, "xg": (home_xg, away_xg)}
