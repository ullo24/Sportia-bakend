import numpy as np

def accuracy_1x2(preds, actuals):
    """preds, actuals: listes de 'H'/'D'/'A'"""
    return sum(p == a for p, a in zip(preds, actuals)) / len(actuals)

def brier_score_1x2(probs, actuals):
    """probs: liste de tuples (p_home, p_draw, p_away); actuals: 'H'/'D'/'A'"""
    targets = {'H': (1,0,0), 'D': (0,1,0), 'A': (0,0,1)}
    score = 0.0
    for (ph, pd, pa), actual in zip(probs, actuals):
        t = targets[actual]
        score += (ph-t[0])**2 + (pd-t[1])**2 + (pa-t[2])**2
    return score / len(actuals)

def log_loss_1x2(probs, actuals, eps=1e-15):
    targets = {'H': 0, 'D': 1, 'A': 2}
    losses = []
    for p, actual in zip(probs, actuals):
        p_actual = max(p[targets[actual]], eps)
        losses.append(-np.log(p_actual))
    return float(np.mean(losses))

def calibration_table(confidences, outcomes, n_buckets=10):
    """confidences: proba prédite de l'issue choisie [0..1]; outcomes: 1/0"""
    buckets = [[] for _ in range(n_buckets)]
    for c, o in zip(confidences, outcomes):
        i = min(int(c * n_buckets), n_buckets - 1)
        buckets[i].append((c, o))
    table = []
    for i, b in enumerate(buckets):
        if not b: continue
        avg_conf = float(np.mean([x[0] for x in b]))
        avg_acc = float(np.mean([x[1] for x in b]))
        table.append({
            'bucket': f"{i*10}-{(i+1)*10}%",
            'n': len(b),
            'conf': round(avg_conf, 3),
            'acc': round(avg_acc, 3),
            'gap': round(avg_acc - avg_conf, 3),
        })
    return table
