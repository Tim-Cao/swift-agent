#!/usr/bin/env zsh
# verify-minimax.sh — silently collect MINIMAX_API_KEY, probe the Anthropic-
# compatible endpoint, and report whether the credential works.
#
# Usage: ./verify-minimax.sh [model-id]
#   model-id defaults to MiniMax-M3.
#
# Exit codes:
#   0 — 200 OK (key accepted by minimax)
#   2 — 401 (key rejected — rotate it)
#   3 — 402 (insufficient balance — top up)
#   1 — any other status / transport error
#
# The key is held only in this process; nothing is written to disk or shell
# history. Persist it separately via ~/.zshrc or the macOS Keychain.

set -euo pipefail

MODEL="${1:-MiniMax-M3}"
BASE_URL="https://api.minimaxi.com/anthropic"

print_header() {
  print -r -- "▶ $1"
}

print_header "Reading MINIMAX_API_KEY from stdin (silent, no echo, no history)..."
IFS= read -rs MINIMAX_API_KEY
[[ -n "$MINIMAX_API_KEY" ]] || { print -r -- "✗ empty key — aborting"; exit 1 }
print -r -- "  (received ${#MINIMAX_API_KEY} characters)"
export MINIMAX_API_KEY

REQUEST_BODY=$(printf '{"model":"%s","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}' "$MODEL")

print_header "POST $BASE_URL/v1/messages  model=$MODEL"
RAW=$(curl -sS --max-time 30 \
  -H "x-api-key: $MINIMAX_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d "$REQUEST_BODY" \
  -o /tmp/verify-minimax.body \
  -w "%{http_code}" \
  "$BASE_URL/v1/messages") || {
  print -r -- "✗ curl failed — check network / DNS"
  unset MINIMAX_API_KEY
  exit 1
}

# Scrub from process env before printing anything else.
unset MINIMAX_API_KEY

STATUS="$RAW"
BODY=$(head -c 800 /tmp/verify-minimax.body 2>/dev/null || true)
rm -f /tmp/verify-minimax.body

print -r -- "  HTTP $STATUS"
[[ -n "$BODY" ]] && print -r -- "  body (first 800B): $BODY"

case "$STATUS" in
  200)
    print_header "✓ key accepted by minimax"
    print -r -- ""
    print -r -- "Next:"
    print -r -- "  1. Persist the key (still unset in this shell):"
    print -r -- "       %q — see earlier message for the safe snippet."
    print -r -- "  2. Open the dsh Web UI and send any message; if it still says"
    print -r -- "     'API key is invalid', restart dsh so it re-reads settings.yaml."
    exit 0
    ;;
  401)
    print_header "✗ 401 — key rejected"
    print -r -- "  Rotate the key at the minimax console, then re-run this script."
    exit 2
    ;;
  402)
    print_header "✗ 402 — insufficient balance"
    print -r -- "  Top up at the minimax console, then re-run this script."
    exit 3
    ;;
  *)
    print -r -- "✗ unexpected status $STATUS"
    exit 1
    ;;
esac