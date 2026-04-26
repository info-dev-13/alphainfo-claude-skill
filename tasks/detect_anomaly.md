# Task: Detect Anomaly Without a Baseline

**When:** user uploads a CSV column or paste of numbers and asks "is this weird?", "anomaly?", "anything wrong with this?" — with **no reference signal**.

This was previously hard (skill required synthetic baselines). The API now solves it natively via `detect_internal_change()`.

## One-liner

```python
from lib.helpers import quick_anomaly
r = quick_anomaly(client, signal=stream, plan=plan, sampling_rate=10.0)
print(r['alert_level'], r['severity_score'], r['summary'])
```

The API internally compares fingerprints of the signal's own segments. Returns:

- `score > 0.70` → internally consistent (no anomaly)
- `score < 0.35` → contains a structural change (anomaly somewhere inside)
- `0.35-0.70` → suspicious

`alert_level` ∈ `normal | attention | alert | critical`.

## Two intents

```python
# DEFAULT: 'local_anomaly' — looks for spike-like events
r = quick_anomaly(client, signal, plan, intent='local_anomaly')

# 'regime_change' — looks for sustained shifts mid-signal
r = quick_anomaly(client, signal, plan, intent='regime_change')
```

For periodic data (sine-like, ECG-rhythmic) prefer `regime_change` — the half-vs-half default may pick up phase differences.

## Don't tell user WHERE — just YES/NO

This endpoint answers "is there an anomaly?" not "where". For localization, follow up with `monitor()` (see `tasks/monitor.md`).

Pattern:
1. `quick_anomaly()` to get yes/no fast (1 quota)
2. If `alert_level >= alert`, run `monitor()` to localize (N quota)

## Plan caps

1 quota per call. Free signal length cap = 10K samples. Helper truncates automatically and warns.

## Verified live behavior

Tested with synthetic spike inside 500-sample stream:
- Clean signal: `score ≈ 0.6-0.8`, `alert_level=normal`
- Spike of 50 samples at 5σ: `score ≈ 0.11`, `alert_level=critical`, `severity ≈ 88`

For PhysioNet ECG (real data, see `examples/ecg_anomaly.py`), this endpoint reliably catches arrhythmic beats vs sinus rhythm.
