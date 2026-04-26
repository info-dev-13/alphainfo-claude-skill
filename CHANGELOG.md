# Changelog

All notable changes to the AlphaInfo Claude Skill.

## [1.0.0] — 2026-04-26 (initial public release)

### Highlights

- **30 use cases validated live** across 12 buyer segments (DevOps, MLOps,
  Quant, BioMed, Security, SaaS, Industrial, Audio, Climate, Gaming,
  Streaming, Logistics) — see `USE_CASES.md`.
- **`smart_anomaly()` 4-stage self-correcting cascade** — detects borderline
  results and automatically escalates: alt-domain → fingerprint dim inspection
  → sliding window. Validated lifts:
  - Pod restart: sev 42 → **92 critical** (monitor)
  - Bearing wear: sev 20 → **67 alert** (fingerprint dim sim_transition=0.48)
  - Climate heat wave: sev 50 → **75 alert** (fingerprint + monitor)
  - Deploy +30%: sev 19 → **61 alert** (fingerprint + monitor + amplitude warning)
- **`smart_compare()` mirror cascade** for "is B different from A?" with
  amplitude-shift detection.
- **`autotune_classifier()`** — finds the best (reference, classifier) combo
  via cross-validation. Validated on real PhysioNet ECG: 50% → 100% CV
  accuracy without manual config.
- **Plan-aware caps** verified against live `/v1/plans` (50, 5K, 25K, 100K,
  unlimited). Helpers auto-truncate and surface upgrade hints.
- **Real-data examples**: yfinance financial regime, PhysioNet ECG anomaly,
  multi-sensor fault, server metrics, auto-domain demo.

### Components

- `lib/setup.py` — API key detection + onboarding message with registration link.
- `lib/plan.py` — plan detection + capability matrix + smart `adapt()` function.
- `lib/helpers.py` — 7 plan-aware wrappers (compare, monitor, multi_channel,
  quick_anomaly, auto_compare, fingerprint, safe_call).
- `lib/autotune.py` — 5 self-tuning functions (autotune_classifier, baseline,
  window, domain) + 2 self-correcting cascades (smart_anomaly, smart_compare)
  + amplitude-shift detector + auto_retry primitive.
- 7 task recipes in `tasks/`
- 4 reference files in `reference/`
- 5 examples in `examples/` (3 with real public data)

### Security positioning — DEFENSE not OFFENSE

The skill is positioned for **defenders** (CISOs, IT ops, compliance, privacy
teams). Validated security use cases:

- **Account takeover detection** (sev 84) — protect users from compromised credentials by detecting behavior pattern changes
- **Auth system health monitoring** (sev 96) — protect your platform from credential-stuffing campaigns proactively
- **Privileged access anomaly** (sev 67) — protect sensitive systems from insider threats / compromised admin accounts
- **Data access pattern monitoring** (sev 92) — protect fileservers from ransomware and exfiltration early

These are framed as PROTECTION, not attack-detection. Same technical
capability, but positioned for the actual buyer (defender, not red-teamer).

### Reported SDK UX issues (separate from skill)

1. AuthError-as-quota-exhaustion: `/v1/analyze` returns misleading
   "Invalid or missing API key" message when free tier is exhausted.
2. `sampling_rate` required without sensible default — first error every dev hits.
3. `analyze_windowed` returns tuples `(start, end, score)`, inconsistent with
   other endpoints that return objects with attributes.

The skill works around all three (better error message in setup; helpers
demand sampling_rate; tuple normalization in monitor wrapper).

### Quota cost reference

| Operation | Free | Starter |
|---|---|---|
| `compare()`, `quick_anomaly()` (single call) | 1 | 1 |
| `smart_anomaly()` (cascade, only pays for what's needed) | 1-10 | 1-15 |
| `smart_compare()` (cascade) | 1-10 | 1-15 |
| `autotune_classifier()` (8-combo CV) | 24 | 50 |
| `autotune_baseline()` | 4 | 8 |
| `autotune_window()` | 6 | 12 |
| `multi_channel()` (vector) | 1 | 1 |
| `monitor()` (sliding window) | 1 per window | 1 per window |
