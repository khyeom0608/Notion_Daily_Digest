#!/bin/bash
# Wrapper invoked by launchd.
# - cd into the script's directory so relative paths work
# - append both stdout and stderr to a per-day log file
# - propagate the python exit code

set -u

cd "$(dirname "$0")"

LOG_DIR="$HOME/Library/Logs/notion-digest"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/digest-$(date +%Y-%m-%d).log"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') run start ====="
  /usr/bin/python3 daily_notion_digest.py
  RC=$?
  echo "===== exit code: $RC ====="
  exit $RC
} >> "$LOG" 2>&1
