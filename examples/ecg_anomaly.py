"""
EXAMPLE: Detect anomalous beats in real ECG data.

Uses MIT-BIH Arrhythmia Database (PhysioNet, free, well-known clinical data).
Record 100 contains mostly Normal (N) beats with occasional Atrial premature (A)
beats — a clinically relevant anomaly.

Demonstrates:
  - lib.helpers.compare() to compare suspicious beat vs known-normal template
  - 5-D fingerprint per beat for classification
  - Domain='biomedical' calibration for ECG-rate signals

Run:
  pip install wfdb numpy
  export ALPHAINFO_API_KEY=ai_...
  python examples/ecg_anomaly.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import wfdb

from lib.setup import setup
from lib.plan import detect_plan, explain_plan, adapt
from lib.helpers import compare


def extract_beats(signal, ann_samples, half_window=108):
    """Extract beat windows around each annotation.

    half_window=108 samples = 300ms @ 360 Hz, captures full PQRST.
    Returns (beats, valid_idx) — drops beats too close to signal edges.
    """
    beats = []
    valid_idx = []
    for i, pos in enumerate(ann_samples):
        if pos - half_window >= 0 and pos + half_window < len(signal):
            beats.append(signal[pos - half_window:pos + half_window].tolist())
            valid_idx.append(i)
    return beats, valid_idx


def main(record_id: str = '100', duration_sec: int = 30) -> None:
    print(f"=== ECG anomaly detection: MIT-BIH record {record_id} ===\n")

    client = setup(check_health=True)
    plan = detect_plan(client)
    print(explain_plan(plan), "\n")

    # ── Real ECG data from PhysioNet ─────────────────────────────
    fs = 360  # MIT-BIH sampling rate
    sampto = duration_sec * fs
    print(f"Fetching {duration_sec}s of ECG (sampto={sampto})...")

    record = wfdb.rdrecord(record_id, pn_dir='mitdb', sampto=sampto)
    ann = wfdb.rdann(record_id, 'atr', pn_dir='mitdb', sampto=sampto)

    # Use lead MLII (channel 0)
    ecg = record.p_signal[:, 0]
    print(f"ECG: {len(ecg)} samples @ {fs} Hz = {len(ecg)/fs:.1f}s")
    print(f"Annotations: {len(ann.symbol)} marks, types: {set(ann.symbol)}\n")

    # Extract beat windows around each annotated beat
    beats, valid_idx = extract_beats(ecg, ann.sample, half_window=108)
    labels = [ann.symbol[i] for i in valid_idx]
    print(f"Extracted {len(beats)} beat windows (216 samples each)")
    counts = {l: labels.count(l) for l in set(labels)}
    print(f"Label counts: {counts}\n")

    # Find indices of N (normal) and A (atrial premature)
    normal_idx = [i for i, l in enumerate(labels) if l == 'N']
    abnormal_idx = [i for i, l in enumerate(labels) if l == 'A']

    if not normal_idx or not abnormal_idx:
        print("ERROR: This record doesn't contain both N and A beats — try '102' or '108'")
        return

    print(f"  N (normal) beats: {len(normal_idx)}")
    print(f"  A (atrial premature) beats: {len(abnormal_idx)}\n")

    # ── Build template: average normal beat ──────────────────────
    template = np.mean([beats[i] for i in normal_idx], axis=0).tolist()
    print(f"Template = mean of {len(normal_idx)} normal beats\n")

    # ── Plan-aware comparison budget ─────────────────────────────
    # Compare a few normals + a few abnormals vs template
    n_each = adapt(plan, 'batch', 5)['adjusted_size']  # max 5 per class on Free
    print(f"Comparing {n_each} normals + {n_each} abnormals vs template "
          f"({n_each*2} quota)...\n")

    print(f"{'Type':6s} {'Score':>8s} {'Band':>14s} {'Alert':>10s} {'Severity':>10s}")
    print("-" * 60)

    n_results = []
    for i in normal_idx[:n_each]:
        r = compare(client, signal=beats[i], baseline=template, plan=plan,
                    sampling_rate=float(fs), domain='biomedical')
        n_results.append(r['score'])
        print(f"{'N':6s} {r['score']:>8.3f} {r['confidence_band']:>14s} "
              f"{r['alert_level'] or '-':>10s} {r['severity_score'] or 0:>10.0f}")

    a_results = []
    for i in abnormal_idx[:n_each]:
        r = compare(client, signal=beats[i], baseline=template, plan=plan,
                    sampling_rate=float(fs), domain='biomedical')
        a_results.append(r['score'])
        print(f"{'A':6s} {r['score']:>8.3f} {r['confidence_band']:>14s} "
              f"{r['alert_level'] or '-':>10s} {r['severity_score'] or 0:>10.0f}")

    # ── Verdict ──────────────────────────────────────────────────
    print()
    n_mean = np.mean(n_results) if n_results else 0
    a_mean = np.mean(a_results) if a_results else 0
    sep = n_mean - a_mean
    print(f"Mean score — Normal: {n_mean:.3f}, Abnormal: {a_mean:.3f}, separation: {sep:.3f}")

    if sep > 0.15:
        print(f"✅ Clear separation: AlphaInfo distinguishes N from A beats on real ECG")
    elif sep > 0.05:
        print(f"⚠️  Modest separation: signal-level enough to flag, "
              f"but better with fingerprint centroid (see tasks/classify.md)")
    else:
        print(f"❌ Weak separation at scalar level — try fingerprint centroid classification")

    if plan['slug'] == 'free':
        print(f"\n[Tip] Starter ($49/mo): batch up to 50 beats per call (vs 10).")
        print(f"      Growth ($199): probes_biomedical includes tachycardia, PVC,")
        print(f"      lead_disconnect, atrial_fib pre-built detectors.")
        print(f"      → https://www.alphainfo.io/pricing?ref=claude-skill")


if __name__ == '__main__':
    record = sys.argv[1] if len(sys.argv) > 1 else '100'
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    main(record, duration)
