#!/usr/bin/env bash
# resolve_conflicts_ci.sh — GitHub Actions 专用：push 前自动处理冲突
# 策略与 git_sync.sh 相反（rebase 视角）:
#   docs 报告 → 保留 CI 刚生成的 (--theirs in rebase = our new commit)
#   backtest.db → 保留 git 仓库版本 (--ours in rebase = upstream)

set -euo pipefail

DOCS=(
  docs/index.html
  docs/lite_card.md
  docs/fund_report.md
  docs/.daily_run_status.json
)

if ! git diff --name-only --diff-filter=U 2>/dev/null | grep -q .; then
  exit 0
fi

echo "[ci-resolve] 检测到冲突，自动处理..."

for f in "${DOCS[@]}"; do
  if git diff --name-only --diff-filter=U | grep -qxF "$f"; then
    echo "[ci-resolve] docs → CI版本: $f"
    git checkout --theirs "$f" 2>/dev/null || git checkout --ours "$f" 2>/dev/null || true
    git add "$f"
  fi
done

if git diff --name-only --diff-filter=U | grep -qxF "backend/backtest.db"; then
  echo "[ci-resolve] db → 仓库版本: backend/backtest.db"
  git checkout --ours backend/backtest.db 2>/dev/null || true
  git add backend/backtest.db
fi

while IFS= read -r f; do
  [ -z "$f" ] && continue
  echo "[ci-resolve] 其他 → 仓库版本: $f"
  git checkout --ours "$f" 2>/dev/null || true
  git add "$f"
done < <(git diff --name-only --diff-filter=U)

echo "[ci-resolve] 完成"
