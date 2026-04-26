# Interpreting AlphaInfo Results

How to translate API output into human-readable insight you surface to the user.

## The decision funnel

```
API output
    ↓
Is change_detected=True AND severity_score > 60?
    → "Significant change detected" + canal delator if vector
    ↓
Is score < 0.35 (diverging)?
    → "Structure diverged" + which fingerprint dim dropped most
    ↓
Is score > 0.70 (stable)?
    → "Structure preserved" + any warnings
    ↓
Middle (0.35-0.70)?
    → "Transition zone" + trend direction
```

## Semantic layer translation

Always pass `include_semantic=True` (helpers do this by default).

| `semantic.alert_level` | Surface to user as |
|---|---|
| `normal` | "No action needed." |
| `attention` | "Worth monitoring." |
| `alert` | "Check soon." |
| `critical` | "Investigate now." |

| `semantic.recommended_action` | Workflow |
|---|---|
| `log_only` | Archive, no further action |
| `monitor` | Track over time |
| `human_review` | Flag for team |
| `immediate_human_review` | Escalate immediately |

Always parrot back `semantic.summary` (already emoji-decorated and human-readable).

## Fingerprint dimension interpretation

When alerting, the dimension that DROPPED most reveals the failure type:

| Dimension | What dropping means |
|---|---|
| `sim_local` | Point-to-point shape changed (jitter, noise, warp) |
| `sim_fractal` | Self-similarity / complexity changed (regime shift fundamental) |
| `sim_spectral` | Frequency content shifted (new harmonics, drift) |
| `sim_transition` | Phase-space topology changed (sharp transitions, steps) |
| `sim_trend` | Macro direction / slope changed (drift, secular shift) |

### Phrasing per dropped dim

- **sim_local low** → "The fine-grained shape is different."
- **sim_fractal low** → "Something fundamental about complexity changed."
- **sim_spectral low** → "Frequency content or rhythm changed."
- **sim_transition low** → "There's a new sharp event or regime boundary."
- **sim_trend low** → "The macro direction shifted."

## Multiscale curvature

`metrics.multiscale.scale_profile.structural_slope`:

| Range | Interpretation |
|---|---|
| > 0.1 | Change at FINE scale (detail) |
| -0.05 to 0.05 | Uniform change across scales |
| -0.1 to -0.05 | Slight large-scale tendency |
| < -0.1 | Change at LARGE scale (regime) |
| < -0.5 | Fractal / computation signature |

## Fingerprint scenarios (from `/v1/guide`)

| Scenario | local | fractal | spectral | transition |
|---|---|---|---|---|
| Same signal, shifted | high | high | high | high |
| Shape change (sine→square) | medium | high | low | very low |
| Frequency change | high | high | high | medium |
| Gradual drift | high | high | high | medium |
| Chaotic bifurcation | low | high | medium | very low |
| Noise added | medium | high | medium | medium |

## Canal delator phrasing

```python
print(f"{r['delator_channel']} is driving the change "
      f"(score {r['delator_score']:.2f}). "
      f"Severity {r['severity_score']:.0f}/100. "
      f"Action: {r['recommended_action']}.")
```

If MULTIPLE channels at similar low scores → cascade failure (propagating).

## When to hedge

- Signal length < 50 → ALWAYS warn user "Results unreliable, use more samples"
- All fingerprint dims near 0.80 → "stable anchor", no strong signal
- Score exactly 1.000 → verify signal != baseline
- Score very unstable across reruns → check stochastic baseline, may need averaging

## "diverging" warning

`diverging` does NOT mean "getting worse" — it means CHANGED. Could be improvement.
Don't surface "things are bad" without checking severity_score AND domain context.
