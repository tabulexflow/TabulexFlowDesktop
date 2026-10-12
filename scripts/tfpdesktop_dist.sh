#!/usr/bin/env bash
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
# tfpdesktop_dist.sh - 启动编译后的 TabulexFlowDesktop 前端程序（Linux/macOS）
# 与 tfpdesktop_dist.bat（Windows）对应；启动前先切换到可执行文件所在目录
# 自动探测产物（PyInstaller）：名称格式 <名称>-<版本>-<形态>[-devtest]（如 TabulexFlow-1.0.0-OSS）
#   onedir : dist/<名称>/<名称>          例：dist/TabulexFlow-1.0.0-OSS/TabulexFlow-1.0.0-OSS
#   onefile: dist/<名称>                 例：dist/TabulexFlow-1.0.0-OSS-devtest
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)"
FE_DIST="$(cd "$SCRIPT_PATH/../dist" 2>/dev/null && pwd)"

# Linux 发行版侦测（Debian 系 / Red Hat 系）：启动二进制本身一致，此处仅侦测并校验，
# 未识别发行版 fail-closed（仅支持 Debian 与 Red Hat 系）。
DISTRO_FAMILY=""
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
fi
case "${ID:-} ${ID_LIKE:-}" in
    *debian*|*ubuntu*) DISTRO_FAMILY="debian" ;;
    *rhel*|*redhat*|*fedora*|*centos*) DISTRO_FAMILY="redhat" ;;
    *)
        echo "  [FAIL] Unsupported Linux distribution: ID='${ID:-?}' ID_LIKE='${ID_LIKE:-}' / 不支持的 Linux 发行版"
        echo "         Only Debian family and Red Hat family are supported. / 仅支持 Debian 系与 Red Hat 系。"
        exit 1
        ;;
esac

clear
echo "============================================================"
echo "  TabulexFlowDesktop Frontend - Build Artifact Launcher (Linux) / TabulexFlowDesktop 前端 - 编译产物启动（Linux）"
echo "  Distro family / 发行版家族: $DISTRO_FAMILY (ID=${ID:-?})"
echo "============================================================"
echo ""

# 自动探测：名称形如 TabulexFlow-<版本>-<形态>[-devtest]；
# onedir 与 onefile 均支持，多版本共存时按修改时间取最新（onedir/onefile 混合取最新者）
EXE_PATH=""
shopt -s nullglob
_cands=( "$FE_DIST"/TabulexFlow-*/TabulexFlow-* "$FE_DIST"/TabulexFlow-* )
shopt -u nullglob
if [ "${#_cands[@]}" -gt 0 ]; then
    while IFS= read -r _cand; do
        if [ -f "$_cand" ] && [ -x "$_cand" ]; then
            EXE_PATH="$_cand"
            break
        fi
    done <<< "$(ls -1dt "${_cands[@]}" 2>/dev/null || true)"
fi

if [ -z "$EXE_PATH" ]; then
    echo "  [FAIL] Compiled frontend executable not found / 未找到编译后的前端可执行文件：$FE_DIST"
    echo "         Expected name pattern: TabulexFlow-<version>-<OSS|Full>[-devtest] / 期望命名：TabulexFlow-<版本>-<OSS|Full>[-devtest]"
    echo "           onedir : dist/TabulexFlow-<version>-<edition>/TabulexFlow-<version>-<edition> / （目录模式）"
    echo "           onefile: dist/TabulexFlow-<version>-<edition> / （单文件模式）"
    echo "         Please run scripts/tfpdesktop_build.sh to build first. / 请先运行 scripts/tfpdesktop_build.sh 进行编译。"
    exit 1
fi

EXE_DIR="$(dirname "$EXE_PATH")"
echo "  Frontend program dir / 前端程序目录 : $EXE_DIR"
echo "  Executable / 可执行文件   : $EXE_PATH"
echo ""

# Local Test 开发版产物提示（后端指向本地 127.0.0.1:8080，禁止分发）
case "$EXE_PATH" in
    *-devtest*)
        echo "  [WARN] LOCAL TEST dev-test artifact detected (backend points to local 127.0.0.1:8080). / 检测到 LOCAL TEST 开发测试产物（backend 指向本地 127.0.0.1:8080）。"
        echo "         This artifact is for development testing only, do NOT distribute! / 该产物仅用于开发测试，请勿分发！"
        echo ""
        ;;
esac

# 切换到可执行文件所在目录，保证相对路径正确
cd "$EXE_DIR" || { echo "  [FAIL] Cannot switch to frontend program directory: $EXE_DIR / 无法切换到前端程序目录：$EXE_DIR"; exit 1; }
echo "  Starting frontend program (close the window to exit)... / 正在启动前端程序（关闭窗口即退出）..."
echo "============================================================"
echo ""
./"$(basename "$EXE_PATH")"