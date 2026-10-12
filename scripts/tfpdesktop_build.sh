#!/usr/bin/env bash
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
# tfpdesktop_build_linux.sh - TabulexFlowDesktop Frontend Build Script (Linux/macOS)
# Purpose: Build frontend binary using PyInstaller with build mode selection
# Reference: README.md (build instructions)
# 目标平台：前端程序需要编译并部署于 Windows、Debian、Red Hat 系统。
set -euo pipefail

# ==========================================
# 许可证合规说明（构建期依赖）
# PyInstaller 及其 hooks 依赖 pyinstaller-hooks-contrib（GPL-2.0，"GPL with
# Bootloader Exception"）仅在构建期使用：其产物（二进制）不含 hooks 源码，
# 按 PyInstaller 官方 Bootloader Exception 条款不传染最终二进制。
# 详见 docs/NOTICE.txt "Core Dependencies -> pyinstaller" 条目。
# ==========================================

# ==========================================
# Configuration - Modify these values as needed
# ==========================================
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_PATH/.." && pwd)"

# ==========================================
# Linux 发行版侦测（Debian 系 / Red Hat 系）
# 前端需编译并部署于 Windows + Debian + Red Hat；Ubuntu/Mint 归 Debian 系。
# 未识别的发行版 fail-closed（仅支持 Debian 与 Red Hat 系）。
# ==========================================
DISTRO_FAMILY=""
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
fi
NATIVE_PKG_EXT=""
case "${ID:-} ${ID_LIKE:-}" in
    *debian*|*ubuntu*)
        DISTRO_FAMILY="debian"
        NATIVE_PKG_EXT="deb"
        ;;
    *rhel*|*redhat*|*fedora*|*centos*)
        DISTRO_FAMILY="redhat"
        NATIVE_PKG_EXT="rpm"
        ;;
    *)
        echo "  [FAIL] Unsupported Linux distribution: ID='${ID:-?}' ID_LIKE='${ID_LIKE:-}' / 不支持的 Linux 发行版"
        echo "         Only Debian family and Red Hat family are supported. / 仅支持 Debian 系与 Red Hat 系。"
        exit 1
        ;;
esac
echo "Detected Linux distro family: $DISTRO_FAMILY (ID=${ID:-?}) / 已侦测发行版家族: $DISTRO_FAMILY"
# ==========================================

# ==========================================
# Activate Python 3.12 venv: Linux 构建必须使用 Python 3.12 环境
# ==========================================
# 编译 Python 环境（venv），默认取前端工程目录内的 venv（$PROJECT_DIR/venv），可用环境变量 TFP_VENV 覆盖：
#   export TFP_VENV=/path/to/your/py312-venv
# venv 需已安装 requirements.txt 依赖（wxPython/PyInstaller 等，wx 由系统 apt 提供，
# 见 requirements_linux.txt）。
PYTHON_VENV="${TFP_VENV:-$PROJECT_DIR/venv}"
if [ ! -d "$PYTHON_VENV/bin" ]; then
    echo "  [FAIL] Python venv not found: $PYTHON_VENV"
    exit 1
fi

source "$PYTHON_VENV/bin/activate" || { echo "  [FAIL] Could not activate venv: $PYTHON_VENV"; exit 1; }

if [ "${VIRTUAL_ENV:-}" != "$PYTHON_VENV" ]; then
    echo "  [FAIL] Python venv activation failed (VIRTUAL_ENV != $PYTHON_VENV)"
    exit 1
fi
echo "Activated py312tf venv: $(python3 --version)"

# ==========================================
# RemoteWebpage Linux 回退引擎依赖检查 (v5.x)
# ==========================================
echo ""
echo "Checking RemoteWebpage fallback engine dependencies (pywebview/PyGObject)..."
DEP_MISSING=""
if ! python3 -c "import webview" 2>/dev/null; then
    DEP_MISSING="$DEP_MISSING pywebview"
fi
if ! python3 -c "import gi" 2>/dev/null; then
    DEP_MISSING="$DEP_MISSING PyGObject(gi)"
