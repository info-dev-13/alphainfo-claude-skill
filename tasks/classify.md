# Task: Classify Signals (Zero-Shot via Fingerprint)

**When:** user wants to categorize signals into known classes (normal/arrhythmia, healthy/faulty, AI/human, etc.) **without training a model**.

The 5-D fingerprint produced by AlphaInfo's `multiscale=True` is competitive with purpose-trained classifiers for zero-shot use.

**Always use fingerprint for classification, not the scalar score.**

## Preferred path: `autotune_classifier()` — let the skill find the right config

Different reference signals + classifier combos give wildly different accuracy
on the same data. Manual choice is unreliable. Use `autotune_classifier`:

```python
from lib.autotune import autotune_classifier

# At least 4 labeled samples per class
labeled = [('normal', sig1), ('normal', sig2), ('arr', sig3), ...]

res = autotune_classifier(client, labeled, plan,
                           sampling_rate=250.0, domain='biomedical')

print(f"Best config: {res['best_config']}")  # {'reference_strategy': ..., 'classifier': ...}
print(f"CV accuracy: {res['cv_accuracy']:.0%}")

# Use the returned closure to classify new signals (1 quota each)
prediction = res['predict'](new_signal)
```

The function:
1. Builds 2-3 candidate references (mean of class 0, median of class 0, sine for Starter+)
2. Tries 4 classifiers (centroid raw, centroid normalized, k-NN, LDA)
3. Cross-validates each combo via leave-one-out on training set
4. Returns the winning combo + a `predict` callable ready to use

**Quota cost (plan-aware):**
- Free: 24 quota target (12 fingerprints × 2 refs)
- Starter: 50 quota
- Growth+: 80+ quota

**Validated on real PhysioNet ECG (record 208, N vs PVC):**
- Manual sine + raw centroid: 50% accuracy
- Manual mean + standardized + LDA: 95% accuracy
- **`autotune_classifier`**: **100% CV / 80% held-out, 24 quota, zero manual config**

The autotune approach removes the methodology trap.

## Manual recipe (if you have specific reference / classifier preference)

## Recipe

```python
import numpy as np
from alphainfo import AlphaInfo

# 1. Collect labeled training signals (~10 per class is enough)
training = [
    ('normal', sig_normal_1), ('normal', sig_normal_2), ...
    ('arrhythmia', sig_arr_1), ('arrhythmia', sig_arr_2), ...
]

# 2. Pick a neutral reference (a clean sine, or a known-healthy template)
import math
ref = [math.sin(2*math.pi*i/30) for i in range(200)]

# 3. Get fingerprint per training signal (1 API call each)
DIMS = ['sim_local', 'sim_fractal', 'sim_spectral', 'sim_transition', 'sim_trend']
fps = {}
for label, sig in training:
    r = client.analyze(signal=sig, baseline=ref, sampling_rate=250.0,
                       domain='biomedical')
    fp = np.array([r.metrics[d] for d in DIMS])
    fps.setdefault(label, []).append(fp)

# 4. Compute centroid per class
centroids = {label: np.mean(arr, axis=0) for label, arr in fps.items()}

# 5. Classify a new signal: nearest centroid
def classify(sig):
    r = client.analyze(signal=sig, baseline=ref, sampling_rate=250.0, domain='biomedical')
    fp = np.array([r.metrics[d] for d in DIMS])
    return min(centroids, key=lambda c: np.linalg.norm(fp - centroids[c]))
```

## Class separation diagnostic

After training, check inter-centroid distances:

```python
from itertools import combinations
for a, b in combinations(centroids, 2):
    d = np.linalg.norm(centroids[a] - centroids[b])
    print(f'{a} vs {b}: {d:.3f}')
```

If centroids are too close (< 0.3), classes aren't separable with this reference — try:
- A different reference signal
- k-NN instead of centroid (when classes are multi-modal)
- LDA for linear separation (binary classification)

## Cost

- Training: N API calls (one per labeled sample) — use `analyze_batch` for cheap bulk
- Prediction: 1 call per query signal
- Total: O(training + queries)

## Plan caps

- Free: train with ≤ 10 samples per class total (50 quota cap)
- Starter+: train with hundreds, classify thousands

## When NOT to use API for classification

- > 1000 training samples and need maximum accuracy → train a dedicated model
- Inference < 100ms required → API has ~250-500ms floor
- Class differences are time-lagged in a specific way the API doesn't perceive
