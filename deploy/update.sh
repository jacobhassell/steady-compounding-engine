#!/usr/bin/env bash
#
# One-command update for an existing Mastermind VM deployment.
#
#   sudo bash deploy/update.sh
#
# This pulls the latest code, re-runs the idempotent bootstrap (refreshes
# dependencies and the systemd unit), and restarts the service.

set -euo pipefail

APP_DIR="/opt/mastermind"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this with sudo: sudo bash deploy/update.sh" >&2
  exit 1
fi

cd "${APP_DIR}"

echo "==> Pulling latest code"
sudo -u mastermind git pull

echo "==> Re-running bootstrap"
bash "${APP_DIR}/deploy/setup.sh"

echo "==> Restarting service"
systemctl restart mastermind

cat <<EOF

Update complete. The bot is restarting.

Watch live logs:
  journalctl -u mastermind -f

Check status:
  systemctl status mastermind

View recent trade history:
  sudo -u mastermind ${APP_DIR}/.venv/bin/python -m project.main trades --limit 50

EOF
