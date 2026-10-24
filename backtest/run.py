import json
from pathlib import Path
from .metrics import (accuracy_1x2, brier_score_1x2, log_loss_1x2,
                      calibration_table)
from .dataset import (load_finished_matches, build_team_history, stats_before)

# ⚠️ À adapter : importe ta fonction de prédiction actuelle
from ai.poisson_v1 import predict_match_v1

MIN_HISTORY = 5  # matchs minimum pour prédire
OUTPUT = Path(__file__).parent / "baseline.json"

def run_backtest(engine_name="v1", predictor=predict_match_v1,
                 min_date="2024-01-01"):
    matches = load_finished_matches(min_date=min_date)
    print(f"Matchs chargés: {len(matches)}")
    history = build_team_history(matches)

    preds, probs, actuals, confidences, outcomes = [], [], [], [], []
    skipped = 0

    for m in matches:
        h_stats = stats_before(history, m['home_team'], m['kickoff'], n=10)
        a_stats = stats_before(history, m['away_team'], m['kickoff'], n=10)
        if not h_stats or not a_stats \
           or h_stats['n'] < MIN_HISTORY or a_stats['n'] < MIN_HISTORY:
            skipped += 1
            continue

        result = predictor(
            home_stats=h_stats, away_stats=a_stats,
            league=m['league'], kickoff=m['kickoff'],
        )
        # result attendu: {'probs': (ph, pd, pa), 'pick': 'H'/'D'/'A'}

        ph, pd, pa = result['probs']
        actual = ('H' if m['home_goals'] > m['away_goals']
                  else 'A' if m['home_goals'] < m['away_goals'] else 'D')

        preds.append(result['pick'])
        probs.append((ph, pd, pa))
        actuals.append(actual)
        pick_idx = {'H': 0, 'D': 1, 'A': 2}[result['pick']]
        confidences.append((ph, pd, pa)[pick_idx])
        outcomes.append(1 if result['pick'] == actual else 0)

    metrics = {
        'engine': engine_name,
        'n_matches': len(actuals),
        'n_skipped': skipped,
        'accuracy_1x2': round(accuracy_1x2(preds, actuals), 4),
        'brier_1x2': round(brier_score_1x2(probs, actuals), 4),
        'log_loss_1x2': round(log_loss_1x2(probs, actuals), 4),
        'calibration': calibration_table(confidences, outcomes),
    }
    print(json.dumps(metrics, indent=2))
    with open(OUTPUT, 'w') as f:
        json.dump(metrics, f, indent=2)
    return metrics

if __name__ == "__main__":
    run_backtest()
