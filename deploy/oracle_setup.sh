#!/bin/bash
# ============================================================
# oracle_setup.sh
# Run ONCE on a fresh Oracle Cloud Free Tier Ubuntu instance.
# Sets up Python, the app, and a systemd service that starts
# automatically on boot and restarts on crash.
#
# Usage:
#   ssh ubuntu@<your-oracle-ip>
#   curl -O https://raw.githubusercontent.com/<you>/lucid-ai-trader/main/deploy/oracle_setup.sh
#   chmod +x oracle_setup.sh && ./oracle_setup.sh
# ============================================================
set -e

APP_DIR="/home/ubuntu/lucid-ai-trader"
SERVICE_NAME="lucid-ai-trader"
PORT=8080

echo "=== [1/6] System update ==="
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl

echo "=== [2/6] Clone / update repo ==="
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR" && git pull
else
  git clone https://github.com/<YOUR_GITHUB_USERNAME>/lucid-ai-trader.git "$APP_DIR"
fi

echo "=== [3/6] Python virtual environment ==="
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install ib_insync  # IBKR support

echo "=== [4/6] Copy .env if missing ==="
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo ""
  echo "  *** ACTION REQUIRED ***"
  echo "  Edit $APP_DIR/.env and fill in your API keys."
  echo "  Then re-run: sudo systemctl restart $SERVICE_NAME"
  echo ""
fi

echo "=== [5/6] Open firewall port $PORT ==="
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport $PORT -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

echo "=== [6/6] Install systemd service ==="
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null <<EOF
[Unit]
Description=Lucid AI Trader
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python main.py --mode paper
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo ""
echo "========================================================"
echo "  Lucid AI Trader is running at http://$(curl -s ifconfig.me):$PORT"
echo ""
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  Restart: sudo systemctl restart $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "========================================================"
