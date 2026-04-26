"""
EXAMPLE: Detect regime changes in S&P 500 returns.

Uses REAL data from Yahoo Finance (yfinance, free, no API key).
Demonstrates:
  - lib.helpers.monitor() for sliding-window over 2 years of daily returns
  - Plan-aware: caps windows / signal length to user's tier
  - Domain calibration: 'finance' for heavy-tailed returns

Run:
  pip install yfinance numpy
  export ALPHAINFO_API_KEY=ai_...
  python examples/financial_regime.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import yfinance as yf

from lib.setup import setup
from lib.plan import detect_plan, explain_plan
from lib.helpers import monitor, quick_anomaly


def main(ticker: str = 'SPY', years: int = 2) -> None:
    print(f"=== Regime detection: {ticker} over {years}y of daily returns ===\n")

    # Setup with onboarding if no key
    client = setup(check_health=True)
    plan = detect_plan(client)
    print(explain_plan(plan), "\n")

    # Real data: download via yfinance
    print(f"Downloading {ticker} from Yahoo Finance...")
    data = yf.download(ticker, period=f'{years}y', interval='1d',
                       progress=False, auto_adjust=True)
    prices = data['Close'].values.flatten()
    log_returns = np.diff(np.log(prices)).tolist()
    print(f"Got {len(log_returns)} daily returns "
          f"(mean={np.mean(log_returns):.4f}, std={np.std(log_returns):.4f})\n")

    # ── Step 1: Quick yes/no anomaly check (1 quota) ───────────────
    print("[1] Quick anomaly check on the whole stream...")
    qa = quick_anomaly(client, log_returns, plan,
                       sampling_rate=1.0, domain='finance')
    print(f"  score={qa['score']:.3f} band={qa['confidence_band']}")
    print(f"  alert: {qa['alert_level']} (severity {qa['severity_score']})")
    print(f"  → {qa['summary']}\n")

    # ── Step 2: Localize WHEN regime shifted (sliding window) ──────
    print("[2] Sliding window monitor (locate regime transitions)...")
    # 60-day windows = quarterly, 20-day step = monthly resolution
    mr = monitor(client, log_returns, plan,
                 window_size=60, step=20, sampling_rate=1.0,
                 domain='finance', score_threshold=0.4)
    print(f"  Analyzed {mr['n_windows']} windows, flagged {mr['n_alerts']} as low-similarity\n")

    if mr['alerts']:
        print(f"  Days where structural similarity dropped below 0.4 vs prior window:")
        for a in mr['alerts'][:10]:
            day_of_window = a['start']
            try:
                dt = data.index[day_of_window].strftime('%Y-%m-%d')
            except (IndexError, ValueError):
                dt = f"day {day_of_window}"
            print(f"    {dt}  score={a['score']:.3f}")

    worst = mr['worst_window']
    if worst:
        try:
            dt = data.index[worst['start']].strftime('%Y-%m-%d')
        except (IndexError, ValueError):
            dt = f"day {worst['start']}"
        print(f"\n  WORST window: starts {dt}, score={worst['score']:.3f}")
        print(f"  → This is when the structure of returns differed most from the surrounding period.")

    # ── Plan messaging ─────────────────────────────────────────────
    if mr.get('upgrade_hint'):
        print(f"\n  [plan] {mr['upgrade_hint']}")

    if plan['slug'] == 'free':
        print("\n  [Tip] Starter ($49/mo) unlocks finer windowing (50+ windows per signal),")
        print(f"        plus 11 finance-specific probes (vol_regime, crash_event, etc.).")
        print(f"        See https://www.alphainfo.io/pricing?ref=claude-skill")


if __name__ == '__main__':
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'SPY'
    years = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    main(ticker, years)
