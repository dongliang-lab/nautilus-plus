#!/usr/bin/env bash
# 开发部署:安装到系统,并兜住书签被清空的意外。
#
# 书签文件只在用户改动书签时才被写入,安装本身不碰它(见 pitfalls)。这里仍然
# 在安装前临时留一份,安装后条目数变少就还原,用完即清,不留历史、不留常驻单元。
#
# 两个环境变量只为自测与特殊场合留口,平时不用设:
#   BOOKMARKS_FILE  书签文件路径(默认 ~/.config/gtk-3.0/bookmarks)
#   INSTALL_CMD     安装命令(默认 pkexec <ninja> -C <build> install)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"
BOOKMARKS="${BOOKMARKS_FILE:-$HOME/.config/gtk-3.0/bookmarks}"

count_entries() {
    if [ ! -f "$1" ]; then
        echo 0
        return
    fi
    awk 'NF' "$1" | wc -l
}

backup=""
cleanup() {
    # 用 if 而非 `[ ... ] && rm`:后者在 backup 为空时返回 1,
    # 会把整个脚本的退出码带成失败。
    if [ -n "$backup" ]; then
        rm -f "$backup"
    fi
}
trap cleanup EXIT

before=0
if [ -f "$BOOKMARKS" ]; then
    backup="$(mktemp -t nautilus-bookmarks.XXXXXX)"
    cp -a "$BOOKMARKS" "$backup"
    before="$(count_entries "$backup")"
    echo "书签:$before 条,已临时备份"
else
    echo "书签文件不存在,跳过备份"
fi

# 先以当前用户身份构建完。否则 ninja 会以 root 编译,在 build/ 里留下
# root 属主的产物,之后你自己的构建就写不动了(实测踩到过)。
ninja -C "$BUILD_DIR"

if [ -n "${INSTALL_CMD:-}" ]; then
    eval "$INSTALL_CMD"
else
    ninja_bin="$(command -v ninja)"
    pkexec "$ninja_bin" -C "$BUILD_DIR" install
fi

after="$(count_entries "$BOOKMARKS")"
if [ "$before" -gt 0 ] && [ "$after" -lt "$before" ]; then
    cp -a "$backup" "$BOOKMARKS"
    echo "⚠ 安装后书签由 $before 条变为 $after 条,已还原"
else
    echo "✓ 书签未变($after 条)"
fi
