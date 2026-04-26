"""
Auto-tuning configuration for AlphaInfo skill.

The skill doesn't just route to native methods — it can also probe small
budgets of quota to FIND the best configuration for the user's specific data,
instead of relying on the LLM (or developer) to guess the right reference,
classifier, baseline, or window.

This solves the documented case where naive config (e.g., sine reference for
ECG) gives 50% accuracy and proper config (mean-beat reference + k-NN on
standardized fingerprints) gives 95% — same data, same skill, same API.

Each function accepts a `budget` (max quota to spend on tuning) which auto-
adjusts to the user's plan. Returns the best config plus the predictions /
results from that config so the caller doesn't redo work.
"""
from __future__ import annotations
from typing import Sequence, Callable, Any
import itertools
import numpy as np
from alphainfo import AlphaInfo

from .plan import adapt


DIMS = ['sim_local', 'sim_fractal', 'sim_spectral', 'sim_transition', 'sim_trend']


def _safe_fp(client: AlphaInfo,
             signal: list[float],
             baseline: list[float],
             sampling_rate: float,
             domain: str) -> np.ndarray | None:
    """Get fingerprint, returning None on failure."""
    try:
        r = client.analyze(signal=signal, baseline=baseline,
                           sampling_rate=sampling_rate, domain=domain,
                           use_multiscale=True)
        if not r.metrics:
            return None
        return np.array([r.metrics.get(d, 0.0) for d in DIMS])
    except Exception:
        return None


def _accuracy(preds: list, truth: list) -> float:
    if not truth:
        return 0.0
    # None predictions count as wrong (e.g., LDA failed for that fold)
    return sum(p is not None and p == t for p, t in zip(preds, truth)) / len(truth)


# ─────────────────────────────────────────────────────────────────
# 1. autotune_classifier
#    Tries multiple (reference, classifier) combos, picks best by
#    leave-one-out cross-validation on the training set.
# ─────────────────────────────────────────────────────────────────

