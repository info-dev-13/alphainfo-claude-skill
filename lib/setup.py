"""
AlphaInfo skill setup — finds API key and onboards the user if missing.

The onboarding message includes a registration link. Surface it to the user
verbatim when no key is found.
"""
from __future__ import annotations
import os
from pathlib import Path
from alphainfo import AlphaInfo
from alphainfo.exceptions import AuthError


REGISTER_URL = 'https://www.alphainfo.io/register?ref=claude-skill'
PRICING_URL = 'https://www.alphainfo.io/pricing?ref=claude-skill'
DOCS_URL = 'https://www.alphainfo.io/v1/guide'


ONBOARDING_MESSAGE = f"""
╔══════════════════════════════════════════════════════════════╗
║  AlphaInfo skill is ready — but needs an API key             ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Get a free key (50 analyses/month, no card):             ║
║     → {REGISTER_URL}
║                                                              ║
║  2. Add it to one of:                                        ║
║     • ~/.alphainfo/.env  (recommended, persistent)           ║
║         echo 'ALPHAINFO_API_KEY=ai_...' > ~/.alphainfo/.env  ║
║     • Shell env var:                                         ║
║         export ALPHAINFO_API_KEY=ai_...                      ║
║                                                              ║
║  3. Run again — Claude will pick it up automatically.        ║
║                                                              ║
║  Want more? Starter $49/mo unlocks probes + 5K analyses.     ║
║     → {PRICING_URL}
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


class APIKeyMissing(RuntimeError):
    """Raised when no API key can be found. Message contains onboarding."""


def find_key(path: str | None = None) -> str:
    """Locate AlphaInfo API key.

    Search order:
      1. Given path
      2. ~/.alphainfo/.env  (recommended persistent location)
      3. ./.env  (project-local)
      4. ALPHAINFO_API_KEY env var

    Raises APIKeyMissing with onboarding message if nothing found.
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(Path.home() / '.alphainfo' / '.env')
    candidates.append(Path.cwd() / '.env')

    for p in candidates:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    if 'ALPHAINFO' in line.upper() and '=' in line:
                        val = line.split('=', 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
                # Fallback to first non-comment line
                f.seek(0)
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    if '=' in line:
                        val = line.split('=', 1)[1].strip().strip('"').strip("'")
                        if val.startswith('ai_'):
                            return val

    env = os.environ.get('ALPHAINFO_API_KEY')
    if env:
        return env

    raise APIKeyMissing(ONBOARDING_MESSAGE)


def setup(key_path: str | None = None,
          check_health: bool = True,
          check_analyze: bool = False) -> AlphaInfo:
    """Initialize AlphaInfo client with clear error UX.

    Args:
        key_path: explicit path to .env file
        check_health: verify /v1/health (free, no quota)
        check_analyze: also send a tiny test analyze() to detect quota
                       exhaustion (the SDK's AuthError message is misleading
                       in that case — we translate)

    Raises APIKeyMissing (onboarding link) or RuntimeError (clear quota message).
    """
    key = find_key(key_path)
    client = AlphaInfo(api_key=key)

    if check_health:
        try:
            h = client.health()
            if h.status != 'healthy':
                raise RuntimeError(
                    f"AlphaInfo /health returned status='{h.status}': {h.message}\n"
                    f"  Service status: https://www.alphainfo.io/status"
                )
        except AuthError:
            raise RuntimeError(
                f"API key authentication failed (key: {key[:6]}...).\n"
                f"  Get a fresh key: {REGISTER_URL}"
            )

    if check_analyze:
        ok, hint = _probe_analyze(client)
        if not ok:
            raise RuntimeError(hint)

    return client


def _probe_analyze(client: AlphaInfo) -> tuple[bool, str | None]:
    """Send a tiny analyze() to verify the key works for paid endpoints.

    The SDK's AuthError on quota-exhausted accounts is misleading; we translate.
    """
    tiny_signal = [float(i % 7) for i in range(50)]
    tiny_baseline = [float((i + 1) % 7) for i in range(50)]
    try:
        client.analyze(signal=tiny_signal, baseline=tiny_baseline,
                       sampling_rate=1.0)
        return True, None
    except AuthError:
        return False, (
            f"AlphaInfo authenticated /health but /analyze fails — almost\n"
            f"certainly QUOTA EXHAUSTED on the free tier (the SDK's auth error\n"
            f"message is misleading in this case).\n\n"
            f"  Check usage / upgrade: {PRICING_URL}"
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def show_onboarding() -> None:
    """Print onboarding message. Useful for first-run scripts."""
    print(ONBOARDING_MESSAGE)
