#!/bin/bash
# PaperSqueeze post-consume hook for Paperless-ngx
#
# Environment variables provided by Paperless:
#   DOCUMENT_ID - The ID of the newly consumed document
#   DOCUMENT_FILE_NAME - Original filename
#   DOCUMENT_CREATED - Creation timestamp
#   DOCUMENT_ADDED - Added timestamp
#
# To enable: Set PAPERLESS_POST_CONSUME_SCRIPT=/usr/src/paperless/scripts/post_consume.sh

set -u

SCRIPT_DIR="/usr/src/paperless/scripts"
VENV_DIR="$SCRIPT_DIR/papersqueeze/.venv"
LOG_FILE="$SCRIPT_DIR/papersqueeze.log"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "=== PaperSqueeze post_consume.sh called ==="
log "Args: $*"
log "DOCUMENT_ID env: ${DOCUMENT_ID:-NOT_SET}"
log "PWD: $(pwd)"
log "PAPERLESS_API_URL: ${PAPERLESS_API_URL:-NOT_SET}"

DOC_ID="${DOCUMENT_ID:-${1:-}}"
DOC_NAME="${DOCUMENT_FILE_NAME:-${2:-unknown}}"

# Check if document ID is provided
if [ -z "$DOC_ID" ]; then
    log "ERROR: DOCUMENT_ID not set"
    exit 1
fi

log "Processing document $DOC_ID ($DOC_NAME)"

# Auto-setup venv if missing
if [ ! -f "$VENV_DIR/bin/python" ]; then
    log "Virtual environment not found, setting up..."
    cd "$SCRIPT_DIR/papersqueeze"
    python3 -m venv --system-site-packages .venv >> "$LOG_FILE" 2>&1
    "$VENV_DIR/bin/pip" install --quiet -r requirements.txt >> "$LOG_FILE" 2>&1
    if [ ! -f "$VENV_DIR/bin/python" ]; then
        log "ERROR: Failed to create virtual environment"
        exit 0  # Don't fail the document consumption
    fi
    log "Virtual environment created successfully"
fi

# Activate venv and run PaperSqueeze
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR/papersqueeze/src:${PYTHONPATH:-}"

# Run PaperSqueeze process command
"$VENV_DIR/bin/python" -m papersqueeze process "$DOC_ID" >> "$LOG_FILE" 2>&1

RESULT=$?
if [ $RESULT -eq 0 ]; then
    log "Document $DOC_ID processed successfully"
else
    log "ERROR: Document $DOC_ID processing failed (exit code: $RESULT)"
fi

exit 0  # Always succeed to not block document consumption
