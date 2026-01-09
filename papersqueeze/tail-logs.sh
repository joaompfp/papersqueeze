#!/bin/bash
# Tail container logs for debugging
# Usage: ./tail-logs.sh [paperless|postgres|all] [lines]

CONTAINER="${1:-paperless}"
LINES="${2:-50}"

case "$CONTAINER" in
    paperless|p)
        docker logs paperless-ngx --tail "$LINES" -f
        ;;
    postgres|pg|db)
        docker logs office-postgres-db --tail "$LINES" -f
        ;;
    all|a)
        echo "=== PAPERLESS ===" && docker logs paperless-ngx --tail "$LINES"
        echo ""
        echo "=== POSTGRES ===" && docker logs office-postgres-db --tail "$LINES"
        ;;
    *)
        echo "Usage: $0 [paperless|postgres|all] [lines]"
        exit 1
        ;;
esac
