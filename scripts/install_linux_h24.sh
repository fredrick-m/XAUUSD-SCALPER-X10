#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/xauusd-scalper-x10}"
APP_USER="${APP_USER:-xauusd}"
REPO_URL="${REPO_URL:-https://github.com/fredrick-m/XAUUSD-SCALPER-X10.git}"
BRANCH="${BRANCH:-audit/x10-500}"
SERVICE_NAME="xauusd-scalper-x10"
ENV_FILE="/etc/${SERVICE_NAME}.env"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git python3 python3-venv python3-pip build-essential curl ca-certificates

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip wheel setuptools
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements-linux.txt"

mkdir -p "$APP_DIR/data/raw" "$APP_DIR/data/processed" "$APP_DIR/logs"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
# Optional but recommended for autonomous LLM agents.
# Add the value securely, then restart the service:
# ANTHROPIC_API_KEY=...
PYTHONUNBUFFERED=1
EOF
  chmod 600 "$ENV_FILE"
fi

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=XAUUSD-SCALPER-X10 24/7 Research Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/start.py
Restart=always
RestartSec=10
TimeoutStopSec=30
KillSignal=SIGTERM
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

sleep 2
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo
echo "Installed: $APP_DIR"
echo "Branch:    $BRANCH"
echo "Service:   $SERVICE_NAME"
echo "Logs:      journalctl -u $SERVICE_NAME -f"
echo "Status:    systemctl status $SERVICE_NAME"
echo "Restart:   systemctl restart $SERVICE_NAME"
echo "Research runs 24/7. MT5 execution remains unavailable/locked on Linux."
