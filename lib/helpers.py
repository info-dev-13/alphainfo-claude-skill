"""
Plan-aware native helpers wrapping the AlphaInfo SDK.

Each helper:
1. Accepts a `plan` dict from lib.plan.detect_plan().
2. Calls lib.plan.adapt() before invoking the API to respect tier caps.
3. Returns a flat dict for ergonomic Claude consumption.
4. Includes any upgrade hints in the result so Claude can surface them.

Use these instead of direct client.* methods when the user is on Free or
Starter — they prevent surprise quota errors and produce better UX.
"""
from __future__ import annotations
from typing import Any, Sequence
from alphainfo import AlphaInfo
from alphainfo.exceptions import APIError, RateLimitError

from .plan import adapt


def quick_anomaly(client: AlphaInfo,
                  signal: Sequence[float],
                  plan: dict[str, Any],
                  sampling_rate: float = 10.0,
                  domain: str = 'generic',
                  intent: str = 'local_anomaly') -> dict[str, Any]:
    """Anomaly detection without baseline. Wraps detect_internal_change.

    Plan-aware: caps signal length to plan max.
    """
    sig_check = adapt(plan, 'signal_length', len(signal))
    sig = list(signal)[:sig_check['adjusted_size']]
    truncated = not sig_check['within_cap']

    r = client.detect_internal_change(
        signal=sig,
        sampling_rate=sampling_rate,
        domain=domain,
        intent=intent,
        include_semantic=True,
    )
    out = {
        'score': r.structural_score,
        'confidence_band': r.confidence_band,
        'change_detected': r.change_detected,
        'alert_level': r.semantic.alert_level if r.semantic else None,
        'severity_score': r.semantic.severity_score if r.semantic else None,
        'summary': r.semantic.summary if r.semantic else None,
        'analysis_id': r.analysis_id,
        'truncated': truncated,
    }
    if truncated:
        out['upgrade_hint'] = sig_check['upgrade_hint']
        out['truncated_to'] = len(sig)
    return out


