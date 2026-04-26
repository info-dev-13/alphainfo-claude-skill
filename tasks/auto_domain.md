# Task: Auto-Infer Domain

**When:** user hands you a signal of unknown type, or you don't know which of the 10 domain calibrations to pick.

## One-liner

```python
from lib.helpers import auto_compare

r = auto_compare(client, signal=mystery, baseline=ref, plan=plan, sampling_rate=10.0)
print(f"Inferred: {r['inferred_domain']} (confidence {r['domain_confidence']})")
print(f"Reasoning: {r['domain_reasoning']}")
print(f"Score: {r['score']}, alert: {r['alert_level']}")
```

The API inspects signal statistics (length, sampling rate, value range, distribution shape) and dispatches to the most appropriate calibration.

## Always show `reasoning` to the user

It's plain English explaining the choice. Surfaces educational value:

> *"low_sampling_rate_heavy_tailed_sparse_peaks → seismic"*

Helps the user learn what domain their data fits — and sometimes surfaces a better domain than they expected.

## When to USE auto

- Mystery data (CSV column with no context)
- Mixed pipelines processing many sources
- Onboarding a new user
- Sanity check on a domain you THINK you know

## When to SKIP auto

- You already know the domain — pass it explicitly. Saves the inference and avoids any wrong-domain risk.
- Production pipelines where reproducibility of scores matters across API updates

## Cost

1 quota — same as `analyze()`. Inference is essentially free overhead.

## When `fallback_used=True`

The API wasn't confident in its choice and substituted a default. Treat the chosen domain with skepticism, or re-call with `domain='generic'` instead.

## Verified live behavior

Tested with heavy-tailed log-returns (Student-t, df=3) vs gaussian:
- Inferred: `seismic` (NOT `finance`!)
- Confidence: 0.95
- Reasoning: `low_sampling_rate_heavy_tailed_sparse_peaks`

This is a real example of `auto` surfacing a domain choice the dev wouldn't pick alone — both finance and seismic have heavy tails, and the API correctly identified the structural similarity.

ECG data (250 Hz sampling, periodic pattern) → correctly inferred `biomedical` with confidence > 0.9.
