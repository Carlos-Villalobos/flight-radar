#!/usr/bin/env bash
# Installs (or removes) the flight-radar timer on a Linux server with systemd.
#   ./scripts/install_systemd.sh             → price check 3 times a day
#   ./scripts/install_systemd.sh uninstall   → disable and remove
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
UNITS=(flight-radar-check.service flight-radar-check.timer)

if [[ "${1:-}" == "uninstall" ]]; then
  sudo systemctl disable --now flight-radar-check.timer 2>/dev/null || true
  for unit in "${UNITS[@]}"; do sudo rm -f "/etc/systemd/system/$unit"; done
  sudo systemctl daemon-reload
  echo "Uninstalled."
  exit 0
fi

[[ -x "$DIR/.venv/bin/python" ]] || { echo "Missing $DIR/.venv: install the project first"; exit 1; }
[[ -f "$DIR/.env" ]] || { echo "Missing $DIR/.env"; exit 1; }
[[ -f "$DIR/config/trip.yaml" ]] || { echo "Missing $DIR/config/trip.yaml (copy config/trip.example.yaml)"; exit 1; }
# Only checks that the variables have a value; never prints them
for var in IMAP_USER IMAP_PASSWORD TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
  grep -qE "^$var=.+" "$DIR/.env" || { echo "Missing $var in .env"; exit 1; }
done

for unit in "${UNITS[@]}"; do
  sed "s|__DIR__|$DIR|g; s|__USER__|$USER_NAME|g" "$DIR/deploy/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo systemd-analyze verify "${UNITS[@]/#//etc/systemd/system/}"
sudo systemctl daemon-reload
sudo systemctl enable --now flight-radar-check.timer
systemctl list-timers 'flight-radar-*' --no-pager
echo
echo "Logs: journalctl -u flight-radar-check.service -n 50 --no-pager"