def monitor(client: AlphaInfo,
            signal: Sequence[float],
            plan: dict[str, Any],
            window_size: int = 200,
            step: int = 50,
            sampling_rate: float = 10.0,
            domain: str = 'generic',
            baseline: Sequence[float] | None = None,
            score_threshold: float = 0.5) -> dict[str, Any]:
    """Native sliding-window monitoring. Wraps analyze_windowed.

    Plan-aware: estimates window count, caps to recommended max for the plan,
    enlarges step if needed.
    """
    # Truncate signal first
    sig_check = adapt(plan, 'signal_length', len(signal))
    sig = list(signal)[:sig_check['adjusted_size']]

    # Estimate window count
    n_windows_requested = max(1, (len(sig) - window_size) // step + 1)
    win_check = adapt(plan, 'windows', n_windows_requested)
    if not win_check['within_cap']:
        # Increase step to reduce window count to cap
        new_step = max(step, (len(sig) - window_size) // win_check['adjusted_size'])
        step = new_step

    result = client.analyze_windowed(
        signal=sig,
        window_size=window_size,
        step=step,
        sampling_rate=sampling_rate,
        domain=domain,
        baseline=list(baseline) if baseline else None,
    )

    windows = result.get('windows', [])
    alerts = []
    for w in windows:
        if isinstance(w, tuple) and len(w) >= 3:
            start, end, score = w[0], w[1], w[2]
        elif isinstance(w, dict):
            start = w.get('start')
            end = w.get('end')
            score = w.get('structural_score') or w.get('score')
        else:
            continue
        if score is not None and score < score_threshold:
            alerts.append({'start': start, 'end': end, 'score': score})

    def _norm(w: Any) -> dict | None:
        if isinstance(w, tuple) and len(w) >= 3:
            return {'start': w[0], 'end': w[1], 'score': w[2]}
        if isinstance(w, dict):
            return w
        return None

    out = {
        'windows': windows,
        'worst_window': _norm(result.get('worst_window')),
        'best_window': _norm(result.get('best_window')),
        'alerts': alerts,
        'n_windows': len(windows),
        'n_alerts': len(alerts),
        'effective_step': step,
        'truncated': not sig_check['within_cap'],
    }
    if not win_check['within_cap']:
        out['upgrade_hint'] = win_check['upgrade_hint']
    return out


def multi_channel(client: AlphaInfo,
                  channels: dict[str, Sequence[float]],
                  baselines: dict[str, Sequence[float]],
                  plan: dict[str, Any],
                  sampling_rate: float = 10.0,
                  domain: str = 'sensors') -> dict[str, Any]:
    """Multi-channel fault isolation (canal delator). Wraps analyze_vector.

    Plan-aware: caps to max_channels for the plan.
    """
    assert set(channels.keys()) == set(baselines.keys()), \
        "channel names must match between channels and baselines"

    n_requested = len(channels)
    ch_check = adapt(plan, 'channels', n_requested)

    if not ch_check['within_cap']:
        # Keep first N (could be smarter — keep most variable, etc.)
        keep = list(channels.keys())[:ch_check['adjusted_size']]
        channels = {k: channels[k] for k in keep}
        baselines = {k: baselines[k] for k in keep}

    r = client.analyze_vector(
        channels={k: list(v) for k, v in channels.items()},
        baselines={k: list(v) for k, v in baselines.items()},
        sampling_rate=sampling_rate,
        domain=domain,
        include_semantic=True,
    )

    ch_scores = {name: ch.structural_score
                 for name, ch in r.channels.items() if ch.success}
    delator = min(ch_scores, key=ch_scores.get) if ch_scores else None

    out = {
        'aggregated_score': r.structural_score,
        'alert_level': r.semantic.alert_level if r.semantic else None,
        'severity_score': r.semantic.severity_score if r.semantic else None,
        'recommended_action': r.semantic.recommended_action if r.semantic else None,
        'delator_channel': delator,
        'delator_score': ch_scores[delator] if delator else None,
        'per_channel_scores': ch_scores,
        'analysis_id': r.analysis_id,
        'channels_analyzed': len(ch_scores),
        'channels_dropped': max(0, n_requested - len(ch_scores)),
    }
    if not ch_check['within_cap']:
        out['upgrade_hint'] = ch_check['upgrade_hint']
    return out


def auto_compare(client: AlphaInfo,
                 signal: Sequence[float],
                 baseline: Sequence[float],
                 plan: dict[str, Any],
                 sampling_rate: float = 10.0) -> dict[str, Any]:
    """Compare with auto-domain inference. Wraps analyze_auto."""
    sig_check = adapt(plan, 'signal_length', len(signal))
    sig = list(signal)[:sig_check['adjusted_size']]
    base = list(baseline)[:sig_check['adjusted_size']]

    r = client.analyze_auto(
        signal=sig,
        baseline=base,
        sampling_rate=sampling_rate,
        include_semantic=True,
    )
    di = getattr(r, 'domain_inference', None) or {}
    out = {
        'score': r.structural_score,
        'confidence_band': r.confidence_band,
        'alert_level': r.semantic.alert_level if r.semantic else None,
        'severity_score': r.semantic.severity_score if r.semantic else None,
        'summary': r.semantic.summary if r.semantic else None,
        'inferred_domain': di.get('inferred') if isinstance(di, dict) else None,
        'domain_confidence': di.get('confidence') if isinstance(di, dict) else None,
        'domain_reasoning': di.get('reasoning') if isinstance(di, dict) else None,
        'analysis_id': r.analysis_id,
        'truncated': not sig_check['within_cap'],
    }
    if not sig_check['within_cap']:
        out['upgrade_hint'] = sig_check['upgrade_hint']
    return out


def compare(client: AlphaInfo,
            signal: Sequence[float],
            baseline: Sequence[float],
            plan: dict[str, Any],
            sampling_rate: float = 10.0,
            domain: str = 'generic',
            intent: str = 'regime_change') -> dict[str, Any]:
    """Profile comparison. Wraps client.compare()."""
    sig_check = adapt(plan, 'signal_length', max(len(signal), len(baseline)))
    cap = sig_check['adjusted_size']
    sig = list(signal)[:cap]
    base = list(baseline)[:cap]

    r = client.compare(
        signal=sig, baseline=base,
        sampling_rate=sampling_rate,
        domain=domain, intent=intent,
        include_semantic=True,
    )
    out = {
        'score': r.structural_score,
        'confidence_band': r.confidence_band,
        'change_detected': r.change_detected,
        'alert_level': r.semantic.alert_level if r.semantic else None,
        'severity_score': r.semantic.severity_score if r.semantic else None,
        'summary': r.semantic.summary if r.semantic else None,
        'analysis_id': r.analysis_id,
        'truncated': not sig_check['within_cap'],
    }
    if not sig_check['within_cap']:
        out['upgrade_hint'] = sig_check['upgrade_hint']
    return out


def fingerprint(client: AlphaInfo,
                signal: Sequence[float],
                plan: dict[str, Any],
                sampling_rate: float = 10.0,
                domain: str = 'generic',
                baseline: Sequence[float] | None = None) -> dict[str, Any]:
    """Get the 5-D structural fingerprint."""
    sig_check = adapt(plan, 'signal_length', len(signal))
    sig = list(signal)[:sig_check['adjusted_size']]
    base = list(baseline)[:sig_check['adjusted_size']] if baseline else None

    r = client.fingerprint(
        signal=sig,
        sampling_rate=sampling_rate,
        domain=domain,
        baseline=base,
    )
    return {
        'fingerprint': r.fingerprint if hasattr(r, 'fingerprint') else None,
        'available': getattr(r, 'available', None),
        'reason': getattr(r, 'reason', None),
        'truncated': not sig_check['within_cap'],
    }


def safe_call(fn, *args, **kwargs) -> dict[str, Any]:
    """Wrap any helper call with rate-limit-aware retry/skip.

    Returns dict with 'success' bool and 'result' or 'error'.
    Useful when iterating over many signals.
    """
    try:
        return {'success': True, 'result': fn(*args, **kwargs)}
    except RateLimitError as e:
        retry = getattr(e, 'retry_after', None)
        return {'success': False, 'error': 'rate_limited', 'retry_after': retry}
    except APIError as e:
        return {'success': False, 'error': str(e), 'type': 'api'}
    except Exception as e:
        return {'success': False, 'error': str(e), 'type': type(e).__name__}
