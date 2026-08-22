#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/xauusd-scalper-x10}"
SERVICE_UNIT="/etc/systemd/system/xauusd-data-update.service"
TIMER_UNIT="/etc/systemd/system/xauusd-data-update.timer"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

if [[ ! -x "$APP_DIR/scripts/update_xauusd_data.sh" ]]; then
  chmod +x "$APP_DIR/scripts/update_xauusd_data.sh"
fi

cat > "$SERVICE_UNIT" <<EOF
[Unit]
Description=Refresh XAUUSD M1 historical data
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$APP_DIR/scripts/update_xauusd_data.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=6
EOF

cat > "$TIMER_UNIT" <<'EOF'
[Unit]
Description=Daily XAUUSD data refresh timer

[Timer]
OnCalendar=*-*-* 01:15:00 UTC
RandomizedDelaySec=900
Persistent=true
Unit=xauusd-data-update.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now xauusd-data-update.timer
systemctl --no-pager --full status xauusd-data-update.timer || true
systemctl list-timers xauusd-data-update.timer --no-pager
