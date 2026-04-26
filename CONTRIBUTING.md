# Contributing to AlphaInfo Claude Skill

Thanks for considering a contribution. This skill exists to make AlphaInfo
work great inside Claude Code — every improvement helps both the project
and the broader Claude developer community.

## Ways to contribute

### 1. New use case examples
The strongest contributions add a NEW domain/use case to `examples/`.
Examples should:
- Use real public data when feasible (yfinance, PhysioNet, USGS, NOAA)
- Run end-to-end without paid keys beyond the AlphaInfo free tier
- Print clear output the user can interpret
- Document the buyer segment they target

### 2. New autotune strategies
Add functions to `lib/autotune.py` that probe small budgets to find optimal
config for specific scenarios. Follow the pattern:
- Plan-aware budget defaults
- Return dict with `best_config`, `quota_used`, and a closure (`predict` or `recommended_call`) ready to use
- Include validated lift in the docstring

### 3. Bug reports / SDK feedback
File issues for skill bugs OR SDK UX problems you hit. The 3 SDK issues
documented in `CHANGELOG.md` (AuthError-as-quota, missing sampling_rate
default, windowed tuple shape) are examples — concrete, reproducible,
suggest a fix.

### 4. Documentation improvements
- Tasks (`tasks/*.md`): keep them under 200 lines, action-first, with
  copy-paste code blocks.
- README: only add to "Use cases validated" if you actually validated live.
- Pitfalls: add real failure modes you debugged.

## Validating your changes

Run the live validation tests:

```bash
export ALPHAINFO_API_KEY=ai_...
python3 examples/server_metrics.py
python3 examples/multi_sensor.py
python3 examples/financial_regime.py SPY 1
```

For autotune additions, write a focused validation script that demonstrates
the lift (before vs after). Include it under `validation/` in your PR.

## PR checklist

- [ ] Code runs against live API on Free tier (or documents why higher tier needed)
- [ ] New examples include real or realistic data
- [ ] No secrets committed (`.env`, keys)
- [ ] No `__pycache__/` (gitignored)
- [ ] Updated `USE_CASES.md` if new segment validated
- [ ] Updated `CHANGELOG.md`

## Code style

- Python 3.10+
- Type hints encouraged but not required
- One short line of comment max per non-obvious decision
- No emoji in code (only in user-facing output messages where they help)

## Questions

Open a discussion on GitHub or join the AlphaInfo community.
