#!/usr/bin/env bash
# AlphaInfo Claude Skill — one-line installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<org>/alphainfo-claude-skill/main/install.sh | sh
#
# What it does:
#   1. Clones the skill into ~/.claude/skills/alphainfo
#   2. Installs Python dependencies (alphainfo SDK, optional yfinance/wfdb for examples)
#   3. Detects existing API key in env; prompts user to register if missing
#   4. Opens browser to alphainfo.io/register?ref=claude-skill if no key found

set -euo pipefail

REPO_URL="${ALPHAINFO_SKILL_REPO:-https://github.com/alphainfo-io/claude-skill}"
INSTALL_DIR="${HOME}/.claude/skills/alphainfo"
ENV_DIR="${HOME}/.alphainfo"
ENV_FILE="${ENV_DIR}/.env"
REGISTER_URL="https://www.alphainfo.io/register?ref=claude-skill"
DOCS_URL="https://www.alphainfo.io/v1/guide"

C_GREEN='\033[0;32m'
C_BLUE='\033[0;34m'
C_YELLOW='\033[1;33m'
C_RED='\033[0;31m'
C_RESET='\033[0m'
C_BOLD='\033[1m'

info()  { printf "${C_BLUE}ℹ${C_RESET}  %s\n" "$1"; }
ok()    { printf "${C_GREEN}✓${C_RESET}  %s\n" "$1"; }
warn()  { printf "${C_YELLOW}⚠${C_RESET}  %s\n" "$1"; }
err()   { printf "${C_RED}✗${C_RESET}  %s\n" "$1" >&2; }
title() { printf "\n${C_BOLD}%s${C_RESET}\n" "$1"; }

title "AlphaInfo Claude Skill installer"

# ── 1. Check prerequisites ────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { err "python3 not found. Install Python 3.10+."; exit 1; }
command -v git >/dev/null 2>&1 || { err "git not found. Install git first."; exit 1; }

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "python3 ${PY_VER}"
ok "git $(git --version | awk '{print $3}')"

# ── 2. Clone or update skill ──────────────────────────────────────
title "Installing skill"
mkdir -p "$(dirname "${INSTALL_DIR}")"

if [ -d "${INSTALL_DIR}/.git" ]; then
    info "Existing install found at ${INSTALL_DIR} — pulling latest..."
    (cd "${INSTALL_DIR}" && git pull --quiet --ff-only) && ok "Updated"
elif [ -d "${INSTALL_DIR}" ]; then
    warn "${INSTALL_DIR} exists but is not a git checkout."
    warn "Move it aside or delete it, then re-run installer."
    exit 1
else
    info "Cloning ${REPO_URL} → ${INSTALL_DIR}"
    git clone --quiet --depth 1 "${REPO_URL}" "${INSTALL_DIR}" && ok "Cloned"
fi

# ── 3. Python dependencies ────────────────────────────────────────
title "Installing Python dependencies"
PIP_FLAGS=""
if python3 -c "import sys; sys.exit(0 if hasattr(sys,'base_prefix') and sys.base_prefix==sys.prefix else 1)" 2>/dev/null; then
    # Not in venv — system Python: use --user --break-system-packages on PEP 668 systems
    PIP_FLAGS="--user --break-system-packages"
    info "Using --user --break-system-packages (system Python)"
fi

python3 -m pip install ${PIP_FLAGS} --quiet --upgrade alphainfo && ok "alphainfo SDK installed"

# Optional deps for examples
read -p "$(printf "${C_BLUE}?${C_RESET}  Install optional packages for real-data examples (yfinance, wfdb)? [Y/n] ")" -n 1 -r REPLY
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    python3 -m pip install ${PIP_FLAGS} --quiet yfinance wfdb numpy && ok "Example deps installed"
fi

# ── 4. API key check ──────────────────────────────────────────────
title "Checking API key"

KEY_FOUND=""
if [ -n "${ALPHAINFO_API_KEY:-}" ]; then
    KEY_FOUND="env (ALPHAINFO_API_KEY)"
elif [ -f "${ENV_FILE}" ] && grep -q "^ALPHAINFO_API_KEY=" "${ENV_FILE}"; then
    KEY_FOUND="${ENV_FILE}"
elif [ -f "./.env" ] && grep -q "^ALPHAINFO_API_KEY=" "./.env"; then
    KEY_FOUND="./.env"
fi

if [ -n "${KEY_FOUND}" ]; then
    ok "API key found in ${KEY_FOUND}"
else
    warn "No API key configured."
    echo
    cat <<EOF
   Get a free key (50 analyses/month, no card required):

      ${REGISTER_URL}

   Then save it to:

      mkdir -p ${ENV_DIR}
      echo 'ALPHAINFO_API_KEY=ai_...' > ${ENV_FILE}

   Or set it in your shell:

      export ALPHAINFO_API_KEY=ai_...
EOF

    # Try to open the registration page in a browser (best-effort)
    if command -v open >/dev/null 2>&1; then
        read -p "$(printf "\n${C_BLUE}?${C_RESET}  Open registration page now? [Y/n] ")" -n 1 -r REPLY2
        echo
        [[ ! $REPLY2 =~ ^[Nn]$ ]] && open "${REGISTER_URL}" 2>/dev/null
    elif command -v xdg-open >/dev/null 2>&1; then
        read -p "$(printf "\n${C_BLUE}?${C_RESET}  Open registration page now? [Y/n] ")" -n 1 -r REPLY2
        echo
        [[ ! $REPLY2 =~ ^[Nn]$ ]] && xdg-open "${REGISTER_URL}" 2>/dev/null
    fi
fi

# ── 5. Done ───────────────────────────────────────────────────────
title "All set"
cat <<EOF
The AlphaInfo skill is now installed at:
   ${INSTALL_DIR}

Next steps:
   1. (Open Claude Code in any project)
   2. Ask: "analyze this signal" or "detect anomaly in [data]"
      → Claude will route through the AlphaInfo skill automatically.

Try a real-data example now:
   cd ${INSTALL_DIR}
   python3 examples/server_metrics.py
   python3 examples/multi_sensor.py

Docs:    ${DOCS_URL}
Pricing: https://www.alphainfo.io/pricing?ref=claude-skill

EOF