fi
if [ -n "$DEP_MISSING" ]; then
    echo "  [WARN] Missing Linux RemoteWebpage fallback deps:$DEP_MISSING"
    echo "         RemoteWebpage tool will fall back to 'cannot display' behavior (other features unaffected) / RemoteWebpage 工具将退回"无法显示"行为（其余功能不受影响）。"
    echo "         Linux installation steps (see TabulexFlowDesktop/requirements_linux.txt) / Linux 环境安装方法（见 TabulexFlowDesktop/requirements_linux.txt）："
    echo "           pip install -r requirements_linux.txt"
    if [ "$DISTRO_FAMILY" = "debian" ]; then
        echo "           sudo apt install python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0"
    else
        echo "           sudo dnf install python3-gobject webkit2gtk4.1"
    fi
else
    echo "  [OK] pywebview / PyGObject both available; Linux RemoteWebpage fallback engine enabled / pywebview / PyGObject 均可用，Linux RemoteWebpage 回退引擎已启用"
fi
echo ""

# ==========================================
# Build mode selection (v3.9)
# ==========================================
echo "=========================================="
echo " TabulexFlowDesktop Build Configuration"
echo "=========================================="
echo ""
echo " Select build mode:"
echo ""
echo " [1] Production (default)"
echo "     Binary connects to https://tabulexflow.com:443"
echo "     Fallback to 127.0.0.1:8080 is BLOCKED"
echo "     Sub-tools download binary ZIP from backend"
echo "     Full security checks enforced"
echo ""
echo " [2] Local Test"
echo "     Binary connects to http://127.0.0.1:8080"
echo "     Fallback to public backend is BLOCKED"
echo "     Sub-tools download binary ZIP from backend"
echo "     Binary name has -devtest suffix"
echo "     For development testing ONLY, do NOT distribute"
echo ""
read -rp "Enter choice [1-2] (default=1): " BUILD_CHOICE
BUILD_CHOICE="${BUILD_CHOICE:-1}"

if [ "$BUILD_CHOICE" = "1" ]; then
    TFP_BUILD_TARGET_FRONTEND="production"
    echo ""
    echo " [Selected] Production build"
elif [ "$BUILD_CHOICE" = "2" ]; then
    TFP_BUILD_TARGET_FRONTEND="localtest"
    echo ""
    echo " [Selected] Local Test build - FOR DEVELOPMENT ONLY"
else
    echo ""
    echo " Invalid choice. Defaulting to Production build."
    TFP_BUILD_TARGET_FRONTEND="production"
fi
echo ""

# ==========================================
# Package mode selection
# ==========================================
echo " Select package mode:"
echo ""
echo " [1] Single-file (default)"
echo "     Everything packed into one binary, easier to distribute"
echo ""
echo " [2] Directory mode"
echo "     Binary + dependencies in a folder, faster startup"
echo ""
read -rp "Enter choice [1-2] (default=1): " PKG_CHOICE
PKG_CHOICE="${PKG_CHOICE:-1}"

if [ "$PKG_CHOICE" = "1" ]; then
    TFP_PACKAGE_MODE="onefile"
    echo ""
    echo " [Selected] Single-file mode"
elif [ "$PKG_CHOICE" = "2" ]; then
    TFP_PACKAGE_MODE="onedir"
    echo ""
    echo " [Selected] Directory mode"
else
    echo ""
    echo " Invalid choice. Defaulting to Single-file mode."
    TFP_PACKAGE_MODE="onefile"
fi
echo ""
export TFP_PACKAGE_MODE="$TFP_PACKAGE_MODE"

# ==========================================
# Build edition selection (OSS Community vs Full)
# ==========================================
echo " Select build edition:"
echo ""
echo " [1] OSS Community Edition (default)"
echo "     Pure frontend + BuiltinProgram only"
echo "     Hides login/backend/remote tools"
echo "     IS_OSS_COMMUNITY_BUILD = True baked into binary"
echo ""
echo " [2] Full Edition"
echo "     Includes login + remote tools (RemoteProgram/RemoteWebpage)"
echo "     Connects to backend (production or local test)"
echo "     IS_OSS_COMMUNITY_BUILD = False baked into binary"
echo ""
read -rp "Enter choice [1-2] (default=1): " OSS_CHOICE
OSS_CHOICE="${OSS_CHOICE:-1}"

