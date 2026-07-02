#!/usr/bin/env bash
# git_sync.sh — 本地 ↔ 云端冲突自动处理
#
# 场景: GitHub Actions 提交了日报，本地也跑了 daily_run，push/pull 时冲突
#
# 用法:
#   ./scripts/git_sync.sh pull     # 拉取远程，自动解决冲突（推荐：本地跑 daily 之前）
#   ./scripts/git_sync.sh push     # 拉取 + 解决冲突 + 推送
#   ./scripts/git_sync.sh status   # 检查是否与 remote 分叉
#
# 冲突策略:
#   docs/* 报告文件  → 保留远程（CI 已发布的日报为准）
#   backend/backtest.db → 保留本地（你的 backfill 为准）

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${GIT_BRANCH:-main}"
REMOTE="${GIT_REMOTE:-origin}"

# 自动合并时按策略处理的文件
DOCS_FILES=(
  "docs/index.html"
  "docs/lite_card.md"
  "docs/fund_report.md"
  "docs/.daily_run_status.json"
)
DB_FILE="backend/backtest.db"

log() { echo "[git_sync $(date '+%H:%M:%S')] $*"; }

has_conflicts() {
  git diff --name-only --diff-filter=U 2>/dev/null | grep -q .
}

# pull 冲突: 在 merge 中 --ours=当前分支(本地) --theirs=正在合并进来的(远程)
resolve_pull_conflicts() {
  log "自动解决 pull 冲突..."
  local f
  for f in "${DOCS_FILES[@]}"; do
    if git diff --name-only --diff-filter=U 2>/dev/null | grep -qxF "$f"; then
      log "  docs → 远程: $f"
      git checkout --theirs "$f" 2>/dev/null || true
      git add "$f" 2>/dev/null || true
    fi
  done
  if git diff --name-only --diff-filter=U 2>/dev/null | grep -qxF "$DB_FILE"; then
    log "  db → 本地: $DB_FILE"
    git checkout --ours "$DB_FILE" 2>/dev/null || true
    git add "$DB_FILE" 2>/dev/null || true
  fi
  # 其余冲突文件：保留本地
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    log "  其他 → 本地: $f"
    git checkout --ours "$f" 2>/dev/null || true
    git add "$f" 2>/dev/null || true
  done < <(git diff --name-only --diff-filter=U 2>/dev/null || true)
}

# rebase 冲突: --ours=upstream(远程) --theirs=本地 commit
resolve_rebase_conflicts() {
  log "自动解决 rebase 冲突..."
  local f
  for f in "${DOCS_FILES[@]}"; do
    if git diff --name-only --diff-filter=U 2>/dev/null | grep -qxF "$f"; then
      log "  docs → 远程: $f"
      git checkout --ours "$f" 2>/dev/null || true
      git add "$f" 2>/dev/null || true
    fi
  done
  if git diff --name-only --diff-filter=U 2>/dev/null | grep -qxF "$DB_FILE"; then
    log "  db → 本地: $DB_FILE"
    git checkout --theirs "$DB_FILE" 2>/dev/null || true
    git add "$DB_FILE" 2>/dev/null || true
  fi
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    log "  其他 → 本地: $f"
    git checkout --theirs "$f" 2>/dev/null || true
    git add "$f" 2>/dev/null || true
  done < <(git diff --name-only --diff-filter=U 2>/dev/null || true)
}

do_pull() {
  log "fetch $REMOTE/$BRANCH ..."
  git fetch "$REMOTE" "$BRANCH"

  if git merge-base --is-ancestor HEAD "$REMOTE/$BRANCH" 2>/dev/null; then
    log "fast-forward pull"
    git merge --ff-only "$REMOTE/$BRANCH"
    return 0
  fi

  if git merge-base --is-ancestor "$REMOTE/$BRANCH" HEAD 2>/dev/null; then
    log "本地领先远程，无需 pull"
    return 0
  fi

  log "merge $REMOTE/$BRANCH ..."
  if git merge "$REMOTE/$BRANCH" --no-edit -m "merge: sync with $REMOTE/$BRANCH"; then
    log "✅ merge 成功"
    return 0
  fi

  if has_conflicts; then
    resolve_pull_conflicts
    git commit --no-edit -m "merge: sync with $REMOTE/$BRANCH (auto-resolved)" || true
    log "✅ 冲突已自动解决"
    return 0
  fi

  log "❌ merge 失败"
  return 1
}

do_push() {
  do_pull || true
  log "push $REMOTE $BRANCH ..."
  if git push "$REMOTE" "$BRANCH"; then
    log "✅ push 成功"
    return 0
  fi

  log "push 被拒，rebase 后重试..."
  if ! git pull --rebase "$REMOTE" "$BRANCH"; then
    if has_conflicts; then
      resolve_rebase_conflicts
      git rebase --continue
    else
      log "❌ rebase 失败"
      return 1
    fi
  fi

  git push "$REMOTE" "$BRANCH"
  log "✅ push 成功（rebase 后）"
}

cmd_status() {
  git fetch "$REMOTE" "$BRANCH" 2>/dev/null || true
  local ahead behind
  ahead=$(git rev-list --count "$REMOTE/$BRANCH..HEAD" 2>/dev/null || echo "?")
  behind=$(git rev-list --count "HEAD..$REMOTE/$BRANCH" 2>/dev/null || echo "?")
  log "分支 $BRANCH | 领先 $ahead | 落后 $behind"
  if [ "$ahead" != "0" ] && [ "$behind" != "0" ]; then
    log "⚠️  与远程分叉，建议: ./scripts/git_sync.sh pull"
  fi
}

case "${1:-pull}" in
  pull)   do_pull ;;
  push)   do_push ;;
  status) cmd_status ;;
  *)
    echo "用法: $0 {pull|push|status}"
    exit 1
    ;;
esac
