#!/usr/bin/env bash
# Run on the Pi, in /opt/curator. Safe to run again after each update.
# It needs sudo for the systemd steps only. See docs/DEPLOY.md.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || {
  echo "Curator needs Python 3.11 or newer." >&2; exit 1; }

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating the virtual environment..."
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

mkdir -p data config
if [[ ! -f config/local.toml ]]; then
  cp deploy/pi.toml config/local.toml
  echo "Created config/local.toml from deploy/pi.toml. Check the addresses in it."
fi
if [[ -f config/token.txt ]]; then
  chmod 600 config/token.txt
else
  echo "Note: config/token.txt is missing. The TV asks for Allow on the first connection."
fi

sudo install -m 644 deploy/curator.service /etc/systemd/system/curator.service
sudo systemctl daemon-reload
sudo systemctl enable curator
sudo systemctl restart curator
sleep 2
systemctl --no-pager --lines=5 status curator || true
echo "Curator is installed in $ROOT."
