"""
Plan-aware capabilities for AlphaInfo skill.

Detected at runtime via client.rate_limit_info.limit. Caps verified live
against /v1/plans on 2026-04-26.
"""
from __future__ import annotations
from typing import Any
from alphainfo import AlphaInfo


# Authoritative capability matrix from /v1/plans (verified 2026-04-26)
# Slug → (monthly_limit, price_cents, capability dict)
PLANS: dict[int, dict[str, Any]] = {
    50: {
        'slug': 'free', 'name': 'Free', 'price_usd': 0,
        'caps': {
            'monthly_limit': 50,
            'max_channels': 3,
            'max_batch_size': 10,
            'max_concurrent': 1,
            'max_signal_length': 10_000,
            'retention_days': 7,
            'executive_reports': False,
            'custom_configs': False,
            'dedicated_endpoint': False,
            # Skill-derived guidance (we err conservative on free)
            'max_windows_recommended': 5,
            'max_grid_candidates': 5,
            'probes_recommended_count': 1,
        },
    },
    5_000: {
        'slug': 'starter', 'name': 'Starter', 'price_usd': 49,
        'caps': {
            'monthly_limit': 5_000,
            'max_channels': 8,
            'max_batch_size': 10,
            'max_concurrent': 2,
            'max_signal_length': 100_000,
            'retention_days': 30,
            'executive_reports': True,
            'custom_configs': False,
            'dedicated_endpoint': False,
            'max_windows_recommended': 50,
            'max_grid_candidates': 10,
            'probes_recommended_count': 5,
        },
    },
    25_000: {
        'slug': 'growth', 'name': 'Growth', 'price_usd': 199,
        'caps': {
            'monthly_limit': 25_000,
            'max_channels': 16,
            'max_batch_size': 50,
            'max_concurrent': 5,
            'max_signal_length': 500_000,
            'retention_days': 60,
            'executive_reports': True,
            'custom_configs': True,
            'dedicated_endpoint': False,
            'max_windows_recommended': 200,
            'max_grid_candidates': 50,
            'probes_recommended_count': 11,  # full library
        },
    },
    100_000: {
        'slug': 'professional', 'name': 'Professional', 'price_usd': 499,
        'caps': {
            'monthly_limit': 100_000,
            'max_channels': 32,
            'max_batch_size': 100,
            'max_concurrent': 8,
            'max_signal_length': 1_000_000,
            'retention_days': 90,
            'executive_reports': True,
            'custom_configs': True,
            'dedicated_endpoint': False,
            'max_windows_recommended': 1_000,
            'max_grid_candidates': 100,
            'probes_recommended_count': 11,
        },
    },
    -1: {  # is_unlimited
        'slug': 'enterprise', 'name': 'Enterprise', 'price_usd': None,
        'caps': {
            'monthly_limit': -1,
            'max_channels': 64,
            'max_batch_size': 100,
            'max_concurrent': 20,
            'max_signal_length': 5_000_000,
            'retention_days': 365,
            'executive_reports': True,
            'custom_configs': True,
            'dedicated_endpoint': True,
            'max_windows_recommended': 5_000,
            'max_grid_candidates': 100,
            'probes_recommended_count': 11,
        },
    },
}

PRICING_URL = 'https://www.alphainfo.io/pricing?ref=claude-skill'
REGISTER_URL = 'https://www.alphainfo.io/register?ref=claude-skill'

# Op → capability key. Used by adapt().
OP_TO_CAP = {
    'channels': 'max_channels',
    'batch': 'max_batch_size',
    'windows': 'max_windows_recommended',
    'signal_length': 'max_signal_length',
    'grid_candidates': 'max_grid_candidates',
    'probes': 'probes_recommended_count',
    'concurrent': 'max_concurrent',
}


