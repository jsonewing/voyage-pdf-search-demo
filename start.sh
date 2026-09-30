#!/usr/bin/env bash
# Compatibility alias. run.sh is the canonical self-contained launcher.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run.sh" "$@"
