# AlphaInfo API Guide (snapshot 2026-04-26)

This mirrors `/v1/guide`. Always fetch fresh if you suspect the API changed:

```python
g = client.guide()  # native helper
```

API version: **1.1**. SDK reference: `1.4+` (HTTP/2), `1.5.27+` (custom encoders).

## Principle

> The API measures structural similarity between two numeric signals. It does NOT understand your domain — it perceives structure. Your job: encode your problem as a signal where structure = what matters to you.

## Three questions the API answers

1. **Did it change?** → `structural_score`, `confidence_band`, `trend`
2. **How much?** → `severity_score` (0-100), `change_score`
3. **What KIND?** → 5-D fingerprint (sim_local, sim_fractal, sim_spectral, sim_transition, sim_trend) + `multiscale.scale_profile.structural_slope`

## Endpoints

| HTTP | SDK helper | Cost | Purpose |
|---|---|---|---|
| POST `/v1/analyze/stream` | `analyze()`, `compare()`, `detect_internal_change()`, `analyze_auto()` | 1 | Single signal full analysis |
| POST `/v1/analyze/batch` | `analyze_batch()` | N | N independent signals (max 100) |
| POST `/v1/analyze/matrix` | `analyze_matrix()` | N·(N-1)/2 | Pairwise (max 50, SYMMETRIC) |
| POST `/v1/analyze/vector` | `analyze_vector()` | **1** | Multi-channel system (max 64) |
| (composite) | `analyze_windowed()` | per-window | Sliding window |
| (composite) | `fingerprint()` | 1 | Direct 5-D vector |
| (composite) | `fit_parameter_grid()` | per-candidate | Parameter search |

## Discovery (no auth, no quota)

| HTTP | SDK helper |
|---|---|
| GET `/health` | `health()` |
| GET `/v1/version` | `version()` |
| GET `/v1/guide` | `guide()` |
| GET `/v1/recipes` | `httpx.get(...)` |

## Output schema

```
structural_score: 0-1   # higher = more similar
change_detected: bool
change_score: 0-1       # complement of preservation
confidence_band: "stable" | "transition" | "unstable"
                        # also accepts: "stable" | "monitoring" | "diverging"
analysis_id: UUID       # for audit_replay
engine_version: str
provenance: dict
metrics:
  sim_local: 0-1
  sim_fractal: 0-1      # ANCHOR ~0.80 when stable
  sim_spectral: 0-1
  sim_transition: 0-1
  sim_trend: 0-1
  fingerprint_available: bool
  fingerprint_reason: str | null
multiscale.scale_profile (when use_multiscale=True):
  structural_slope: float    # >0.1 fine | ~0 broadband | <-0.1 macro | <-0.5 fractal
  profile_score: 0-1
semantic (when include_semantic=True):
  alert_level: "normal" | "attention" | "alert" | "critical"
  severity: "none" | "low" | "moderate" | "high" | "critical"
  severity_score: 0-100
  recommended_action: "log_only" | "monitor" | "human_review" | "immediate_human_review"
  trend: "stable" | "monitoring" | "diverging"
  summary: str
domain_inference (when domain="auto"):
  inferred: str
  confidence: 0-1
  fallback_used: bool
  reasoning: str
```

## Signal requirements

| Length | Behavior |
|---|---|
| < 10 | HTTP 422 |
| 10-49 | Single-scale only, warning returned |
| 50-99 | Multiscale engaged |
| 200-500 | Optimal |
| 500+ | Consider windowing |
| Fingerprint with baseline | min 50 |
| Fingerprint without baseline | min 192 |

## Thresholds

- `score > 0.70` → stable
- `score < 0.35` → diverging / unstable
- `0.35-0.70` → transition / monitoring
- `sim_fractal ~0.80` is anchor; below 0.70 = fundamental shift

## "diverging" semantic note

> "diverging" does NOT mean "getting worse". It means structure CHANGED. Could be improvement, degradation, or neutral. The API perceives, doesn't judge.

## Error codes

| Code | Type | Action |
|---|---|---|
| 400 / 422 | ValidationError | Fix request, do not retry |
| 401 | AuthError | Verify key. **Note**: also fires (misleadingly) on free-tier quota exhaustion |
| 429 | RateLimitError | Wait `retry_after` |
| 5xx | APIError | SDK auto-retries |

## Performance

- Single call: ~250-500ms (multiscale) or ~200ms (`use_multiscale=False`)
- Batch: ~250-300ms per signal in batches of 100
- Vector: ~20-28ms per channel (64 channels in ~1.3-1.8s)
- HTTP/2 (SDK 1.4+): `pip install alphainfo[http2]`

## Deterministic guarantees (verified)

1. Batch and individual calls produce identical results
2. Similarity matrices exactly symmetric with unit diagonal
3. Channel permutation does not change aggregated `structural_score`
4. Sync and async clients produce identical results
5. Without baseline, score is largely amplitude-invariant
6. With baseline, amplitude registers
7. Every analysis reproducible via `audit_replay(analysis_id)`
