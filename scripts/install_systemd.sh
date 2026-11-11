#!/usr/bin/env bash
# Instala (o quita) el timer de vuelos-baratos en un servidor Linux con systemd (la EC2).
#   ./scripts/install_systemd.sh             → revisión de precios 3 veces al día
#   ./scripts/install_systemd.sh uninstall   → desactiva y borra
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
UNITS=(vuelos-revisar.service vuelos-revisar.timer)

if [[ "${1:-}" == "uninstall" ]]; then
  sudo systemctl disable --now vuelos-revisar.timer 2>/dev/null || true
  for unit in "${UNITS[@]}"; do sudo rm -f "/etc/systemd/system/$unit"; done
  sudo systemctl daemon-reload
  echo "Desinstalado."
  exit 0
fi

[[ -x "$DIR/.venv/bin/python" ]] || { echo "Falta $DIR/.venv: instala el proyecto primero"; exit 1; }
[[ -f "$DIR/.env" ]] || { echo "Falta $DIR/.env"; exit 1; }
# Solo comprueba que las variables tengan valor; nunca las imprime
for var in IMAP_USER IMAP_PASSWORD TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
  grep -qE "^$var=.+" "$DIR/.env" || { echo "Falta $var en .env"; exit 1; }
done

for unit in "${UNITS[@]}"; do
  sed "s|__DIR__|$DIR|g; s|__USER__|$USER_NAME|g" "$DIR/deploy/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo systemd-analyze verify "${UNITS[@]/#//etc/systemd/system/}"
sudo systemctl daemon-reload
sudo systemctl enable --now vuelos-revisar.timer
systemctl list-timers 'vuelos-*' --no-pager
echo
echo "Logs: journalctl -u vuelos-revisar.service -n 50 --no-pager"
