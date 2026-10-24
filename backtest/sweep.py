# backtest/sweep.py
# Sweep des hyperparamètres de v2d : K_SHRINK × RHO × form_factor.
# Réutilise le dataset walk-forward de backtest.run, affiche un tableau trié par brier.
import itertools
import json
import math
from pathlib import Path

from .dataset import load_finished_matches, build_team_history, stats_before
from .metrics import accuracy_1x2, brier_score_1x2, log_loss_1x2
from ai.poisson_v2d import LEAGUE_AVG_GOALS, _SQRT_HA, poisson_prob, _tau

MIN_HISTORY = 5
MAX_GOALS = 10


def _form_factor(form_str, use_form):
    if not use_form or not form_str:
        return 1.0
    w = form_str.upper().count("W")
    d = form_str.upper().count("D")
    t = len(form_str)
    if t == 0:
        return 1.0
    r = (w * 3 + d) / (t * 3) if t * 3 > 0 else 0.5
    return 0.90 + (r * 0.20)


def predict_with_params(h_stats, a_stats, league_code, K, rho, use_form):
    base = LEAGUE_AVG_GOALS.get(league_code, 2.7)
    league_avg_home = (base / 2.0) * _SQRT_HA
    league_avg_away = (base / 2.0) / _SQRT_HA

    attack_home = (h_stats["goals_for_home"] + K * league_avg_home) \
                  / (h_stats["n_home"] + K)
    defense_home = (h_stats["goals_against_home"] + K * league_avg_away) \
                   / (h_stats["n_home"] + K)
    attack_away = (a_stats["goals_for_away"] + K * league_avg_away) \
                  / (a_stats["n_away"] + K)
    defense_away = (a_stats["goals_against_away"] + K * league_avg_home) \
                   / (a_stats["n_away"] + K)

    home_xg = attack_home * defense_away / league_avg_home
    away_xg = attack_away * defense_home / league_avg_away
    home_xg *= _form_factor(h_stats["form"] or "", use_form)
    away_xg *= _form_factor(a_stats["form"] or "", use_form)
    home_xg = max(0.6, min(3.0, home_xg))
    away_xg = max(0.6, min(3.0, away_xg))
    total = home_xg + away_xg
    if total > 4.5:
        r = 4.5 / total
        home_xg *= r
        away_xg *= r

    home_win = draw = away_win = 0.0
    total_prob = 0.0
    for h in range(MAX_GOALS + 1):
        p_h = poisson_prob(h, home_xg)
        for a in range(MAX_GOALS + 1):
            p = p_h * poisson_prob(a, away_xg) * _tau(h, a, home_xg, away_xg, rho)
            total_prob += p
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
    probs = (home_win / total_prob, draw / total_prob, away_win / total_prob)
    pick = "HDA"[int(max(range(3), key=lambda i: probs[i]))]
    return probs, pick


def run_sweep():
    matches = load_finished_matches()
    print(f"Matchs chargés : {len(matches)}")
    history = build_team_history(matches)

    eval_set = []
    for m in matches:
        h_stats = stats_before(history, m["home"], m["kickoff"])
        a_stats = stats_before(history, m["away"], m["kickoff"])
        if (not h_stats or not a_stats
                or h_stats["matches_played"] < MIN_HISTORY
                or a_stats["matches_played"] < MIN_HISTORY):
            continue
        actual = ("H" if m["home_goals"] > m["away_goals"]
                  else "A" if m["home_goals"] < m["away_goals"] else "D")
        eval_set.append((h_stats, a_stats, m["league_code"], actual))
    print(f"Matchs évaluables : {len(eval_set)}\n")

    combos = list(itertools.product([3, 5, 10], [-0.05, -0.10, -0.15, -0.20],
                                    [True, False]))
    results = []
    print(f"{'K':>3} {'rho':>6} {'form':>5} "
          f"{'acc':>7} {'brier':>7} {'logloss':>8}")
    print("-" * 45)
    for K, rho, use_form in combos:
        preds, probs_list, actuals = [], [], []
        for h_stats, a_stats, league_code, actual in eval_set:
            probs, pick = predict_with_params(h_stats, a_stats, league_code,
                                              K, rho, use_form)
            preds.append(pick)
            probs_list.append(probs)
            actuals.append(actual)
        acc = accuracy_1x2(preds, actuals)
        brier = brier_score_1x2(probs_list, actuals)
        ll = log_loss_1x2(probs_list, actuals)
        results.append({"K": K, "rho": rho, "form": use_form,
                        "acc": acc, "brier": brier, "logloss": ll})
        print(f"{K:>3} {rho:>6.2f} {str(use_form):>5} "
              f"{acc:>7.4f} {brier:>7.4f} {ll:>8.4f}")

    results.sort(key=lambda r: r["brier"])
    best = results[0]
    print("\n" + "=" * 45)
    print(f"🏆 Meilleur (brier) : K={best['K']} rho={best['rho']} "
          f"form={best['form']}")
    print(f"   acc={best['acc']:.4f} brier={best['brier']:.4f} "
          f"logloss={best['logloss']:.4f}")

    out = Path(__file__).parent / "results" / "sweep_v2d.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nTous les résultats dans {out}")


if __name__ == "__main__":
    run_sweep()
