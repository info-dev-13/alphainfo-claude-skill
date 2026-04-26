# Common Pitfalls

Hard-won lessons. Each entry is a real mistake catalogued.

## Encoding

### "Score came back 1.0, API is broken"
NO. You set `baseline = signal` (identity) or `baseline = self`. Choose a DIFFERENT baseline that represents "normal/expected".

### "Score is 0.05, signal must be totally different"
Check if baseline is all zeros or near-zero. That produces low scores on ANY signal regardless of structure.

### "Single spike at position 100 not detected"
If baseline is all zeros, single spike returns 1.000 (trivially "similar"). Use a non-zero baseline. With a real baseline, 1-sample outlier DOES drop score.

### "Amplitudes are huge (1e8) and API crashes"
HTTP 422 above dynamic range ~1e5. The error tells you to normalize. Use z-score or log returns first.

### "Classification gave 60%, much worse than classical"
You used scalar `structural_score`. **Use the 5-D fingerprint.** Per-class centroid in fingerprint space → 90%+ accuracy.

## Endpoint

### "I'm calling analyze() 1000 times in a loop"
Use `analyze_batch` (up to 100 at once) or `analyze_vector` (up to 64 channels, 1 quota total).

### "Matrix doesn't show asymmetry I expected"
`analyze_matrix` SYMMETRIZES. For asymmetric analysis, call `analyze()` both directions explicitly.

### "Multi-channel aggregated score doesn't match any channel"
Aggregated is **worst-case across channels** (biased toward detection). Per-channel via `result.channels[name]`.

### "Vector endpoint rejected 200 channels"
Max 64 (was 60 in older API). For more, batch across multiple vector calls.

### "I'm hand-rolling sliding window when `analyze_windowed()` exists"
Native sliding window returns `windows`, `worst_window`, `best_window` in one call. Use it.

### "I'm picking a domain when `analyze_auto` would tell me"
For unknown signals, `analyze_auto` returns `domain_inference.{inferred, confidence, reasoning}`.

### "I'm encoding fintech anomalies from scratch instead of using probes_finance"
`/v1/recipes` exposes 8 domain probe libraries. Always check before hand-encoding.

## Interpretation

### "Score = 0.6, user says OK or not?"
Refer to thresholds: > 0.70 stable / 0.35-0.70 monitor / < 0.35 different.
Also check `confidence_band` — domain-calibrated.

### "sim_fractal = 0.80, is that normal?"
YES. **sim_fractal ~0.80 is THE anchor value** for stable signals. Below 0.70 = fundamental change.

### "Trend says 'diverging', is it getting worse?"
NOT necessarily. "Diverging" = CHANGED. Could be improvement, degradation, or neutral. Provide context.

## SDK / API UX

### "Key validates against /health but fails on /analyze with AuthError"
**MISLEADING SDK message** — fires on quota-exhausted accounts too.

How to disambiguate:
1. `client.health().status == "healthy"` → key reaches the server
2. `client.plans()` returns list → key authenticates
3. `client.analyze(...)` → AuthError → almost certainly **free tier exhausted**

`lib/setup.py` has `setup(check_analyze=True)` to probe this.

### "I called analyze() and got 'sampling_rate is required'"
`sampling_rate` is the **2nd positional argument**. Pass it always:
- 1.0 for daily/hourly metrics
- 250 for clinical ECG, 100-500 for EEG
- 10 for typical IoT
- Don't guess — affects the spectral channel

### "analyze_windowed returned tuples, not dicts"
Yes — windows are `(start, end, score)` tuples (not objects with attributes). The helper `monitor()` in `lib/helpers.py` normalizes this.

## Plan-aware

### "Vector with 50 channels failed on Free"
Free is capped at 3 channels. The skill helper auto-truncates with a hint, but if you call `client.analyze_vector` directly with > cap channels, you get HTTP 403. Use `lib.helpers.multi_channel` instead.

### "200K-sample analysis failed on Free"
Free max signal length is 10K. Helpers auto-truncate. Surface to user that data was capped + suggest upgrade.

## Meta

### "I tried one method, didn't work, so the API can't do X"
Historical accuracy of this reasoning: near zero. Almost always wrong encoding, wrong endpoint, or missing feature. Try at least 3 approaches before asserting a limit.

### "The documentation doesn't mention this use case"
Check `/v1/guide` AND `/v1/recipes` ITSELF, not just memory. Recipes layer alone has 21 entries you might be reinventing.
