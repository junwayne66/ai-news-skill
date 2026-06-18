#!/usr/bin/env bash
# Print resolved SSH HostName for an alias (use on operator Mac with ~/.ssh/config).
set -euo pipefail
ALIAS="${1:-remote-spark}"
ssh -G "$ALIAS" 2>/dev/null | awk '/^hostname /{print $2; exit}'
ssh -G "$ALIAS" 2>/dev/null | awk '/^user /{print $2; exit}'