if [ "$OSS_CHOICE" = "1" ]; then
    TFP_OSS_MODE="oss"
    echo ""
    echo " [Selected] OSS Community Edition (default)"
elif [ "$OSS_CHOICE" = "2" ]; then
    TFP_OSS_MODE="full"
    echo ""
    echo " [Selected] Full Edition (with login & remote tools)"
else
    echo ""
    echo " Invalid choice. Defaulting to OSS Community Edition."
    TFP_OSS_MODE="oss"
fi
echo ""

# ==========================================
# Linux 发布包询问（提前到这里、编译开始之前）
# 目的：让用户在前面一次性选完所有选项，编译过程全程无人值守；
#       且此时尚未启动计时，用户思考/等待不会计入编译耗时。
# ==========================================
if [ "$TFP_BUILD_TARGET_FRONTEND" = "production" ]; then
    echo " Select whether to also generate Linux distro packages (.$NATIVE_PKG_EXT + .AppImage):"
    echo ""
    echo " [Y] (default) Generate .$NATIVE_PKG_EXT + .AppImage (via scripts/tfpdesktop_package_linux.sh)"
    echo " [n] Skip; run scripts/tfpdesktop_package_linux.sh later to generate"
    echo ""
    read -rp "Enter choice [Y/n] (default=Y): " PKG_CHOICE_UPFRONT
    case "${PKG_CHOICE_UPFRONT:-Y}" in
        [Nn])
            TFP_RUN_PACKAGE="no"
            echo ""
            echo " [Selected] Skip distro packages (run scripts/tfpdesktop_package_linux.sh later)"
            ;;
        *)
            TFP_RUN_PACKAGE="yes"
            echo ""
            echo " [Selected] Will generate .$NATIVE_PKG_EXT + .AppImage after build"
            ;;
    esac
else
    TFP_RUN_PACKAGE="no"
fi
echo ""

# Record start time (after last user interaction)
SCRIPT_T0=$(python3 -c "import time;print(int(time.time()))" 2>/dev/null)

# Trap EXIT to restore OSS flag and show total elapsed time
trap '_restore_oss_flag; _show_total_time' EXIT
# 恢复 build_mode.py 中的 OSS 标记为 False（无论编译成功与否都执行，避免影响后续开发）
_restore_oss_flag() {
    if [ -f "$PROJECT_DIR/build_mode.py" ]; then
        sed -i 's/^IS_OSS_COMMUNITY_BUILD = True$/IS_OSS_COMMUNITY_BUILD = False/' "$PROJECT_DIR/build_mode.py" 2>/dev/null || true
    fi
}
_show_total_time() {
    if [ -z "${SCRIPT_T0:-}" ]; then
        return
    fi
    local SCRIPT_T1=$(python3 -c "import time;print(int(time.time()))" 2>/dev/null || echo "$SCRIPT_T0")
    local SCRIPT_ELAPSED=$((SCRIPT_T1 - SCRIPT_T0))
    local SCRIPT_MIN=$((SCRIPT_ELAPSED / 60))
    local SCRIPT_SEC=$((SCRIPT_ELAPSED % 60))
    echo ""
    echo "  Total script time: $SCRIPT_MIN min $SCRIPT_SEC sec"
    echo ""
}

# Write _build_target.py so build_mode.py can read it at runtime
# This file is packaged into the binary by PyInstaller (see build.spec)
cat > "$PROJECT_DIR/_build_target.py" <<EOF
# Auto-generated by tfpdesktop_build_linux.sh - DO NOT EDIT MANUALLY
BUILD_TARGET_FRONTEND = "$TFP_BUILD_TARGET_FRONTEND"
EOF
echo "Written _build_target.py: BUILD_TARGET_FRONTEND=$TFP_BUILD_TARGET_FRONTEND"

echo "=========================================="
echo "Building TabulexFlowDesktop project..."
echo "Build mode: $TFP_BUILD_TARGET_FRONTEND"
echo "Edition: $TFP_OSS_MODE"
echo "Package mode: $TFP_PACKAGE_MODE"
echo "=========================================="

