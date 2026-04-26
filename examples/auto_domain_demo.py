"""
EXAMPLE: Let the API auto-infer the right domain.

Runs `analyze_auto` against 3 different signal types and shows what the
API picks + reasoning. Useful when you don't know which of the 10 domains
to use.

Run:
  pip install yfinance numpy
  export ALPHAINFO_API_KEY=ai_...
  python examples/auto_domain_demo.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from lib.setup import setup
from lib.plan import detect_plan, explain_plan
from lib.helpers import auto_compare


def get_financial_returns():
    """Real S&P 500 daily log-returns from yfinance."""
    try:
        import yfinance as yf
        data = yf.download('SPY', period='1y', interval='1d',
                           progress=False, auto_adjust=True)
        prices = data['Close'].values.flatten()
        return np.diff(np.log(prices))
    except ImportError:
        # Fallback: heavy-tailed Student-t
        return np.random.standard_t(df=3, size=250) * 0.01


def get_ecg_like(fs=250, duration_sec=2):
    """Synthetic ECG-like (PQRST waveform)."""
    t = np.arange(duration_sec * fs) / fs
    period = 60.0 / 70  # 70 bpm
    phase = (t % period) / period
    pqrst = (
        0.15 * np.exp(-((phase - 0.10)**2) / (2 * 0.0015)) +     # P
        -0.20 * np.exp(-((phase - 0.18)**2) / (2 * 0.0005)) +    # Q
        1.00 * np.exp(-((phase - 0.20)**2) / (2 * 0.005)) +      # R
        -0.10 * np.exp(-((phase - 0.22)**2) / (2 * 0.0008)) +    # S
        0.20 * np.exp(-((phase - 0.40)**2) / (2 * 0.005))        # T
    )
    return pqrst + 0.02 * np.random.normal(size=len(t))


def get_iot_vibration(n=500):
    """Bearing-like vibration: 50Hz fundamental + harmonics + noise."""
    t = np.arange(n) / 1000
    return (np.sin(2 * np.pi * 50 * t) +
            0.3 * np.sin(2 * np.pi * 100 * t) +
            0.1 * np.sin(2 * np.pi * 150 * t) +
            0.05 * np.random.normal(size=n))


def main():
    print("=== Auto-domain inference demo ===\n")

    client = setup(check_health=True)
    plan = detect_plan(client)
    print(explain_plan(plan), "\n")

    np.random.seed(0)
    datasets = [
        ('Financial returns (S&P 500 daily, real yfinance data)',
         get_financial_returns(), 1.0,  'finance (or seismic — both have heavy tails)'),
        ('ECG-like (synthetic, PQRST waveform)',
         get_ecg_like(), 250.0,         'biomedical'),
        ('IoT vibration (50Hz fundamental + harmonics)',
         get_iot_vibration(), 1000.0,   'sensors'),
    ]

    for name, signal, fs, expected in datasets:
        print(f"━━ {name} ━━")
        signal = signal.tolist() if hasattr(signal, 'tolist') else signal

        # Use signal vs noise as baseline (just to invoke auto)
        baseline = np.random.normal(0, np.std(signal), len(signal)).tolist()

        r = auto_compare(client, signal=signal, baseline=baseline, plan=plan,
                         sampling_rate=fs)

        print(f"  Inferred domain: {r['inferred_domain']} "
              f"(confidence {r['domain_confidence']})")
        print(f"  Reasoning: {r['domain_reasoning']}")
        print(f"  Score: {r['score']:.3f}  band: {r['confidence_band']}")
        print(f"  Expected: {expected}")
        print()

    print("Note: 'auto' is most useful for unknown CSVs and exploratory analysis.")
    print("For production with known domain, pass it explicitly.")
    print(f"\nAll 10 domains available on every plan — see https://www.alphainfo.io/pricing")


if __name__ == '__main__':
    main()
