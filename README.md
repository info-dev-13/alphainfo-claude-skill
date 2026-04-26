# AlphaInfo for Claude

> **Give Claude eyes for time-series structure.** A Claude Code skill that wires the [AlphaInfo Structural Intelligence API](https://www.alphainfo.io) into your Claude conversations — so you can detect anomalies, find regime changes, isolate failing sensors, and classify signals **without writing statistical code from scratch**.

## What this is

Claude can read numbers but can't *see structure*. With this skill installed:

- 👁️ **Detect anomalies** in any signal — with or without a baseline
- 📍 **Localize WHEN** something changed in a long stream
- 🔧 **Identify WHICH** of N sensors is failing (canal delator)
- 🧬 **Classify by structure** without training a model
- 🎯 **Compare two signals** with calibrated thresholds
- 📜 **Audit-replay** every analysis (compliance-ready)

Plus **autotune layer** that automatically finds the best config for your data (no manual tuning), 80+ pre-built domain probes (finance, biomedical, mlops, security, etc.), and 10 domain calibrations.

## Install (one line)

```bash
curl -fsSL https://raw.githubusercontent.com/info-dev-13/alphainfo-claude-skill/main/install.sh | sh
```

This:
1. Clones the skill into `~/.claude/skills/alphainfo`
2. Installs the `alphainfo` Python SDK
3. (Optional) installs `yfinance` and `wfdb` for real-data examples
4. Detects existing API key — or opens [the registration page](https://www.alphainfo.io/register?ref=claude-skill) so you can grab a free one (50 analyses/month, no card)

## 30-second quick start

```bash
# 1. Install (one line)
curl -fsSL https://raw.githubusercontent.com/info-dev-13/alphainfo-claude-skill/main/install.sh | sh

# 2. Get a free key (50 analyses/month, no credit card)
open https://www.alphainfo.io/register?ref=claude-skill

# 3. Save the key
mkdir -p ~/.alphainfo
echo 'ALPHAINFO_API_KEY=ai_...' > ~/.alphainfo/.env

# 4. Try it
cd ~/.claude/skills/alphainfo
python3 examples/server_metrics.py
```

That's it. Claude Code will pick up the skill in any future conversation.

## Quickstart inside Claude

After install, just talk to Claude in any project:

```
You: "I have CPU metrics from yesterday — anything weird?"
Claude: [uses the skill] "Detected critical anomaly at 14:00, severity 75/100. The sustained spike pattern differs structurally from your normal diurnal cycle. Audit ID: 5533a276..."
```

Or run an example directly:

```bash
cd ~/.claude/skills/alphainfo
python3 examples/server_metrics.py     # Server CPU anomaly detection
python3 examples/multi_sensor.py       # HVAC fault isolation
python3 examples/financial_regime.py SPY 2   # S&P 500 regime detection (real yfinance data)
python3 examples/ecg_anomaly.py 100 60       # ECG analysis (real PhysioNet data)
```

## The autotune + self-correction layer

Different references / classifiers / windows / domains give wildly different
results on the same data. Instead of relying on the AI (Claude) or developer
to guess, the skill probes small budgets of quota to find the right config
**and even ESCALATES strategy when the initial answer is borderline**:

### `smart_anomaly()` — the self-correcting cascade

3-stage cascade that only pays for what's needed:

1. **Stage 1**: quick anomaly with your domain (1 quota). Confident? → done.
2. **Stage 2**: try 3 alternative domains (3 quota). Better answer? → done.
3. **Stage 3**: escalate to sliding window (5-10 quota). Catches regime
   changes the global view missed.

**Validated improvements** (real test results):
| Case | Initial (1 quota) | After smart cascade | Improvement |
|---|---|---|---|
| k8s pod restart spike | sev 42 attention | **sev 92 critical** + localized | 10 quota total |
| SaaS conversion drop | sev 44 attention | **sev 79 alert** + localized | 10 quota total |
| CPU spike (already strong) | sev 70 alert | sev 70 alert (no escalation) | **1 quota only** |

The skill uses extra quota only when the answer needs it.

### Other autotune helpers

| Function | Tunes | Free budget | Validated lift |
|---|---|---|---|
| `autotune_classifier()` | reference × classifier (8 combos) | 24 quota | PhysioNet ECG N vs PVC: **50% → 100% CV** without manual config |
| `autotune_baseline()` | first/last/middle/median baseline strategies | 4 quota | More stable alerts |
| `autotune_window()` | window_size × step (best contrast) | 6 quota | Better localization |
| `autotune_domain()` | tries 2-3 candidate domains | 3 quota | Best calibration |

When Claude uses this skill on your data, it routes through autotune for
ambiguous configs — so the answer doesn't depend on Claude (or you) picking
the right knobs.

## What's verified to work (live tests on real data)

| Test | Data source | Result | Quota |
|---|---|---|---|
| **CPU anomaly localization** | Synthetic 24h CPU + 30-min spike | ✅ Critical alert (sev 75), localized to 13:12 (real spike 14:00) | 6 |
| **HVAC fault isolation** | 4-sensor synthetic | ✅ `airflow` identified as canal delator (score 0.253) | 1 |
| **S&P 500 regime detection** | **REAL yfinance**, 500 days | ✅ Anomaly detected, worst window 2024-04-25 | 7 |
| **Auto-domain inference** | Mixed | ✅ ECG→biomedical, returns→seismic (defensible), vibration→sensors | 3 |
| **ECG arrhythmia classification (N vs PVC)** | **REAL PhysioNet MIT-BIH** | ✅ **95% accuracy** with manual best config; **100% CV via `autotune_classifier`** (no manual tuning) | 40 / 24 |
| **Plan-aware capping** | Free plan | ✅ Auto-truncates 23→5 windows, 4→3 channels, surfaces upgrade hints | — |
| **Audit replay (compliance)** | Live | ✅ Returns full `AuditReplay` with reproducible score | 0 |

**Important methodology note**: ECG classification at 95% requires the skill's
documented best practices (domain-appropriate reference, standardization,
k-NN/LDA). A naive 1-line implementation gives ~50%. Read `tasks/classify.md`.

Full results in `VALIDATION.md`.

## How plan-aware works

The skill detects your AlphaInfo plan automatically and adapts:

| Cap | Free | Starter $49 | Growth $199 | Pro $499 | Enterprise |
|---|---|---|---|---|---|
| Analyses/mo | 50 | 5K | 25K | 100K | unlimited |
| Vector channels | 3 | 8 | 16 | 32 | 64 |
| Batch size | 10 | 10 | 50 | 100 | 100 |
| Signal length | 10K | 100K | 500K | 1M | 5M |
| Audit retention | 7d | 30d | 60d | 90d | 365d |

**You stay in control** — the skill never makes a paid call without your input. When a request exceeds your plan's caps, the skill *adapts down* and shows you what's missing. One contextual upgrade hint, max one per session.

All 10 domain calibrations + all 8 probe libraries are available on every plan. **Capacity is the differentiator, not features.**

## What's in here

```
~/.claude/skills/alphainfo/
├── SKILL.md                  Entry point Claude reads first
├── install.sh                One-line installer
├── lib/
│   ├── setup.py              Key detection + onboarding
│   ├── plan.py               Plan-aware capability matrix
│   └── helpers.py            7 native wrappers (compare, monitor, multi_channel, ...)
├── tasks/                    7 task recipes
├── reference/                4 reference files (API guide, interpretation, domains, pitfalls)
└── examples/                 5 runnable examples (3 with real public data)
```

## Use cases validated — 25 across 7 buyer segments

The skill is tested live against 25 distinct scenarios spanning DevOps,
MLOps, Quant/Finance, Biomedical, Security, SaaS/Product, and Industrial IoT.
**21 pass cleanly, 3 partial (honest borderline cases), 1 correct-low-severity.**
Full matrix in [`USE_CASES.md`](USE_CASES.md).

Highlights by segment:

| Segment | Best demo | Result |
|---|---|---|
| 🐛 **DevOps** (10 cases) | API 5xx spike, memory leak, DB slow queries | **critical sev 77-89** |
| 🤖 **MLOps** (3 cases) | Model accuracy drift, feature covariate shift | **alert sev 65-73** |
| 📈 **Quant** (4 cases, **REAL data**) | BTC, SPY, VIX, Treasuries via yfinance | regime changes detected |
| 🩺 **Biomed** (2 cases, **REAL PhysioNet**) | ECG arrhythmia N vs PVC via `autotune_classifier` | **100% CV accuracy** |
| 🛡️ **Security/Protection** (4 cases) | Account takeover, auth system health, privileged-access anomaly, ransomware-pattern detection | **critical sev 67-96** |
| 🚀 **SaaS/Product** (2 cases) | DAU drop after release, conversion funnel | sev 45-80 |
| 🏭 **Industrial** (2 cases) | HVAC multi-sensor fault, bearing wear | delator identified, sev 75 |

Validated across observability, MLOps, fintech, health tech, security
protection, SaaS analytics, industrial IoT, audio, climate, gaming, streaming,
and logistics.

## Where the API is borderline (be honest)

- **Pure amplitude regressions** (e.g., latency uniformly +30% with same shape):
  detected as low-severity (~0.80 score) because the *structure* is preserved.
  AlphaInfo measures structure, not magnitude. Use simple mean comparison for
  "did the average go up?". Use AlphaInfo for "did the *shape* change?"
- **Pure spectral changes** (e.g., bearing wear adding harmonics at same energy):
  scalar score sees as similar. Use `probes_industrial` (Starter+ tier) for
  these — pre-tuned for spectral failure modes.
- **Small A/B test lifts** (1-5% delta in conversion): correctly low severity.
  Use statistical t-tests for significance; AlphaInfo flags large changes only.

## What this is NOT

- Not an alternative to FAISS for billion-scale search
- Not a replacement for trained classifiers when you have lots of labels
- Not for sub-100ms HTTP-call latency (~250ms floor; per-comparison sub-100ms via vector OK)
- Not a magical "tell me what's wrong" — it perceives structure; you (Claude) provide the verdict

## Pricing & links

- 🆓 **Free**: 50 analyses/month — [register](https://www.alphainfo.io/register?ref=claude-skill)
- 💼 **Starter $49/mo**: 5K analyses, executive reports, 8-channel vector
- 🚀 **Growth $199/mo**: 25K analyses, custom configs, 16-channel vector
- 🏢 **Professional $499/mo**: 100K analyses, 32-channel vector
- 🏛️ **Enterprise**: unlimited, dedicated endpoint, 99.9% SLA

[Pricing details](https://www.alphainfo.io/pricing?ref=claude-skill) · [API Guide](https://www.alphainfo.io/v1/guide) · [Recipe Library](https://www.alphainfo.io/v1/recipes)

## License

MIT — use freely, contribute via PR.
