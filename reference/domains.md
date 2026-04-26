# Domain Selection Guide

10 domains (calibrated sensitivity), all available on every plan.

## The domains

| Domain | Aliases | Use for | Typical sampling rate |
|---|---|---|---|
| `auto` | — | Unknown signal — let API infer | any |
| `generic` | — | Universal default | any |
| `finance` | `fintech` | Returns, prices, vol | 1 (daily), 1/60 (minute), 1/3600 (hourly) |
| `biomedical` | `biomed` | ECG, EEG, EMG, PPG, vitals | 100-10,000 |
| `sensors` | `iot`, `sensor` | IoT, vibration, SCADA | 1-1000 |
| `ai_ml` | `ml`, `ai`, `mlops` | Bounded metrics [0,1] or [0,100], model outputs | varies |
| `security` | `cyber`, `logs` | Auth events, traffic, log rates | 1-100 |
| `power_grid` | `power`, `grid` | 50/60 Hz electrical signals | 50, 60, 1000 |
| `traffic` | `net`, `network` | Flow, congestion, packet rates | 1-100 |
| `seismic` | `earthquake` | Heavy-tailed, sparse-peak data | 50-500 |

## When to use `auto`

Pass `domain='auto'` and read `result.domain_inference.reasoning`:
- Unknown CSV column
- Mixed-source pipeline
- Onboarding new user
- Sanity check on a domain you THINK you know

If `fallback_used=True`, the API was unsure — consider re-call with `generic`.

## How much does domain choice matter?

Empirically, all domains share the same core engine — pair similarity ordering preserved across domains with correlation 0.99+. Domain choice mostly affects **magnitude** (~10% variation in score). For most tasks, picking correctly improves sensitivity but doesn't change the conclusion.

## When the wrong domain hurts most

- Periodic biomedical data (ECG, EEG) on `generic` → may miss subtle physiological changes
- Heavy-tailed financial returns on `generic` → underestimate volatility regime shifts
- High-frequency vibration on `finance` → completely miscalibrated

When in doubt, run with two domains and compare scores. If they differ a lot, the domain matters and you should pick the right one.

## ~100 verified applications

Detailed catalog at https://www.alphainfo.io (use cases section). Highlights:

**Biomedical**: ECG arrhythmia classification, EEG seizure prediction, gait analysis, sleep quality, speech pathology

**Finance**: Crash early warning, regime detection (bull/bear), portfolio drift, model alpha validation, contagion

**Industrial / Sensors**: HVAC fault, EV battery SoH, pipeline leak, bridge structural health, fermentation

**Power / Energy**: Grid stability, solar panel efficiency, wind turbine health

**Security**: Intrusion detection, fraud, AI-content detection, login pattern anomaly

**MLOps**: Model drift, agent behavioral drift, training curve anomaly

**Climate**: El Niño onset, forest fire prediction, earthquake precursor, air quality

If a new domain doesn't fit, the encoding is probably the lever — see `reference/api_guide.md` and the 5 official encoding patterns.
