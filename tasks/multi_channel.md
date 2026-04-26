# Task: Multi-Channel — Which Sensor Is Failing? (Canal Delator)

**When:** user has multiple sensors / channels and one might be anomalous. They want to know **which** without checking each by hand.

Native via `analyze_vector()` — **1 quota for all channels**, plus per-channel scores reveal the failing one (the "canal delator").

## One-liner

```python
from lib.helpers import multi_channel

r = multi_channel(client, channels=current, baselines=normal,
                  plan=plan, sampling_rate=10.0, domain='sensors')

print(f"Delator: {r['delator_channel']} (score {r['delator_score']:.3f})")
print(f"Alert: {r['alert_level']}, severity {r['severity_score']:.0f}/100")
print(f"Per-channel: {r['per_channel_scores']}")
```

`current` and `normal` are dicts mapping channel name → signal list. Both must have the same keys.

## Why this is a killer feature

Compared to calling `analyze()` per channel separately:

- **Cost**: 1 quota vs N quota
- **Aggregation**: aggregated `severity_score` and `recommended_action` for free
- **Less code**: 1 line vs loop + min()

## Plan caps for vector channels

| Plan | Max channels |
|---|---|
| Free | 3 |
| Starter ($49) | 8 |
| Growth ($199) | 16 |
| Professional ($499) | 32 |
| Enterprise | 64 |

The helper auto-caps to plan limit and surfaces upgrade hint when truncated. **For Free users with >3 sensors, the helper drops the rest** — you should pre-select the most diagnostic channels (highest variance, most sensitive) before passing them in.

## Best practices

1. **Baselines per-channel** — don't use the same baseline for different sensor types
2. **Channels of DIFFERENT nature** — vector exploits per-channel structure; duplicating the same signal wastes channels
3. **Baseline from known-stable period** — not zeros, not the signal itself
4. **Right `domain`** — `sensors` for industrial, `biomedical` for vitals, `power_grid` for grid, etc.
5. **N >= 50 per channel** — below that, results default to 0.5 with warning

## Cascade detection

When aggregated score is LOW and MULTIPLE channels score < 0.7:
- Not single-point fault
- Likely cascading failure across subsystems
- Check temporal order (which channel degraded first) by sliding-window per-channel

## Verified live behavior

HVAC fault test (4 channels: temp, pressure, airflow, vibration; airflow dropped 50%):

- Skill (1 call): `delator='airflow'`, alert=`critical`, severity=76
- Per-channel: temp=1.000, pressure=1.000, airflow=0.238, vibration=1.000
- Naive (4 separate calls): same answer but 4 quota + manual aggregation
