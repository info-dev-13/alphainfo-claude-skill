"""
EXAMPLE: Detect anomalies in server CPU metrics — without a baseline.

Uses synthetic-but-realistic data shaped like Prometheus exports:
- Diurnal pattern (low at night, high in afternoon)
- Gaussian noise
- One injected incident (sustained CPU spike for 30 min)

Demonstrates `detect_internal_change()` — anomaly without baseline.
This is the most common dev scenario: someone has a CSV column from
Datadog/Grafana/Prometheus and asks "anything weird here?".

Run:
  export ALPHAINFO_API_KEY=ai_...
  python examples/server_metrics.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from lib.setup import setup
from lib.plan import detect_plan, explain_plan
from lib.helpers import quick_anomaly, monitor


def gen_realistic_cpu(n: int = 1440, seed: int = 42, with_incident: bool = True):
    """1 day @ 1-minute resolution = 1440 samples."""
    np.random.seed(seed)
    t = np.arange(n)
    # Diurnal cycle: low at 4am (240), peak at 4pm (960)
    base = 30 + 25 * np.sin(2 * np.pi * (t - 240) / 1440)
    # Gaussian process noise
    noise = np.random.normal(0, 4, n)
    cpu = np.clip(base + noise, 5, 95)

    if with_incident:
        # Inject incident: 30-min sustained spike at minute 840 (14:00)
        cpu[840:870] = np.clip(cpu[840:870] + 35, 5, 100)

    return cpu


def main():
    print("=== Server CPU anomaly detection (no baseline) ===\n")

    client = setup(check_health=True)
    plan = detect_plan(client)
    print(explain_plan(plan), "\n")

    cpu = gen_realistic_cpu(n=1440, with_incident=True).tolist()
    print(f"Generated {len(cpu)} CPU samples (24h @ 1min). "
          f"Incident: 30min spike at 14:00.\n")

    # ── Step 1: Yes/no anomaly check ────────────────────────────
    print("[1] quick_anomaly() — is there ANY internal change?")
    qa = quick_anomaly(client, cpu, plan, sampling_rate=1/60,
                       domain='sensors', intent='local_anomaly')
    print(f"  score={qa['score']:.3f}  band={qa['confidence_band']}")
    print(f"  alert: {qa['alert_level']} (severity {qa['severity_score']})")
    print(f"  → {qa['summary']}\n")

    if qa['alert_level'] in (None, 'normal'):
        print("  Nothing weird detected. Done.")
        return

    # ── Step 2: Localize WHERE the anomaly is ───────────────────
    print("[2] monitor() — sliding window to localize WHEN it happened")
    mr = monitor(client, cpu, plan,
                 window_size=120,         # 2-hour windows
                 step=60,                 # 1-hour stride
                 sampling_rate=1/60,
                 baseline=cpu[:120],      # first 2h as "normal"
                 score_threshold=0.4)

    print(f"  {mr['n_windows']} windows, {mr['n_alerts']} alerts (score < 0.4)")
    if mr.get('effective_step') != 60:
        print(f"  (step bumped to {mr['effective_step']} due to plan cap)\n")

    if mr['alerts']:
        print(f"\n  Anomaly windows (start time → score):")
        for a in mr['alerts'][:10]:
            mins = a['start']
            hh = mins // 60
            mm = mins % 60
            print(f"    {hh:02d}:{mm:02d}  score={a['score']:.3f}")

    worst = mr['worst_window']
    if worst:
        h, m = worst['start'] // 60, worst['start'] % 60
        print(f"\n  WORST window: {h:02d}:{m:02d}  score={worst['score']:.3f}")
        print(f"  (incident was at 14:00 — did skill localize correctly?)")

    if mr.get('upgrade_hint'):
        print(f"\n[plan] {mr['upgrade_hint']}")

    print(f"\n📊 Audit trail: analysis_id={qa['analysis_id']}")
    print(f"   Retained {plan['caps']['retention_days']} days on {plan['name']}")


if __name__ == '__main__':
    main()
