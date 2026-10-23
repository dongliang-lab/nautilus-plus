#!/usr/bin/env bash
# 把 nautilus-meta 插件装到用户目录,然后重启 nautilus。
#
# 纯插件:不需要构建、不需要 pkexec。系统 nautilus 与 nautilus-plus 都会加载
# 用户目录下的扩展;两份同名副本同时存在会出现双菜单(见 pitfalls #5),所以
# 系统里残留的旧副本会被提示删除(需要 pkexec,不自动执行)。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/plus/extensions/python/nautilus-meta/nautilus-meta.py"
USER_DIR="$HOME/.local/share/nautilus-python/extensions"
SYSTEM_COPY="/usr/share/nautilus-python/extensions/nautilus-meta.py"

mkdir -p "$USER_DIR"
install -m 644 "$SRC" "$USER_DIR/nautilus-meta.py"
echo "已安装: $USER_DIR/nautilus-meta.py"

if [ -e "$SYSTEM_COPY" ]; then
    echo
    echo "注意:系统里还有一份旧副本 $SYSTEM_COPY"
    echo "两份同时存在会出现重复菜单项,请执行:"
    echo "  pkexec rm $SYSTEM_COPY"
fi

nautilus -q 2>/dev/null || true
echo "nautilus 已重启;重新打开窗口生效。"
