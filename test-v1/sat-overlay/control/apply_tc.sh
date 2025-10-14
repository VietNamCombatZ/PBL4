#!/usr/bin/env bash
# Thêm netem cho vệ tinh (chạy bên trong container)
# Ví dụ: delay 300ms ± 30ms, loss 0.5%, rate 20 Mbit
set -euo pipefail

DEV="${1:-eth0}"
DELAY="${2:-300ms}"
JITTER="${3:-30ms}"
LOSS="${4:-0.5%}"
RATE="${5:-20mbit}"

echo "[tc] applying on $DEV delay=$DELAY jitter=$JITTER loss=$LOSS rate=$RATE"
tc qdisc replace dev "$DEV" root netem delay "$DELAY" "$JITTER" loss "$LOSS" rate "$RATE"
tc qdisc show dev "$DEV"
