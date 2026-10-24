# backtest/run.py
"""
Usage :
  python -m backtest.run v1              # baseline v1
  python -m backtest.run v2a             # après fix HOME_ADVANTAGE
  python -m backtest.run v2b             # après split domicile/extérieur
  ...
""" 
import json
import sys
from pathlib import Path

from .metrics import accuracy_1x2, brier_score_1x2, log_loss_1x2, calibration_table
from .dataset import load_finished_matches, build_team_history, stats_before

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

MIN_HISTORY = 5


def _load_predictor(engine):
    if engine == "v1":
        from ai.poisson_v1 import predict_match_v1 as fn
    elif engine == "v2a":
        from ai.poisson_v2a import predict_match_v2a as fn
    elif engine == "v2b":
        from ai.poisson_v2b import predict_match_v2b as fn
    elif engine == "v2c":
        from ai.poisson_v2c import predict_match_v2c as fn
    elif engine == "v2d":
        from ai.poisson_v2d import predict_match_v2d as fn
    else:
        raise SystemExit(f"Engine inconnu : {engine}")
    return fn


def run(engine="v1", min_date=None):
    predictor = _load_predictor(engine)
    matches = load_finished_matches(min_date=min_date)
    print(f"[{engine}] Matchs terminés chargés : {len(matches)}")
    history = build_team_history(matches)

    preds, probs, actuals, confs, outs = [], [], [], [], []
    skipped = 0

    for m in matches:
        h_stats = stats_before(history, m["home"], m["kickoff"])
        a_stats = stats_before(history, m["away"], m["kickoff"])
        if (not h_stats or not a_stats
                or h_stats["matches_played"] < MIN_HISTORY
                or a_stats["matches_played"] < MIN_HISTORY):
            skipped += 1
            continue

        result = predictor(h_stats, a_stats, m["league_code"])
        ph, pd, pa = result["probs"]
        actual = ("H" if m["home_goals"] > m["away_goals"]
                  else "A" if m["home_goals"] < m["away_goals"] else "D")

        preds.append(result["pick"])
        probs.append((ph, pd, pa))
        actuals.append(actual)
        pick_idx = {"H": 0, "D": 1, "A": 2}[result["pick"]]
        confs.append(probs[-1][pick_idx])
        outs.append(1 if result["pick"] == actual else 0)

    metrics = {
        "engine": engine,
        "n_evaluated": len(actuals),
        "n_skipped": skipped,
        "accuracy_1x2": round(accuracy_1x2(preds, actuals), 4),
        "brier_1x2": round(brier_score_1x2(probs, actuals), 4),
        "log_loss_1x2": round(log_loss_1x2(probs, actuals), 4),
        "calibration": calibration_table(confs, outs),
    }
    out_file = RESULTS_DIR / f"{engine}.json"
    out_file.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print(f"\nSauvegardé dans {out_file}")
    return metrics


def compare(engines):
    """Affiche un tableau comparatif de plusieurs runs."""
    rows = []
    for e in engines:
        f = RESULTS_DIR / f"{e}.json"
        if not f.exists():
            print(f"⚠️  {f} manquant, skip {e}")
            continue
        rows.append(json.loads(f.read_text()))
    if not rows:
        return
    header = f"{'engine':<8} {'n':>6} {'acc':>7} {'brier':>7} {'logloss':>8}"
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['engine']:<8} {r['n_evaluated']:>6} "
              f"{r['accuracy_1x2']:>7.4f} {r['brier_1x2']:>7.4f} "
              f"{r['log_loss_1x2']:>8.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        run("v1")
    elif sys.argv[1] == "compare":
        compare(sys.argv[2:] if len(sys.argv) > 2 else ["v1"])
    else:
        run(sys.argv[1])
