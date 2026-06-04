#!/bin/bash
# launchd가 호출하는 wrapper.
# - 작업 디렉토리를 .py 위치로 고정
# - stdout/stderr를 일자별 로그로 저장
# - 종료 코드 그대로 반환

set -u

cd "$(dirname "$0")"

LOG_DIR="$HOME/Library/Logs/notion-digest"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/digest-$(date +%Y-%m-%d).log"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') 실행 시작 ====="
  /usr/bin/python3 daily_notion_digest.py
  RC=$?
  echo "===== 종료 코드: $RC ====="
  exit $RC
} >> "$LOG" 2>&1
