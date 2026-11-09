#!/usr/bin/env bash
# Run on the Mac. Copies the Curator code to the Pi. See docs/DEPLOY.md.
#
#   deploy/push.sh            copy the code only
#   deploy/push.sh --token    also copy config/token.txt (the TV pairing token)
#
# It never copies config/local.toml, data/, .venv/ or git files.
set -euo pipefail

HOST="${CURATOR_PI:-curator-pi}"   # the SSH alias in ~/.ssh/config
DEST="/opt/curator"
cd "$(dirname "$0")/.."

ssh "$HOST" "test -d $DEST && test -w $DEST" || {
  echo "$DEST is missing or not writable on $HOST. Run the first-time steps in docs/DEPLOY.md." >&2
  exit 1
}

rsync -av --delete \
  --exclude '.git/' --exclude '.venv/' --exclude 'data/' --exclude '__pycache__/' \
  --exclude '.pytest_cache/' --exclude 'config/local.toml' --exclude 'config/token.txt' \
  --exclude '*.token' --exclude '.DS_Store' --exclude '.claude/' \
  ./ "$HOST:$DEST/"

if [[ "${1:-}" == "--token" ]]; then
  test -s config/token.txt || { echo "config/token.txt is missing. Pair with the TV first." >&2; exit 1; }
  scp -p config/token.txt "$HOST:$DEST/config/token.txt"
  ssh "$HOST" "chmod 600 $DEST/config/token.txt"
  echo "Copied the TV token."
fi

echo "Done. Next, on the Pi: $DEST/deploy/install.sh"
