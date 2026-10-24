import itertools, json
from pathlib import Path
from .dataset import load_finished_matches, build_team_history, stats_before
from .metrics import accuracy_1x2, brier_score_1x2, log_loss_1x2
from ai.poisson_v2e import calc_expected_goals_v2e, compute_1x2

MIN_HISTORY = 5

def run():
    matches = load_finished_matches()
    history = build_team_history(matches)
    eval_set = []
    for m in matches:
        h = stats_before(history, m["home"], m["kickoff"])
        a = stats_before(history, m["away"], m["kickoff"])
        if (not h or not a or h["matches_played"] < MIN_HISTORY
                or a["matches_played"] < MIN_HISTORY):
            continue
        actual = ("H" if m["home_goals"] > m["away_goals"]
                  else "A" if m["home_goals"] < m["away_goals"] else "D")
        eval_set.append((h, a, m["league_code"], actual))
    print(f"Matchs évaluables : {len(eval_set)}\n")
    print(f"{'alpha':>6} {'acc':>7} {'brier':>7} {'logloss':>8}")
    print("-" * 35)
    for alpha in [1.0, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70]:
        preds, probs_list, actuals = [], [], []
        for h, a, lg, actual in eval_set:
            hxg, axg = calc_expected_goals_v2e(lg, h, a)
            ph, pd, pa = compute_1x2(hxg, axg)
            raw = (ph, pd, pa)
            pw = tuple(p ** alpha for p in raw)
            s = sum(pw)
            probs = tuple(p / s for p in pw)
            pick = "HDA"[int(max(range(3), key=lambda i: probs[i]))]
            preds.append(pick); probs_list.append(probs); actuals.append(actual)
        acc = accuracy_1x2(preds, actuals)
        brier = brier_score_1x2(probs_list, actuals)
        ll = log_loss_1x2(probs_list, actuals)
        print(f"{alpha:>6.2f} {acc:>7.4f} {brier:>7.4f} {ll:>8.4f}")

if __name__ == "__main__":
    run()
