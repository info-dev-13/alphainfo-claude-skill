"""
EXAMPLE: Multi-sensor fault isolation (canal delator).

Synthetic but realistic 4-sensor HVAC system. Demonstrates the
analyze_vector advantage: 1 quota for all channels + automatic identification
of WHICH sensor is failing.

NOTE: real industrial datasets exist (NASA C-MAPSS turbofan, MIMII machine
audio) but require larger downloads. This example shows the pattern with
synthetic data that mimics realistic sensor profiles.

Run:
  export ALPHAINFO_API_KEY=ai_...
  python examples/multi_sensor.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import random
import numpy as np

from lib.setup import setup
from lib.plan import detect_plan, explain_plan
from lib.helpers import multi_channel


def gen_normal_hvac(n: int = 200, seed: int = 1):
    """Generate normal HVAC operation across 4 sensors."""
    rng = random.Random(seed)
    return {
        'temperature': [20 + 0.5*math.sin(2*math.pi*i/100) + 0.1*rng.gauss(0,1)
                        for i in range(n)],
        'pressure':    [1.01 + 0.02*math.sin(2*math.pi*i/80) + 0.005*rng.gauss(0,1)
                        for i in range(n)],
        'airflow':     [0.5 + 0.1*math.sin(2*math.pi*i/30) + 0.02*rng.gauss(0,1)
                        for i in range(n)],
        'vibration':   [0.3*math.sin(2*math.pi*i/5) + 0.05*rng.gauss(0,1)
                        for i in range(n)],
    }


def main():
    print("=== Multi-sensor fault isolation: HVAC system ===\n")

    client = setup(check_health=True)
    plan = detect_plan(client)
    print(explain_plan(plan), "\n")

    # Normal baseline
    normal = gen_normal_hvac(n=200, seed=1)

    # Inject fault: airflow drops 50% (clogged filter)
    faulty = {**normal}
    faulty['airflow'] = [v * 0.5 for v in normal['airflow']]

    print("Scenario: 4-sensor HVAC. Filter clogged → airflow drops 50%.\n")
    print(f"On {plan['name']} plan, vector endpoint allows up to {plan['caps']['max_channels']} channels.\n")

    # ── Single call, all channels ──────────────────────────────
    print("Calling analyze_vector (1 quota for all channels)...")
    r = multi_channel(client, faulty, normal, plan,
                      sampling_rate=10.0, domain='sensors')

    print(f"\nAggregated score: {r['aggregated_score']:.3f}")
    print(f"Alert: {r['alert_level']} (severity {r['severity_score']:.0f}/100)")
    print(f"Recommended action: {r['recommended_action']}")
    print(f"\n🎯 CANAL DELATOR: {r['delator_channel']} (score {r['delator_score']:.3f})\n")

    print("Per-channel structural similarity vs normal:")
    for ch, score in sorted(r['per_channel_scores'].items(),
                            key=lambda x: x[1]):
        marker = '🔥' if score < 0.5 else '✓ '
        bar = '█' * int(score * 30) + '░' * (30 - int(score * 30))
        print(f"  {marker} {ch:12s} [{bar}] {score:.3f}")

    if r.get('channels_dropped', 0) > 0:
        print(f"\n⚠️  Dropped {r['channels_dropped']} channels (over plan cap of "
              f"{plan['caps']['max_channels']})")

    if r.get('upgrade_hint'):
        print(f"\n[plan] {r['upgrade_hint']}")

    print(f"\n📊 Audit trail: analysis_id={r['analysis_id']}")
    print(f"   Replay anytime with: client.audit_replay('{r['analysis_id']}')")
    print(f"   (Retained {plan['caps']['retention_days']} days on {plan['name']})")


if __name__ == '__main__':
    main()