# Change to project directory
cd "$PROJECT_DIR" || { echo "  [FAIL] Could not switch to project dir: $PROJECT_DIR"; exit 1; }

# Read DEFAULT_TOOL from main.py
DEFAULT_TOOL=$(python3 -c "
import re
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'DEFAULT_TOOL\s*=\s*[\"\\']([^\"\\']*)[\"\\']', content)
print(m.group(1) if m and m.group(1) else 'main')
" 2>/dev/null || echo "main")

# Handle empty string as "main"
DEFAULT_TOOL="${DEFAULT_TOOL:-main}"
if [ -z "$DEFAULT_TOOL" ]; then
    DEFAULT_TOOL="main"
fi

# Set base binary name based on DEFAULT_TOOL
if [ "$DEFAULT_TOOL" = "main" ]; then
    BASE_EXE_NAME="TabulexFlow"
else
    BASE_EXE_NAME="$DEFAULT_TOOL"
fi

# Frontend version single source: config/version.txt ProductVersion (shared helper, T1.2)
FE_VERSION="$(python3 "$SCRIPT_PATH/scripts_py/tfpdesktop_version.py" "$PROJECT_DIR" 2>/dev/null || true)"
if [ -z "$FE_VERSION" ]; then
    echo "  [FAIL] Cannot read frontend version from config/version.txt. Aborting build."
    exit 1
fi

# Edition label (OSS / Full) baked into the artifact name
if [ "$TFP_OSS_MODE" = "oss" ]; then
    EDITION_LABEL="OSS"
else
    EDITION_LABEL="Full"
fi

# Final artifact name: <Base>-<version>-<Edition>[-devtest]
# Local test keeps the -devtest suffix to prevent accidental distribution
EXE_NAME="${BASE_EXE_NAME}-${FE_VERSION}-${EDITION_LABEL}"
if [ "$TFP_BUILD_TARGET_FRONTEND" = "localtest" ]; then
    EXE_NAME="${EXE_NAME}-devtest"
fi

echo "Default tool: $DEFAULT_TOOL"
echo "Frontend version: $FE_VERSION"
echo "Edition: $EDITION_LABEL"
echo "Binary name: $EXE_NAME"

# Export final name so build.spec produces it directly (no post-build rename)
export TFP_EXE_NAME="$EXE_NAME"

# Check and close running binary (Linux/macOS)
# 注意：不能用裸 `pkill -f "$EXE_NAME"`——仓库目录 TabulexFlowDesktop 自身含
# "TabulexFlow" 子串，会把本构建脚本进程也匹配并自杀。改为匹配"作为独立路径/命令
# 组件的完整产物名"，仅命中 ./<名>、…/dist/<名>（<名> 形如 TabulexFlow-<版本>-<形态>[-devtest]），
# 不命中脚本自身。
_EXE_MATCH="(^|/)$EXE_NAME( |\$)"
if pgrep -f "$_EXE_MATCH" &>/dev/null; then
    echo "Found running $EXE_NAME, closing..."
    pkill -f "$_EXE_MATCH" 2>/dev/null || true
    sleep 2
    echo "Process closed"
else
    echo "No running $EXE_NAME found"
fi

echo "Cleaning previous builds..."
echo "Cleaning PyInstaller build cache..."
rm -rf "$PROJECT_DIR/__pycache__"
# 不再整体删除 dist：仅移除本次构建目标，保留另一平台（Windows/Linux）已编译产物与校验清单，
# 避免 Windows 与 Linux 构建相互删除对方产物。
mkdir -p "$PROJECT_DIR/dist"
if [ "$TFP_PACKAGE_MODE" = "onedir" ]; then
    echo "Removing previous artifact: dist/$EXE_NAME/"
    rm -rf "$PROJECT_DIR/dist/$EXE_NAME"
else
    echo "Removing previous artifact: dist/$EXE_NAME"
    rm -f "$PROJECT_DIR/dist/$EXE_NAME"
fi
# Clean PyInstaller internal build folder
if [ -d "$PROJECT_DIR/build" ]; then
    echo "Cleaning build directory..."
    rm -rf "$PROJECT_DIR/build"
fi

# ==========================================
# OSS 合规（L-8）：清理源码树 config/ 内运行时残留的凭据文件
# tfp_secure_storage 在本机运行（源码或本地测试产物）时可能把 fallback 凭据
# 写到源码树 config/ 目录（如 .auth_token、.tfp_fernet_key）；构建前统一删除，
# 防止其随源码仓库或源码压缩包发布泄露。仅删除运行时残留命名模式，不影响正常配置文件。
# ==========================================
shopt -s nullglob
for _residual in "$PROJECT_DIR"/config/.auth_* "$PROJECT_DIR"/config/.session* "$PROJECT_DIR"/config/.tfp_fernet_key; do
    rm -f "$_residual"
    echo "Deleted source-tree residual credential file: $_residual"
done
shopt -u nullglob

# ==========================================
# OSS 合规：清理源码树内闭源子工具残留（RemoteProgram / RemoteWebpage + 本地 EXE 完整性清单）
# tools_fe/tools_remote_program、tools_fe/tools_remote_webpage 为运行时从后端下载的
# 闭源工具目录（含 app_icon.ico 等资源），tools_fe/.tfp_manifests 为本地独占的 EXE 哈希
# 清单；三者均不属于开源发布内容。构建前统一移除，避免被源码压缩包 / 非 git 打包方式夹带。
# ==========================================
for _closed_dir in \
    "$PROJECT_DIR/tools_fe/tools_remote_program" \
    "$PROJECT_DIR/tools_fe/tools_remote_webpage" \
    "$PROJECT_DIR/tools_fe/.tfp_manifests"; do
    if [ -d "$_closed_dir" ]; then
        rm -rf "$_closed_dir"
        echo "Removed closed-source sub-tool residue: $_closed_dir"
    fi
done

echo "Building $EXE_NAME..."
echo "Using config/build.spec configuration..."

# ==========================================
# Security pre-build self-check (v3.6/v3.9)
# Fail-fast if the production-mode mechanism is broken
# ==========================================
echo ""
echo "[1/2] Checking build_mode.py production mechanism..."
if [ ! -f "$PROJECT_DIR/build_mode.py" ]; then
    echo "  [FAIL] build_mode.py missing. Aborting build."
    exit 1
fi
BM_BUILD=$(python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from build_mode import IS_PRODUCTION_BUILD
print(IS_PRODUCTION_BUILD)
" 2>/dev/null || echo "")
if [ -z "$BM_BUILD" ]; then
    echo "  [FAIL] Cannot evaluate build_mode.IS_PRODUCTION_BUILD. Aborting build."
    exit 1
fi
if [ "$BM_BUILD" = "True" ]; then
    echo "  [FAIL] build_mode.IS_PRODUCTION_BUILD is True in source tree."
    echo "        Expected False before packaging (PyInstaller sets sys.frozen at runtime)."
    echo "        Aborting build to avoid shipping a misconfigured binary."
    exit 1
fi
echo "  [OK] build_mode.py is healthy (source mode)"

echo "[2/2] Checking backend-address hardcodes in core files... (warning-only for open-source builds)"
# 本项目为开源项目，禁止前端配置 127.0.0.1 等地址无效，因此此检查仅作警告，不终止编译
BAD_HARDC=""
for f in "$PROJECT_DIR/main.py" "$PROJECT_DIR/build_mode.py" "$PROJECT_DIR/tfp_utils/tfp_backend_config.py" "$PROJECT_DIR/tfp_auth/tfp_auth_manager.py"; do
    if [ -f "$f" ] && grep -qE "http://127\.0\.0\.1|http://localhost" "$f" 2>/dev/null; then
        BAD_HARDC="$BAD_HARDC $f"
    fi
done
if [ -n "$BAD_HARDC" ]; then
    echo "  [WARN] Found \"http://127.0.0.1\" or \"http://localhost\" hardcoded in:$BAD_HARDC"
    echo "        This is an open-source project; frontend is not required to forbid local backend addresses."
    echo "        Build continues."
else
    echo "  [OK] No insecure backend-address hardcodes found"
fi

if [ "$TFP_BUILD_TARGET_FRONTEND" = "localtest" ]; then
    echo "  [INFO] Local test binary will use backend: http://127.0.0.1:8080"
else
    echo "  [INFO] Production binary will use fixed backend: https://tabulexflow.com:443"
fi
echo ""

echo "[3/3] Checking config/version.txt placeholder value... (T1.4)"
# 前端版本号单一来源为 config/version.txt 的 ProductVersion（main.py 启动时读取）。
# 检查逻辑单一实现在 tfpdesktop_version_check.py（bat/sh 共用），此处仅薄调用。
if ! python3 "$SCRIPT_PATH/scripts_py/tfpdesktop_version_check.py" "$PROJECT_DIR"; then
    echo "  [FAIL] Frontend version check failed. Aborting build."
    exit 1
fi
echo ""

# ==========================================
# 社区发布版（OSS）标记：仅 OSS 社区版编译前临时置 True，使其被打包进产物
# 社区版为"纯前端 + BuiltinProgram"，隐藏登录/后端/远程工具；
# 完整版（Full）保持 False（含登录/远程工具，连接后端）。
# 编译完成后由 EXIT 陷阱自动恢复为 False，便于平时开发/测试后端与收费工具
# ==========================================
if [ "$TFP_OSS_MODE" = "oss" ]; then
    echo "[OSS] Temporarily setting build_mode.IS_OSS_COMMUNITY_BUILD to True (auto-reverted to False after build) / 将 build_mode.IS_OSS_COMMUNITY_BUILD 临时置为 True（编译后自动还原为 False）..."
    sed -i 's/^IS_OSS_COMMUNITY_BUILD = False$/IS_OSS_COMMUNITY_BUILD = True/' "$PROJECT_DIR/build_mode.py"
else
    echo "[Full] Full edition build: IS_OSS_COMMUNITY_BUILD stays False (includes login/remote tools) / 完整版构建：IS_OSS_COMMUNITY_BUILD 保持 False（含登录/远程工具）"
fi

# Use --clean to ensure clean build
# TFP_PACKAGE_MODE env var is read by build.spec to select onefile/onedir
pyinstaller --clean "$PROJECT_DIR/config/build.spec"

# Determine binary path based on package mode
# Final name (with version + edition + optional -devtest) is produced directly by build.spec
if [ "$TFP_PACKAGE_MODE" = "onedir" ]; then
    EXE_PATH="$PROJECT_DIR/dist/$EXE_NAME/$EXE_NAME"
    DIST_DIR="$PROJECT_DIR/dist/$EXE_NAME"
else
    EXE_PATH="$PROJECT_DIR/dist/$EXE_NAME"
    DIST_DIR="$PROJECT_DIR/dist"
fi

echo "Build process completed, checking output..."
sleep 3

# Check output locations
if [ -f "$EXE_PATH" ]; then
    echo ""
    echo "Build successful!"
    if [ "$TFP_BUILD_TARGET_FRONTEND" = "localtest" ]; then
        echo "Security: LOCAL TEST build - backend fixed to http://127.0.0.1:8080"
        echo "WARNING: This binary is for development testing ONLY. Do NOT distribute!"
    else
        echo "Security: production mode is baked in (backend fixed to https://tabulexflow.com:443)"
    fi
    echo "Executable location: $EXE_PATH"

    # Check file size
    SIZE_BYTES=$(stat -c%s "$EXE_PATH" 2>/dev/null || stat -f%z "$EXE_PATH" 2>/dev/null || echo 0)
    SIZE_MB=$((SIZE_BYTES / 1048576))
    echo "File size: $SIZE_MB MB"

    if [ "$TFP_BUILD_TARGET_FRONTEND" = "localtest" ]; then
        # Local test build: do NOT copy to backend download directory
        echo ""
        echo "Local test build - do NOT distribute!"
        echo "Run the binary directly from: $EXE_PATH"
    else
        # 正常生产构建：不再自动复制到后端目录（开源版）。产物留在 dist/ 下即可。
        echo ""
        echo "Build output is in: $(dirname "$DIST_DIR")"
        echo "Run it via scripts/tfpdesktop_dist.sh, or package via scripts/tfpdesktop_package_linux.sh"
    fi

    # ===== OSS 合规（L-8）：清理 dist 内可能残留的敏感凭据文件 =====
    # tfp_secure_storage 在 frozen 模式下把 fallback 凭据（如 .auth_token）写到
    # exe 同级 config/ 目录；若曾在构建机本机测试运行过 onedir 产物，这些文件
    # 可能残留在 dist/ 内。构建完成后统一扫描删除，防止被打包或误提交 git。
    if [ -d "$PROJECT_DIR/dist" ]; then
        SENSITIVE_FOUND=$(find "$PROJECT_DIR/dist" -type f \( \
            -name ".auth_*" -o -name "*.auth_token" -o -name ".session*" -o \
            -name ".tfp_fernet_key" -o -name "*.key" -o -name "*.pem" -o -name "credentials*" \) 2>/dev/null)
        if [ -n "$SENSITIVE_FOUND" ]; then
            echo ""
            echo "[SECURITY] Found and deleted residual sensitive credential files in dist / 发现并删除 dist 内残留的敏感凭据文件:"
            echo "$SENSITIVE_FOUND" | while read -r sf; do
                rm -f "$sf" && echo "  deleted: $sf"
            done
        fi
    fi

    # ===== 方案A：清理构建产物目录内运行时用户数据 =====
    # user_setting/<用户id>/ 由本机运行产物时生成，目录名为登录用户 id，内含
    # 收藏/最近使用等数据；随 dist 分发会泄露账号身份。编译成功后统一删除。
    for _us in "$PROJECT_DIR/dist/user_setting" "$DIST_DIR/user_setting"; do
        if [ -d "$_us" ]; then
            rm -rf "$_us"
            echo "[SECURITY] Removed runtime user data: $_us / 已移除运行时用户数据"
        fi
    done

    # ===== 方案B：清除构建机本机登录会话（keyring + config 回退文件）=====
    # 否则同一 OS 用户打开新产物会经钥匙串自动恢复登录。破坏性操作（需重新登录）。
    if [ -f "$SCRIPT_PATH/scripts_py/tfpdesktop_clear_credentials.py" ]; then
        python3 "$SCRIPT_PATH/scripts_py/tfpdesktop_clear_credentials.py" "$PROJECT_DIR" || \
            echo "  [WARN] Credential cleanup script failed (build continues) / 凭据清理脚本失败（构建继续）"
    else
        echo "  [WARN] Not found: scripts/scripts_py/tfpdesktop_clear_credentials.py; skipping keyring session cleanup / 未找到凭据清理脚本，跳过钥匙串会话清理"
    fi

    # 生成 Linux 发布包（.$NATIVE_PKG_EXT 安装包 + .AppImage）：按编译开始前询问的结果执行，过程无人值守
    if [ "$TFP_BUILD_TARGET_FRONTEND" = "production" ] && [ "$TFP_RUN_PACKAGE" = "yes" ]; then
        echo ""
        if [ -x "$SCRIPT_PATH/tfpdesktop_package_linux.sh" ]; then
            "$SCRIPT_PATH/tfpdesktop_package_linux.sh" || echo "  [WARN] Distro package script failed to run (see info above) / 发布包生成脚本执行失败（见上方信息）"
        else
            echo "  [WARN] Not found: $SCRIPT_PATH/tfpdesktop_package_linux.sh, skipping distro package generation / 未找到 $SCRIPT_PATH/tfpdesktop_package_linux.sh，跳过发布包生成"
        fi
    fi

    # Clean build directory after build
    if [ -d "$PROJECT_DIR/build" ]; then
        echo "Cleaning build directory..."
        rm -rf "$PROJECT_DIR/build"
    fi
else
    echo ""
    echo "Build failed! Executable not found at: $EXE_PATH"
    echo "Checking what was actually created in dist folder:"
    if [ -d "$PROJECT_DIR/dist" ]; then
        ls -la "$PROJECT_DIR/dist/" 2>/dev/null || echo "Empty or no access"
    else
        echo "No dist folder found"
    fi
fi

echo ""