def detect_plan(client: AlphaInfo) -> dict[str, Any]:
    """Detect the user's plan from rate_limit_info.limit.

    Populates rate_limit_info via a free health() call. Returns dict with
    slug, name, price_usd, caps, remaining, used_pct.

    If the limit isn't recognized (e.g., new plan), returns a safe default
    matching the closest known plan with a `verified=False` flag.
    """
    client.health()  # populates rate_limit_info, free, no quota
    rli = client.rate_limit_info
    if rli is None:
        # Fallback: assume Free, mark unverified
        return {**PLANS[50], 'remaining': None, 'limit': None, 'used_pct': None,
                'verified': False, 'reason': 'rate_limit_info unavailable'}

    limit = rli.limit
    plan = PLANS.get(limit)
    if plan is None:
        # Unknown plan tier — pick nearest below
        candidates = sorted([k for k in PLANS if k > 0 and k <= limit])
        plan = PLANS[candidates[-1]] if candidates else PLANS[50]
        verified = False
    else:
        verified = True

    used_pct = None
    if rli.limit and rli.remaining is not None and rli.limit > 0:
        used_pct = 1.0 - (rli.remaining / rli.limit)

    return {
        **plan,
        'remaining': rli.remaining,
        'limit': rli.limit,
        'used_pct': used_pct,
        'verified': verified,
    }


def adapt(plan: dict[str, Any], op: str, requested_size: int) -> dict[str, Any]:
    """Decide whether to allow / cap an operation given the plan.

    Args:
        plan: dict from detect_plan()
        op: 'channels' | 'batch' | 'windows' | 'signal_length' | 'grid_candidates' | 'probes'
        requested_size: what the user wants

    Returns dict:
        adjusted_size: int (== requested_size if within cap, else cap)
        within_cap: bool
        upgrade_hint: str | None (CTA to surface to user when capped)
    """
    cap_key = OP_TO_CAP.get(op)
    if not cap_key:
        return {'adjusted_size': requested_size, 'within_cap': True, 'upgrade_hint': None}

    cap = plan['caps'].get(cap_key)
    if cap is None or requested_size <= cap:
        return {'adjusted_size': requested_size, 'within_cap': True, 'upgrade_hint': None}

    # Find cheapest plan that fits the requested size.
    # Enterprise (price_usd=None) sorts last via inf so it's only picked when
    # nothing else fits.
    fits_in = []
    for limit, p in PLANS.items():
        plan_cap = p['caps'].get(cap_key, 0)
        if plan_cap >= requested_size:
            price_for_sort = p.get('price_usd') if p.get('price_usd') is not None else float('inf')
            fits_in.append((price_for_sort, p))
    fits_in.sort(key=lambda x: x[0])
    next_plan = fits_in[0][1] if fits_in else None

    hint = None
    if next_plan and next_plan['slug'] != plan['slug']:
        price = next_plan.get('price_usd')
        price_str = f"${price}/mo" if price else "Enterprise"
        hint = (
            f"Capped at {cap} on {plan['name']} (you asked for {requested_size}). "
            f"{next_plan['name']} ({price_str}) lifts this to {next_plan['caps'].get(cap_key)}. "
            f"Upgrade: {PRICING_URL}"
        )

    return {'adjusted_size': cap, 'within_cap': False, 'upgrade_hint': hint}


def quota_warning(plan: dict[str, Any]) -> str | None:
    """Return a one-line warning if quota is nearing exhaustion. None otherwise."""
    used = plan.get('used_pct')
    if used is None or plan['caps']['monthly_limit'] == -1:
        return None
    remaining = plan.get('remaining')
    limit = plan.get('limit')
    if used >= 0.95:
        return (
            f"⚠️  {remaining}/{limit} analyses remaining this month on {plan['name']}. "
            f"Upgrade to avoid interruption: {PRICING_URL}"
        )
    if used >= 0.80:
        return (
            f"📊  Heads up: you've used {int(used*100)}% of {plan['name']} quota "
            f"({remaining}/{limit} left). Larger plans at {PRICING_URL}"
        )
    return None


def explain_plan(plan: dict[str, Any]) -> str:
    """Human-readable summary of plan + key caps."""
    caps = plan['caps']
    lines = [
        f"Connected on AlphaInfo {plan['name']} plan.",
        f"  Monthly limit: {caps['monthly_limit'] if caps['monthly_limit']>0 else 'unlimited'}",
        f"  Max channels (vector): {caps['max_channels']}",
        f"  Max batch: {caps['max_batch_size']}",
        f"  Max signal length: {caps['max_signal_length']:,} samples",
        f"  Audit retention: {caps['retention_days']} days",
    ]
    if plan.get('remaining') is not None:
        lines.append(f"  Remaining this month: {plan['remaining']:,}")
    return "\n".join(lines)
