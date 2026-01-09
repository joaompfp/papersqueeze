#!/usr/bin/env bash
# PaperSqueeze virtual environment setup
# Run this INSIDE the Paperless container:
#   docker exec paperless-ngx bash -c "cd /usr/src/paperless/scripts/papersqueeze && ./setup_venv.sh"

set -e

RUN_DIR=$( dirname -- "$( readlink -f -- "$0"; )"; )
cd "$RUN_DIR"

echo -n "Setting up virtual environment..."
python3 -m venv --system-site-packages .venv
echo "OK"

echo "Installing dependencies..."
source .venv/bin/activate
pip install --quiet -r requirements.txt

echo ""
echo "PaperSqueeze setup complete!"
echo "Venv location: $RUN_DIR/.venv"
