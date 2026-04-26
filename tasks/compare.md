# Task: Compare Two Signals

**When:** "Are these two signals similar?" "Did B change vs A?" "Is the new version structurally equivalent to the old?"

## One-liner (preferred)

```python
from lib.helpers import compare
r = compare(client, signal=A, baseline=B, plan=plan, sampling_rate=10.0)
print(r['score'], r['confidence_band'], r['summary'])
```

`compare()` defaults to `include_semantic=True` — you get human-readable interpretation for free.

## When to use which encoding

| Have | Encoding |
|---|---|
| Two same-type signals (two ECGs, two prices) | Profile (raw, just pass them) |
| Ideal vs measured (efficiency / quality) | Ratio: `[m/r for m,r in zip(meas, ref)]` baseline `[1.0]*N` |
| Model prediction vs actual | Residual: `actual - predicted` |
| Before vs after intervention | Profile, then read `trend` |
| Composite system | `multi_channel` (vector) |

## Reading the result

- `score > 0.70` → similar (stable)
- `score < 0.35` → different (diverging)
- `0.35-0.70` → transition zone, monitor

For per-version rollouts:

```python
r = compare(client, signal=v2_metric, baseline=v1_metric, plan=plan, sampling_rate=1.0)
if r['score'] > 0.9:
    print("v2 ≈ v1 — no functional regression")
elif r['score'] < 0.5:
    print(f"v2 diverged: {r['summary']}")
```

## Asymmetry — does direction matter?

`score(A, B) ≠ score(B, A)` in general. The asymmetry reveals **structural containment**:

- `s(A,B) >> s(B,A)` → A is more complex, contains B
- Symmetric → both have similar complexity

Run both directions if you need to know which is "more general".

## Plan caps

`compare()` is the cheapest endpoint (1 quota). Free tier signal length cap = 10K samples.
For longer signals (e.g., week of minute-resolution metrics = 10K), the helper auto-truncates and surfaces an upgrade hint.
