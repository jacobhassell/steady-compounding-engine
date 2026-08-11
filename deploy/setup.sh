#!/usr/bin/env bash
#
# One-shot bootstrap for a fresh Debian/Ubuntu Google Cloud VM.
#
#   sudo bash deploy/setup.sh
#
# Idempotent: safe to re-run after a git pull to refresh dependencies.

set -euo pipefail

APP_DIR="/opt/mastermind"
APP_USER="mastermind"
VENV="${APP_DIR}/.venv"
SERVICE="mastermind"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this with sudo: sudo bash deploy/setup.sh" >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/project/main.py" ]]; then
  echo "Expected the repository at ${APP_DIR} (project/main.py not found)." >&2
  echo "Clone it first:  sudo git clone <repo-url> ${APP_DIR}" >&2
  exit 1
fi

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git ca-certificates

echo "==> Setting the clock to UTC (session logic assumes UTC)"
timedatectl set-timezone UTC || echo "    (could not set timezone; continuing)"

echo "==> Creating the service account"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "==> Preparing state and report directories"
mkdir -p "${APP_DIR}/.state" "${APP_DIR}/reports"

echo "==> Building the virtualenv"
if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/python" -m pip install --quiet --upgrade pip
"${VENV}/bin/python" -m pip install --quiet -r "${APP_DIR}/project/requirements.txt"

echo "==> Verifying the engine imports"
cd "${APP_DIR}"
"${VENV}/bin/python" -c "from project.paper.trader import PaperTrader; print('    engine ok')"

echo "==> Fixing ownership"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> Installing the systemd unit"
install -m 0644 "${APP_DIR}/deploy/mastermind.service" "/etc/systemd/system/${SERVICE}.service"
systemctl daemon-reload

cat <<EOF

Bootstrap complete.

Smoke-test one scan cycle before going continuous:
  sudo -u ${APP_USER} ${VENV}/bin/python -m project.main scan

Then start the bot:
  sudo systemctl enable --now ${SERVICE}
  journalctl -u ${SERVICE} -f

EOF