def autotune_classifier(client: AlphaInfo,
                        labeled_signals: list[tuple[str, Sequence[float]]],
                        plan: dict[str, Any],
                        sampling_rate: float = 10.0,
                        domain: str = 'generic',
                        budget: int | None = None) -> dict[str, Any]:
    """Find the best (reference, classifier) combo for THIS labeled training set.

    Args:
        labeled_signals: list of (label, signal) pairs. Need at least 4 per class.
        plan: from detect_plan()
        budget: max quota units to spend tuning. If None, defaults to plan-aware.

    Returns dict:
        best_config: {'reference_strategy': str, 'classifier': str, 'normalize': bool}
        cv_accuracy: float (leave-one-out accuracy of best config)
        all_configs: list of (config, accuracy) tuples
        predict: callable(signal) -> predicted_label  (uses 1 quota per call)
        quota_used: int

    Strategy: enumerate {ref_strategy} × {classifier}, score each by LOOCV.
    """
    # Group signals by label
    by_label: dict[str, list[list[float]]] = {}
    for label, sig in labeled_signals:
        by_label.setdefault(label, []).append(list(sig))

    classes = list(by_label.keys())
    if len(classes) < 2:
        raise ValueError("Need ≥ 2 classes")
    min_per_class = min(len(by_label[c]) for c in classes)
    if min_per_class < 4:
        raise ValueError(f"Need ≥ 4 samples per class (got min {min_per_class})")

    # Plan-aware budget default. Target ≥5 samples per class for reliable LOOCV.
    if budget is None:
        budget = {'free': 24, 'starter': 50, 'growth': 80,
                  'professional': 120, 'enterprise': 150}.get(plan['slug'], 30)

    # Reference strategies. For Free, drop the 'sine' negative control to save budget.
    if plan['slug'] == 'free':
        reference_strategies = ['mean_class_0', 'median_class_0']
    else:
        reference_strategies = ['mean_class_0', 'median_class_0', 'sine']

    classifiers = [
        ('centroid_raw', False),
        ('centroid_norm', True),
        ('knn_norm', True),
        ('lda_norm', True),
    ]

    n_refs = len(reference_strategies)
    n_classes = len(classes)
    # Each ref requires fingerprinting N samples × n_classes
    # Target n_train per class such that total quota = n_train * n_classes * n_refs <= budget
    # Minimum 4 per class for meaningful LOOCV
    target_per_class = max(4, budget // (n_refs * n_classes))
    n_train = min(min_per_class, target_per_class)

    if n_train < 4:
        # Can't tune meaningfully — fall back to a single sensible config
        return {
            'best_config': {'reference_strategy': 'mean_class_0', 'classifier': 'centroid_norm', 'normalize': True},
            'cv_accuracy': None,
            'all_configs': [],
            'quota_used': 0,
            'note': f'Budget {budget} too small for tuning (need ≥{4*n_refs*n_classes} for n_train≥4 with {n_refs} refs × {n_classes} classes).',
            'predict': None,
        }

    # Build references
    train_per_class = {c: by_label[c][:n_train] for c in classes}
    refs: dict[str, list[float]] = {}

    refs['mean_class_0'] = list(np.mean(train_per_class[classes[0]], axis=0))
    refs['median_class_0'] = list(np.median(train_per_class[classes[0]], axis=0))
    # sine of same length
    sample_len = len(train_per_class[classes[0]][0])
    import math
    refs['sine'] = [math.sin(2*math.pi*i/30) for i in range(sample_len)]

    quota_used = 0

    # Compute fingerprints: dict[(ref_name, class_idx, sample_idx)] = fp
    fps: dict[tuple, np.ndarray] = {}
    for ref_name in reference_strategies:
        for cls in classes:
            for i, sig in enumerate(train_per_class[cls]):
                fp = _safe_fp(client, sig, refs[ref_name], sampling_rate, domain)
                quota_used += 1
                if fp is not None:
                    fps[(ref_name, cls, i)] = fp

    # Cross-validate every (ref, classifier) combo using LOOCV
    results: list[dict[str, Any]] = []
    for ref_name in reference_strategies:
        # Gather fingerprints under this ref
        fp_array = []
        labels = []
        for cls in classes:
            for i in range(n_train):
                if (ref_name, cls, i) in fps:
                    fp_array.append(fps[(ref_name, cls, i)])
                    labels.append(cls)
        if len(fp_array) < 2 * len(classes):
            continue
        X = np.array(fp_array)

        for clf_name, normalize in classifiers:
            preds = _loocv_predict(X, labels, clf_name, normalize)
            acc = _accuracy(preds, labels)
            results.append({
                'reference_strategy': ref_name,
                'classifier': clf_name,
                'normalize': normalize,
                'cv_accuracy': acc,
            })

    # Pick best
    if not results:
        return {
            'best_config': None, 'cv_accuracy': None, 'all_configs': [],
            'quota_used': quota_used, 'predict': None,
            'note': 'All fingerprint calls failed.',
        }

    results.sort(key=lambda r: r['cv_accuracy'], reverse=True)
    best = results[0]

    # Build a closure that classifies new signals using the winning config
    best_ref = refs[best['reference_strategy']]

    # Pre-compute centroids/training for the best config
    train_X = []
    train_y = []
    for cls in classes:
        for i in range(n_train):
            key = (best['reference_strategy'], cls, i)
            if key in fps:
                train_X.append(fps[key])
                train_y.append(cls)
    train_X = np.array(train_X)
    if best['normalize']:
        mu = train_X.mean(axis=0)
        sd = train_X.std(axis=0) + 1e-9
        train_X_proc = (train_X - mu) / sd
    else:
        mu = None; sd = None
        train_X_proc = train_X

    centroids = {c: train_X_proc[[i for i, y in enumerate(train_y) if y == c]].mean(axis=0)
                 for c in classes}
    if best['classifier'] == 'lda_norm':
        try:
            sw = sum(np.cov(train_X_proc[[i for i, y in enumerate(train_y) if y == c]].T)
                     for c in classes)
            w = np.linalg.pinv(sw) @ (centroids[classes[0]] - centroids[classes[1]])
            threshold = (w @ centroids[classes[0]] + w @ centroids[classes[1]]) / 2
            cls0_high = (w @ centroids[classes[0]]) > threshold
        except (np.linalg.LinAlgError, ValueError):
            # Fallback to centroid_norm
            best['classifier'] = 'centroid_norm'
            w = None; threshold = None; cls0_high = None
    else:
        w = None; threshold = None; cls0_high = None

    def predict(new_signal: Sequence[float]) -> str:
        """Classify a new signal using the winning config. Uses 1 quota."""
        fp = _safe_fp(client, list(new_signal), best_ref, sampling_rate, domain)
        if fp is None:
            return None
        if best['normalize']:
            fp = (fp - mu) / sd
        if best['classifier'] in ('centroid_raw', 'centroid_norm'):
            return min(centroids, key=lambda c: np.linalg.norm(fp - centroids[c]))
        if best['classifier'] == 'knn_norm':
            dists = np.linalg.norm(train_X_proc - fp, axis=1)
            k = min(3, len(train_y))
            nearest = np.argsort(dists)[:k]
            ys = [train_y[i] for i in nearest]
            return max(set(ys), key=ys.count)
        if best['classifier'] == 'lda_norm':
            high = (w @ fp) > threshold
            return classes[0] if high == cls0_high else classes[1]
        return None

    return {
        'best_config': {
            'reference_strategy': best['reference_strategy'],
            'classifier': best['classifier'],
            'normalize': best['normalize'],
        },
        'cv_accuracy': best['cv_accuracy'],
        'all_configs': results,
        'quota_used': quota_used,
        'predict': predict,
    }


def _loocv_predict(X: np.ndarray, y: list, clf_name: str, normalize: bool) -> list:
    """Leave-one-out cross-validation predictions for a given classifier."""
    n = len(y)
    classes = list(set(y))
    preds = []

    for i in range(n):
        mask = np.ones(n, dtype=bool); mask[i] = False
        train_X = X[mask]
        train_y = [y[j] for j in range(n) if mask[j]]

        if normalize:
            mu = train_X.mean(axis=0)
            sd = train_X.std(axis=0) + 1e-9
            train_proc = (train_X - mu) / sd
            test_proc = (X[i] - mu) / sd
        else:
            train_proc = train_X
            test_proc = X[i]

        if clf_name in ('centroid_raw', 'centroid_norm'):
            cents = {c: train_proc[[j for j, yy in enumerate(train_y) if yy == c]].mean(axis=0)
                     for c in classes}
            preds.append(min(cents, key=lambda c: np.linalg.norm(test_proc - cents[c])))
        elif clf_name == 'knn_norm':
            dists = np.linalg.norm(train_proc - test_proc, axis=1)
            k = min(3, len(train_y))
            nearest = np.argsort(dists)[:k]
            ys = [train_y[j] for j in nearest]
            preds.append(max(set(ys), key=ys.count))
        elif clf_name == 'lda_norm':
            if len(classes) != 2:
                preds.append(None)
                continue
            # LDA needs ≥3 samples per class to have non-degenerate covariance
            counts = {c: sum(1 for yy in train_y if yy == c) for c in classes}
            if min(counts.values()) < 3:
                preds.append(None)
                continue
            try:
                cents = {c: train_proc[[j for j, yy in enumerate(train_y) if yy == c]].mean(axis=0)
                         for c in classes}
                sw = sum(np.cov(train_proc[[j for j, yy in enumerate(train_y) if yy == c]].T)
                         for c in classes)
                w = np.linalg.pinv(sw) @ (cents[classes[0]] - cents[classes[1]])
                threshold = (w @ cents[classes[0]] + w @ cents[classes[1]]) / 2
                cls0_high = (w @ cents[classes[0]]) > threshold
                high = (w @ test_proc) > threshold
                preds.append(classes[0] if high == cls0_high else classes[1])
            except (np.linalg.LinAlgError, ValueError):
                preds.append(None)
        else:
            preds.append(None)
    # Filter Nones from accuracy calc by replacing with empty string (always wrong)
    return preds


# ─────────────────────────────────────────────────────────────────
# 2. autotune_baseline
#    For "is this signal weird vs normal?" — finds the most stable baseline
#    from candidate strategies in the user's own data.
# ─────────────────────────────────────────────────────────────────

def autotune_baseline(client: AlphaInfo,
                      signal: Sequence[float],
                      plan: dict[str, Any],
                      sampling_rate: float = 10.0,
                      domain: str = 'generic',
                      budget: int | None = None) -> dict[str, Any]:
    """Try multiple baseline strategies. Pick the most stable.

    Strategies tested:
      - first_quarter: signal[:N//4]
      - last_quarter:  signal[-N//4:]
      - middle:        signal[N//4:-N//4]
      - mean_template: array of len N filled with median(signal)

    Returns dict with best_baseline (np.array), all_strategies + scores,
    and a `recommended_call` closure ready to use.
    """
    if budget is None:
        budget = {'free': 4, 'starter': 8, 'growth': 12,
                  'professional': 16, 'enterprise': 16}.get(plan['slug'], 8)

    sig = list(signal)
    N = len(sig)
    if N < 200:
        return {
            'best_baseline': sig[:N//4],
            'note': 'Signal too short for meaningful tuning. Used first_quarter.',
            'quota_used': 0,
        }

    candidates = {
        'first_quarter': sig[:N//4],
        'last_quarter':  sig[-N//4:],
        'middle':        sig[N//4:3*N//4],
        'median_template': [float(np.median(sig))] * (N//4),
    }

    # Test each baseline against the FULL signal — best baseline produces
    # most CONSISTENT score (closest to "structurally similar" across windows
    # OF THE BASELINE itself when re-evaluated).
    # Heuristic: a good baseline scores ~stable when compared to other regions
    # of the signal that should be similar to it.
    results = {}
    quota_used = 0
    for name, base in candidates.items():
        if quota_used >= budget:
            break
        # Compare baseline to a different chunk of the signal (mid-point)
        midchunk = sig[N//3:N//3 + len(base)]
        try:
            r = client.compare(signal=midchunk, baseline=base,
                               sampling_rate=sampling_rate, domain=domain,
                               include_semantic=True)
            results[name] = {
                'score': r.structural_score,
                'band': r.confidence_band,
            }
        except Exception:
            results[name] = {'score': 0.0, 'band': 'error'}
        quota_used += 1

    # Best = highest score (most representative of stable structure)
    if not results:
        return {'best_baseline': sig[:N//4], 'all_strategies': {}, 'quota_used': 0}

    best_name = max(results, key=lambda k: results[k]['score'])
    return {
        'best_baseline': candidates[best_name],
        'best_strategy': best_name,
        'best_score': results[best_name]['score'],
        'all_strategies': results,
        'quota_used': quota_used,
    }


# ─────────────────────────────────────────────────────────────────
# 3. autotune_window
#    Try multiple (window_size, step) combos for sliding-window monitoring.
#    Pick the combo with best contrast (gap between worst and best window).
# ─────────────────────────────────────────────────────────────────

def autotune_window(client: AlphaInfo,
                    signal: Sequence[float],
                    plan: dict[str, Any],
                    sampling_rate: float = 10.0,
                    domain: str = 'generic',
                    baseline: Sequence[float] | None = None,
                    budget: int | None = None) -> dict[str, Any]:
    """Try multiple window/step combos. Pick best contrast.

    A good window setup has high contrast: worst_window << best_window.
    Bad setups give windows all near 0.5 (no information).
    """
    if budget is None:
        budget = {'free': 6, 'starter': 12, 'growth': 24,
                  'professional': 40, 'enterprise': 60}.get(plan['slug'], 12)

    sig = list(signal)
    N = len(sig)
    if N < 200:
        return {
            'best_config': {'window_size': N//2, 'step': N//4},
            'note': 'Signal too short.',
            'quota_used': 0,
        }

    # Candidate windows: 5%, 10%, 20% of signal length
    candidate_windows = [
        max(50, N // 20),   # 5% — fine
        max(50, N // 10),   # 10% — medium
        max(50, N // 5),    # 20% — coarse
    ]
    # For each window, step = window // 2 (50% overlap)
    candidate_configs = [(w, max(10, w // 2)) for w in candidate_windows]

    # Estimate quota per config and prune to budget
    feasible = []
    for w, s in candidate_configs:
        n_w = max(1, (N - w) // s + 1)
        if n_w <= budget // len(candidate_configs):
            feasible.append((w, s, n_w))

    if not feasible:
        # Take the cheapest config
        w, s = candidate_configs[-1]  # largest window = fewest analyses
        n_w = max(1, (N - w) // s + 1)
        feasible = [(w, s, n_w)]

    results = []
    quota_used = 0
    for w, s, n_w in feasible:
        if quota_used + n_w > budget:
            continue
        try:
            r = client.analyze_windowed(signal=sig, window_size=w, step=s,
                                        sampling_rate=sampling_rate, domain=domain,
                                        baseline=list(baseline) if baseline else None)
            quota_used += n_w
            ws = r.get('windows', [])
            if ws:
                # Each window is (start, end, score) tuple
                scores = [w_[2] for w_ in ws if isinstance(w_, tuple) and len(w_) >= 3]
                if scores:
                    contrast = max(scores) - min(scores)
                    results.append({
                        'window_size': w, 'step': s, 'n_windows': n_w,
                        'contrast': contrast,
                        'min_score': min(scores), 'max_score': max(scores),
                    })
        except Exception:
            continue

    if not results:
        return {'best_config': None, 'all_configs': [], 'quota_used': quota_used}

    # Best = highest contrast = most informative
    results.sort(key=lambda r: r['contrast'], reverse=True)
    best = results[0]
    return {
        'best_config': {'window_size': best['window_size'], 'step': best['step']},
        'best_contrast': best['contrast'],
        'all_configs': results,
        'quota_used': quota_used,
    }


# ─────────────────────────────────────────────────────────────────
# 4. autotune_domain
#    Compare same call across 2-3 candidate domains. Pick the one with
#    most consistent / informative score.
# ─────────────────────────────────────────────────────────────────

DIM_FAILURE_TYPE = {
    'sim_local': 'fine-grained shape changed (jitter, noise pattern, warp)',
    'sim_fractal': 'self-similarity / complexity changed (fundamental regime shift)',
    'sim_spectral': 'frequency content shifted (new harmonics, oscillation drift)',
    'sim_transition': 'sharp transitions / abrupt events / regime boundary',
    'sim_trend': 'macro direction / slope shifted (drift, secular change)',
}


def inspect_fingerprint(client: AlphaInfo,
                        signal: Sequence[float],
                        baseline: Sequence[float],
                        sampling_rate: float = 10.0,
                        domain: str = 'generic') -> dict[str, Any] | None:
    """Inspect 5-D fingerprint to find specific dimension drops.

    The scalar `structural_score` averages the 5 dims. If one specific dim
    dropped dramatically (e.g., sim_spectral for added harmonics), the scalar
    might say "stable" while the API actually saw the change — just in one
    dimension.

    Returns dict with worst dim, value, failure type, and a synthesized
    severity score derived from the worst dim. None on failure.

    Cost: 1 quota.
    """
    try:
        r = client.analyze(signal=list(signal), baseline=list(baseline),
                           sampling_rate=sampling_rate, domain=domain,
                           use_multiscale=True, include_semantic=True)
        if not r.metrics:
            return None
        DIMS = ['sim_local', 'sim_fractal', 'sim_spectral', 'sim_transition', 'sim_trend']
        dims_values = {d: r.metrics.get(d) for d in DIMS if r.metrics.get(d) is not None}
        if not dims_values:
            return None
        worst_dim = min(dims_values, key=dims_values.get)
        worst_val = dims_values[worst_dim]
        # Severity from worst dim: dim<0.35→sev 90+, 0.5→sev 70, 0.7→sev 50
        # Use a more aggressive map: sev = (1 - worst_val) * 130, capped
        derived_sev = max(0, min(100, (1 - worst_val) * 130))
        return {
            'fingerprint': dims_values,
            'worst_dim': worst_dim,
            'worst_value': worst_val,
            'failure_type': DIM_FAILURE_TYPE.get(worst_dim, 'structural change'),
            'derived_severity': derived_sev,
            'scalar_score': r.structural_score,
            'analysis_id': r.analysis_id,
        }
    except Exception:
        return None


def _detect_amplitude_shift(signal: Sequence[float],
                             baseline: Sequence[float],
                             threshold_pct: float = 15.0) -> dict[str, Any] | None:
    """Heuristic: detect when structure is similar but means/stds differ a lot.

    AlphaInfo measures STRUCTURE. If two signals have the same shape but very
    different magnitude (e.g., latency 100ms→130ms with same gamma distribution),
    the structural score will be ~0.80 (not very anomalous) — but the user
    likely wants to know about the magnitude shift.

    Returns dict with shift info if detected, else None.
    """
    if not signal or not baseline:
        return None
    sig = list(signal)
    base = list(baseline)
    sig_mean = sum(sig) / len(sig)
    base_mean = sum(base) / len(base)
    if abs(base_mean) < 1e-9:
        return None
    pct_change = (sig_mean - base_mean) / abs(base_mean) * 100
    if abs(pct_change) < threshold_pct:
        return None

    # Also check std ratio
    sig_var = sum((x - sig_mean)**2 for x in sig) / max(1, len(sig))
    base_var = sum((x - base_mean)**2 for x in base) / max(1, len(base))
    sig_std = sig_var ** 0.5
    base_std = base_var ** 0.5
    std_ratio = (sig_std / base_std) if base_std > 1e-9 else None

    return {
        'pct_change_mean': pct_change,
        'baseline_mean': base_mean,
        'signal_mean': sig_mean,
        'std_ratio': std_ratio,
        'note': (f"⚠️ Mean shifted {pct_change:+.1f}% ({base_mean:.2f} → {sig_mean:.2f}). "
                 f"AlphaInfo measures structure; this looks like an AMPLITUDE shift. "
                 f"Combine with simple mean-comparison for the full picture."),
    }


def smart_compare(client: AlphaInfo,
                  signal: Sequence[float],
                  baseline: Sequence[float],
                  plan: dict[str, Any],
                  sampling_rate: float = 10.0,
                  domain: str = 'generic') -> dict[str, Any]:
    """Self-correcting comparison cascade.

    Same 3-stage pattern as smart_anomaly but for "is B different from A?":
      1. compare() with user's domain (1 quota)
      2. If borderline, try alternative domains (3 quota)
      3. If still borderline, escalate to sliding window (5-10 quota)

    PLUS: detects pure-amplitude shifts and warns the user that the answer
    may understate severity since AlphaInfo measures structure.
    """
    cascade = []
    quota = 0

    def _do_compare(d: str) -> dict | None:
        try:
            if d == 'auto':
                r = client.analyze_auto(signal=list(signal), baseline=list(baseline),
                                         sampling_rate=sampling_rate,
                                         include_semantic=True)
            else:
                r = client.compare(signal=list(signal), baseline=list(baseline),
                                   sampling_rate=sampling_rate, domain=d,
                                   include_semantic=True)
            return {
                'score': r.structural_score,
                'confidence_band': r.confidence_band,
                'alert_level': r.semantic.alert_level if r.semantic else None,
                'severity_score': r.semantic.severity_score if r.semantic else None,
                'summary': r.semantic.summary if r.semantic else None,
                'analysis_id': r.analysis_id,
            }
        except Exception:
            return None

    # Stage 1
    initial = _do_compare(domain)
    quota += 1
    if initial is None:
        return {'winning_result': None, 'method_used': 'failed',
                'cascade': cascade, 'quota_used': quota}
    cascade.append({'method': 'compare', 'config': f"domain={domain}",
                    'severity': initial.get('severity_score') or 0,
                    'alert': initial.get('alert_level')})
    sev = initial.get('severity_score') or 0

    # Always check for amplitude shift (free, no quota)
    amp_shift = _detect_amplitude_shift(signal, baseline)

    if sev > 65:
        result = dict(initial)
        if amp_shift:
            result['amplitude_shift'] = amp_shift
        return {'winning_result': result, 'method_used': 'compare',
                'cascade': cascade, 'quota_used': quota}

    # Stage 2: alternative domains
    for alt_dom in ['auto', 'security', 'sensors', 'ai_ml']:
        if alt_dom == domain or len([c for c in cascade if c['method'] == 'compare']) >= 4:
            continue
        r = _do_compare(alt_dom)
        quota += 1
        if r is None:
            continue
        cascade.append({'method': 'compare', 'config': f"domain={alt_dom}",
                        'severity': r.get('severity_score') or 0,
                        'alert': r.get('alert_level')})
        if (r.get('severity_score') or 0) > sev:
            initial = r
            sev = r.get('severity_score') or 0

    if sev > 65:
        result = dict(initial)
        if amp_shift:
            result['amplitude_shift'] = amp_shift
        return {'winning_result': result, 'method_used': 'auto_retry',
                'cascade': cascade, 'quota_used': quota}

    # Stage 2.5: fingerprint inspection (specific dim dropped?)
    fp = inspect_fingerprint(client, signal, baseline,
                             sampling_rate=sampling_rate, domain=domain)
    quota += 1
    if fp:
        cascade.append({
            'method': 'fingerprint_inspect',
            'config': f"worst_dim={fp['worst_dim']}@{fp['worst_value']:.2f}",
            'severity': fp['derived_severity'],
        })
        if fp['derived_severity'] > sev:
            synth = {
                'score': fp['scalar_score'],
                'confidence_band': 'transition',
                'alert_level': 'critical' if fp['derived_severity'] > 80 else 'alert',
                'severity_score': fp['derived_severity'],
                'summary': (f"Specific dim dropped: {fp['worst_dim']}="
                            f"{fp['worst_value']:.2f}. {fp['failure_type']}."),
                'fingerprint': fp['fingerprint'],
                'method': 'fingerprint_dim',
            }
            if amp_shift:
                synth['amplitude_shift'] = amp_shift
            if fp['derived_severity'] > 65:
                return {'winning_result': synth, 'method_used': 'fingerprint_inspect',
                        'cascade': cascade, 'quota_used': quota}
            initial = synth
            sev = fp['derived_severity']

    # Stage 3: monitor escalation
    sig = list(signal)
    base = list(baseline)
    N = len(sig)
    if N < 60:
        result = dict(initial)
        if amp_shift:
            result['amplitude_shift'] = amp_shift
        return {'winning_result': result, 'method_used': 'auto_retry',
                'cascade': cascade, 'quota_used': quota,
                'note': 'Signal too short to escalate.'}

    win_size = max(30, N // 8)
    step = max(10, win_size // 2)
    max_w = {'free': 6, 'starter': 30, 'growth': 100,
             'professional': 200, 'enterprise': 500}.get(plan['slug'], 20)
    expected = max(1, (N - win_size) // step + 1)
    if expected > max_w:
        step = max(step, (N - win_size) // max_w)
        expected = max_w

    try:
        result = client.analyze_windowed(signal=sig, window_size=win_size,
                                          step=step, sampling_rate=sampling_rate,
                                          domain=domain, baseline=base)
        quota += expected
        windows = result.get('windows', [])
        worst = result.get('worst_window')
        if isinstance(worst, tuple) and len(worst) >= 3:
            worst_score = worst[2]
            worst_loc = (worst[0], worst[1])
        else:
            worst_score = 0.5; worst_loc = None
        worst_sev = max(0, min(100, (1.0 - worst_score) * 100))
        cascade.append({
            'method': 'monitor_escalation',
            'config': f"window={win_size} step={step}",
            'severity': worst_sev,
            'worst_window': worst_loc,
        })
        if worst_sev > sev:
            alerts_count = sum(1 for w in windows
                               if isinstance(w, tuple) and len(w) >= 3 and w[2] < 0.5)
            out = {
                'score': worst_score,
                'confidence_band': 'unstable' if worst_score < 0.35 else 'transition',
                'alert_level': 'critical' if worst_sev > 80 else 'alert',
                'severity_score': worst_sev,
                'summary': (f"Difference detected via sliding window. Worst window "
                            f"at {worst_loc[0]}-{worst_loc[1]} (score {worst_score:.2f}). "
                            f"{alerts_count}/{len(windows)} windows below 0.5."),
                'worst_window': worst_loc,
                'method': 'sliding_window',
            }
            if amp_shift:
                out['amplitude_shift'] = amp_shift
            return {'winning_result': out, 'method_used': 'monitor_escalation',
                    'cascade': cascade, 'quota_used': quota}
    except Exception as e:
        cascade.append({'method': 'monitor_escalation_failed', 'error': str(e)[:100]})

    result = dict(initial)
    if amp_shift:
        result['amplitude_shift'] = amp_shift
    return {'winning_result': result, 'method_used': 'auto_retry',
            'cascade': cascade, 'quota_used': quota}


def smart_anomaly(client: AlphaInfo,
                  signal: Sequence[float],
                  plan: dict[str, Any],
                  sampling_rate: float = 10.0,
                  domain: str = 'generic',
                  baseline: Sequence[float] | None = None) -> dict[str, Any]:
    """The skill's self-correcting anomaly detection.

    4-stage cascade (only pays for what's needed):
      1. quick_anomaly with user's domain (1 quota)
      2. If borderline (sev 30-65), try 2-3 alternative domains (3 quota)
      3. If still borderline AND baseline available, inspect 5-D fingerprint
         (1 quota) — finds specific dim that dropped (e.g., sim_spectral for
         added harmonics) that scalar score averaged out.
      4. If still borderline, ESCALATE to monitor() sliding window (5-10 quota)
         — catches localized regime changes the global view misses.
      Returns the MOST CONFIDENT result (highest severity).

    This solves the case where a regime change exists but the global signal
    looks similar to its baseline — sliding window finds the bad WINDOW.

    Returns dict with:
        winning_result: the dict from the most decisive call
        method_used: 'quick_anomaly' | 'auto_retry' | 'monitor_escalation'
        cascade: list of attempts with severity
        quota_used: total quota burned
    """
    cascade = []
    quota = 0

    # ── Stage 1: quick anomaly with user's preferred domain ──────────
    r = auto_retry(client, signal, plan, sampling_rate=sampling_rate,
                   baseline=baseline,
                   op='quick_anomaly', initial_domain=domain,
                   borderline_range=(30, 65),
                   max_retries=0)  # only initial call here
    quota += 1
    initial = r['winning_result']
    cascade.append({
        'method': 'quick_anomaly',
        'config': f"domain={domain}",
        'severity': initial.get('severity_score') if initial else 0,
        'alert': initial.get('alert_level') if initial else None,
    })

    if not initial:
        return {'winning_result': None, 'method_used': 'failed',
                'cascade': cascade, 'quota_used': quota}

    sev = initial.get('severity_score') or 0
    if sev > 65:
        return {'winning_result': initial, 'method_used': 'quick_anomaly',
                'cascade': cascade, 'quota_used': quota}

    # ── Stage 2: alternative configs ────────────────────────────────
    r2 = auto_retry(client, signal, plan, sampling_rate=sampling_rate,
                    baseline=baseline,
                    op='quick_anomaly', initial_domain=domain,
                    borderline_range=(30, 65),
                    max_retries=3)
    quota += r2['n_retries']
    if r2['retry_used']:
        wc = r2.get('winning_config', {})
        cascade.append({
            'method': 'auto_retry',
            'config': f"domain={wc.get('domain')} intent={wc.get('intent')}",
            'severity': r2['winning_result'].get('severity_score'),
            'alert': r2['winning_result'].get('alert_level'),
        })

    best = r2['winning_result']
    best_sev = best.get('severity_score') or 0

    if best_sev > 65:
        return {'winning_result': best, 'method_used': 'auto_retry',
                'cascade': cascade, 'quota_used': quota}

    # ── Stage 2.5: FINGERPRINT INSPECTION ────────────────────────────
    # Sometimes the scalar score is borderline because changes are concentrated
    # in ONE dim (e.g., sim_spectral for added harmonics). Look at the
    # fingerprint to find the specific dim that dropped.
    if baseline is not None:  # need a baseline to inspect fingerprint
        fp = inspect_fingerprint(client, signal, baseline,
                                 sampling_rate=sampling_rate, domain=domain)
        quota += 1
        if fp:
            cascade.append({
                'method': 'fingerprint_inspect',
                'config': f"worst_dim={fp['worst_dim']}@{fp['worst_value']:.2f}",
                'severity': fp['derived_severity'],
                'failure_type': fp['failure_type'],
            })
            if fp['derived_severity'] > best_sev:
                # Synthesize a result with the dim-specific finding
                synthesized = {
                    'score': fp['scalar_score'],
                    'confidence_band': 'transition',
                    'alert_level': 'critical' if fp['derived_severity'] > 80 else 'alert',
                    'severity_score': fp['derived_severity'],
                    'summary': (f"Specific structural dim dropped: "
                                f"{fp['worst_dim']}={fp['worst_value']:.2f}. "
                                f"Failure type: {fp['failure_type']}."),
                    'fingerprint': fp['fingerprint'],
                    'method': 'fingerprint_dim',
                }
                if fp['derived_severity'] > 65:
                    return {'winning_result': synthesized,
                            'method_used': 'fingerprint_inspect',
                            'cascade': cascade, 'quota_used': quota}
                # else continue to monitor escalation
                best = synthesized
                best_sev = fp['derived_severity']

    # ── Stage 3: ESCALATE to sliding window ──────────────────────────
    # Pick window/step adaptively
    sig = list(signal)
    N = len(sig)
    if N < 60:
        return {'winning_result': best, 'method_used': 'auto_retry',
                'cascade': cascade, 'quota_used': quota,
                'note': 'Signal too short to escalate to sliding window.'}

    # Use first N//4 as baseline if not provided
    base = list(baseline) if baseline else sig[:N//4]
    # Window: 10-20% of signal length, step: 50% of window
    win_size = max(30, N // 8)
    step = max(10, win_size // 2)

    # Plan-aware budget
    max_windows = {'free': 6, 'starter': 30, 'growth': 100,
                   'professional': 200, 'enterprise': 500}.get(plan['slug'], 20)
    expected_windows = max(1, (N - win_size) // step + 1)
    if expected_windows > max_windows:
        step = max(step, (N - win_size) // max_windows)
        expected_windows = max_windows

    try:
        result = client.analyze_windowed(
            signal=sig, window_size=win_size, step=step,
            sampling_rate=sampling_rate, domain=domain,
            baseline=base,
        )
        quota += expected_windows
        windows = result.get('windows', [])
        worst = result.get('worst_window')

        # Convert worst-window score to severity-equivalent
        if isinstance(worst, tuple) and len(worst) >= 3:
            worst_score = worst[2]
            worst_loc = (worst[0], worst[1])
        elif isinstance(worst, dict):
            worst_score = worst.get('structural_score') or worst.get('score')
            worst_loc = (worst.get('start'), worst.get('end'))
        else:
            worst_score = 0.5
            worst_loc = None

        # Severity heuristic: low score = high severity
        # 0.0 → sev 100, 0.5 → sev 50, 1.0 → sev 0
        worst_sev = max(0, min(100, (1.0 - worst_score) * 100))

        cascade.append({
            'method': 'monitor_escalation',
            'config': f"window={win_size} step={step} baseline=first_quarter",
            'severity': worst_sev,
            'worst_window': worst_loc,
            'worst_score': worst_score,
            'n_windows': len(windows),
        })

        if worst_sev > best_sev:
            # Synthesize a result dict
            alerts_count = sum(1 for w in windows
                               if (isinstance(w, tuple) and len(w) >= 3 and w[2] < 0.5)
                               or (isinstance(w, dict) and (w.get('structural_score') or 1) < 0.5))
            return {
                'winning_result': {
                    'score': worst_score,
                    'confidence_band': 'unstable' if worst_score < 0.35 else 'transition',
                    'alert_level': 'critical' if worst_sev > 80 else 'alert',
                    'severity_score': worst_sev,
                    'summary': (f"Regime detected via sliding window. Worst window "
                                f"at index {worst_loc[0]}-{worst_loc[1]} "
                                f"(score {worst_score:.2f}). {alerts_count} of "
                                f"{len(windows)} windows below 0.5 threshold."),
                    'worst_window': worst_loc,
                    'n_alerts': alerts_count,
                    'method': 'sliding_window',
                },
                'method_used': 'monitor_escalation',
                'cascade': cascade, 'quota_used': quota,
            }
    except Exception as e:
        cascade.append({'method': 'monitor_escalation_failed', 'error': str(e)[:100]})

    return {'winning_result': best, 'method_used': 'auto_retry',
            'cascade': cascade, 'quota_used': quota}


def auto_retry(client: AlphaInfo,
               signal: Sequence[float],
               plan: dict[str, Any],
               sampling_rate: float = 10.0,
               baseline: Sequence[float] | None = None,
               op: str = 'quick_anomaly',
               initial_domain: str = 'generic',
               borderline_range: tuple[float, float] = (35, 65),
               max_retries: int | None = None) -> dict[str, Any]:
    """Run an op, and if result is BORDERLINE, auto-retry with alternate configs.

    Goal: skill self-corrects instead of returning a "meh" answer that the
    user/Claude has to interpret as either failure or success.

    A result is "borderline" if severity_score is in [borderline_range].
    On borderline, the skill probes:
      1. domain='auto' (let API infer)
      2. Different intent (local_anomaly ↔ regime_change for quick_anomaly)
      3. 1-2 sensible alternative domains for the apparent data shape

    Picks the result with HIGHEST severity_score (most decisive).

    Args:
        op: 'quick_anomaly' (no baseline needed) or 'compare' (needs baseline)
        max_retries: hard cap on retry calls. Plan-aware default.

    Returns dict with:
        winning_result: the dict from the best call
        configs_tried: list of (config, severity) tuples
        n_retries: how many extra calls were made
        retry_used: bool — True if skill ended up using a non-default config
    """
    if max_retries is None:
        max_retries = {'free': 3, 'starter': 6, 'growth': 10,
                       'professional': 15, 'enterprise': 20}.get(plan['slug'], 5)

    sig = list(signal)
    base = list(baseline) if baseline is not None else None

    def _do_call(domain: str, intent: str = 'local_anomaly') -> dict | None:
        try:
            if op == 'quick_anomaly':
                r = client.detect_internal_change(
                    signal=sig, sampling_rate=sampling_rate,
                    domain=domain, intent=intent, include_semantic=True,
                )
            elif op == 'compare' and base is not None:
                if domain == 'auto':
                    r = client.analyze_auto(signal=sig, baseline=base,
                                             sampling_rate=sampling_rate,
                                             include_semantic=True)
                else:
                    r = client.compare(signal=sig, baseline=base,
                                       sampling_rate=sampling_rate,
                                       domain=domain, include_semantic=True)
            else:
                return None
            return {
                'score': r.structural_score,
                'confidence_band': r.confidence_band,
                'alert_level': r.semantic.alert_level if r.semantic else None,
                'severity_score': r.semantic.severity_score if r.semantic else None,
                'summary': r.semantic.summary if r.semantic else None,
                'analysis_id': r.analysis_id,
                'domain_inference': getattr(r, 'domain_inference', None),
            }
        except Exception:
            return None

    configs_tried = []

    # First call: user's preferred config
    initial_intent = 'local_anomaly'
    first = _do_call(initial_domain, initial_intent)
    if first is None:
        return {'winning_result': None, 'configs_tried': [],
                'n_retries': 0, 'retry_used': False}
    configs_tried.append({'domain': initial_domain, 'intent': initial_intent,
                          'severity': first['severity_score'] or 0,
                          'alert': first['alert_level']})

    sev = first.get('severity_score') or 0
    in_border = borderline_range[0] <= sev <= borderline_range[1]

    if not in_border or max_retries == 0:
        return {'winning_result': first, 'configs_tried': configs_tried,
                'n_retries': 0, 'retry_used': False}

    # Borderline — try alternate configs
    retry_configs = []
    # 1. domain='auto'
    if initial_domain != 'auto':
        retry_configs.append(('auto', initial_intent))
    # 2. Flip intent
    if op == 'quick_anomaly':
        flipped = 'regime_change' if initial_intent == 'local_anomaly' else 'local_anomaly'
        retry_configs.append((initial_domain, flipped))
    # 3. Sensible alternative domains based on data shape
    #    (skill can't know the user's domain, so try a few wide candidates)
    alt_domains = []
    for d in ['security', 'sensors', 'finance', 'biomedical']:
        if d != initial_domain and len(retry_configs) + len(alt_domains) < max_retries:
            alt_domains.append(d)
    for d in alt_domains[:max(0, max_retries - len(retry_configs))]:
        retry_configs.append((d, initial_intent))

    retry_configs = retry_configs[:max_retries]

    best = first
    best_sev = sev
    best_config_idx = 0  # 0 = initial

    for i, (dom, intent) in enumerate(retry_configs, start=1):
        r = _do_call(dom, intent)
        if r is None:
            continue
        s = r.get('severity_score') or 0
        configs_tried.append({'domain': dom, 'intent': intent,
                              'severity': s, 'alert': r.get('alert_level')})
        if s > best_sev:
            best = r
            best_sev = s
            best_config_idx = i

    return {
        'winning_result': best,
        'configs_tried': configs_tried,
        'n_retries': len(retry_configs),
        'retry_used': best_config_idx > 0,
        'winning_config': configs_tried[best_config_idx],
    }


def autotune_domain(client: AlphaInfo,
                    signal: Sequence[float],
                    baseline: Sequence[float],
                    plan: dict[str, Any],
                    sampling_rate: float = 10.0,
                    candidate_domains: list[str] | None = None,
                    budget: int | None = None) -> dict[str, Any]:
    """Try a few domains. Pick the one giving most informative result.

    Informative = farthest from 0.5 (which is the noise/uncertainty zone).
    """
    if budget is None:
        budget = {'free': 3, 'starter': 5, 'growth': 8,
                  'professional': 10, 'enterprise': 10}.get(plan['slug'], 5)

    if candidate_domains is None:
        # Sensible default: auto + 2 most relevant
        candidate_domains = ['auto', 'generic']

    candidate_domains = candidate_domains[:budget]

    results = []
    quota_used = 0
    for dom in candidate_domains:
        try:
            if dom == 'auto':
                r = client.analyze_auto(signal=list(signal), baseline=list(baseline),
                                         sampling_rate=sampling_rate,
                                         include_semantic=True)
                di = getattr(r, 'domain_inference', None) or {}
                inferred = di.get('inferred') if isinstance(di, dict) else None
                results.append({
                    'requested_domain': 'auto',
                    'inferred_domain': inferred,
                    'score': r.structural_score,
                    'band': r.confidence_band,
                    'distance_from_noise': abs(r.structural_score - 0.5),
                })
            else:
                r = client.analyze(signal=list(signal), baseline=list(baseline),
                                   sampling_rate=sampling_rate, domain=dom,
                                   include_semantic=True)
                results.append({
                    'requested_domain': dom,
                    'inferred_domain': dom,
                    'score': r.structural_score,
                    'band': r.confidence_band,
                    'distance_from_noise': abs(r.structural_score - 0.5),
                })
            quota_used += 1
        except Exception:
            continue

    if not results:
        return {'best_domain': 'generic', 'all_domains': [], 'quota_used': 0}

    # Best = farthest from 0.5 = most informative
    results.sort(key=lambda r: r['distance_from_noise'], reverse=True)
    best = results[0]
    return {
        'best_domain': best['inferred_domain'] or best['requested_domain'],
        'best_score': best['score'],
        'all_domains': results,
        'quota_used': quota_used,
    }
