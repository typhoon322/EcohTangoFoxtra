#!/usr/bin/env bash
# daily_run_retry.sh — 本地每日运行：失败则每小时重试，直到成功
#
# 用法:
#   ./scripts/daily_run_retry.sh
#   MAX_ATTEMPTS=8 RETRY_INTERVAL=3600 ./scripts/daily_run_retry.sh
#
# macOS cron 示例（工作日 16:35 启动，含重试）:
#   35 16 * * 1-5 cd /path/to/EcohTangoFoxtra && ./scripts/daily_run_retry.sh >> logs/daily_run.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-12}"
RETRY_INTERVAL="${RETRY_INTERVAL:-3600}"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_run_$(date +%Y%m%d).log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# 跑 daily 前先与远程同步，避免本地/CI 报告冲突
if [ -x "$ROOT/scripts/git_sync.sh" ]; then
  log "同步远程（自动处理冲突）..."
  bash "$ROOT/scripts/git_sync.sh" pull >> "$LOG_FILE" 2>&1 || log "⚠️ git sync 警告（继续运行）"
fi

# 已成功则直接退出
if "$PYTHON" scripts/daily_run.py --check-only 2>/dev/null; then
  log "今日已成功，无需重试"
  exit 0
fi

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  log "尝试 $attempt / $MAX_ATTEMPTS"
  if "$PYTHON" scripts/daily_run.py 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ 每日管线成功 (第 $attempt 次)"
    exit 0
  fi

  if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
    log "❌ 已达最大重试次数 ($MAX_ATTEMPTS)，放弃"
    exit 1
  fi

  log "失败，${RETRY_INTERVAL}s 后重试..."
  sleep "$RETRY_INTERVAL"
  attempt=$((attempt + 1))
done
