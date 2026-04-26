# Task: Monitor Long Stream — WHERE Did It Change

**When:** user has a long signal (hours of metrics, days of returns, multi-minute ECG) and asks "when did things change?", "where's the anomaly?", "show me the bad windows".

Native via `analyze_windowed()` — replaces ~50 lines of manual loop.

## One-liner

```python
from lib.helpers import monitor

r = monitor(client, signal=long_stream, plan=plan,
            window_size=200, step=50, sampling_rate=10.0,
            baseline=known_stable_period)   # optional

print(f"{r['n_windows']} windows analyzed, {r['n_alerts']} alerts")
worst = r['worst_window']
print(f"Most anomalous: starts at {worst['start']}, score={worst['score']:.2f}")
```

## Window sizing rules of thumb

- `window_size`: at least 50 samples (200-500 optimal for fingerprint)
- `step`: 25-50% of window size for good resolution; larger if quota constrained
- Longer windows = more stable but coarser localization
- Shorter windows = more reactive but noisier

## With or without baseline

- **With baseline**: each window compared to `baseline` (known-stable). Best for "is current state OK?"
- **Without baseline**: each window compared to the previous window. Best for "what's changing?"

## Cost

N analyses (one per window). For 1000-sample signal, window=200, step=50 → 17 analyses.

The helper is plan-aware: if the requested window count exceeds the plan's recommendation, it INCREASES the step automatically and warns.

## Localizing further

If you find a bad window, you can recurse: zoom into that window with smaller `window_size` and finer `step` for finer localization. The fingerprint (5-D) inside the worst window also tells you WHAT KIND of change (see `reference/interpretation.md`).

## Alert filtering

The helper returns `alerts` (windows below `score_threshold`, default 0.5). Tighten to 0.35 for stricter (only `unstable`/`diverging` zones).

## Verified live behavior

Tested with synthetic CPU stream (600 samples, spike 300-360):
- Window=120, step=60 → 9 windows
- Worst window correctly localized near the spike (samples 240-360)
- 2 windows flagged as alerts at score < 0.5
