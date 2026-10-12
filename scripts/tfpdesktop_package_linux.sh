#!/usr/bin/env bash
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
# tfpdesktop_package_linux.sh - 将已编译的 TabulexFlowDesktop 前端产物打包为 Linux 分发格式
#   0) 自动侦测 Linux 发行版家族：Debian 系 → .deb；Red Hat 系 → .rpm
#      （未识别发行版 fail-closed，仅支持 Debian 系与 Red Hat 系）
#   1) 原生安装包：
#        Debian 系：.deb（适配 Debian / Ubuntu / Linux Mint，apt install 或双击安装）
#        Red Hat 系：.rpm（适配 RHEL / CentOS / Fedora / Rocky / Alma，dnf install）
#   2) .AppImage 免安装单文件（chmod +x 后直接运行，跨发行版便携）
# 用法：
#   先运行 tfpdesktop_build.sh 编译出 dist 产物（Production 或 Local Test；onefile 或 onedir；
#   OSS 或 Full 均可），再执行本脚本，会自动侦测产物并打包：
#     ./tfpdesktop_package_linux.sh
#   产物名格式 <名称>-<版本>-<形态>[-devtest]（如 TabulexFlow-1.0.0-OSS），自动侦测：
#   Product：dist/TabulexFlow-<版本>-<形态>（onefile）或 dist/TabulexFlow-<版本>-<形态>/TabulexFlow-<版本>-<形态>（onedir）
#   Local Test：同上，名称末尾追加 -devtest
#   - 当同时存在多个产物时：交互选择；可用 TFP_PACKAGE_EXE=<完整路径> 直接指定。
#   - Local Test（-devtest）产物是"禁止对外分发"的开发测试版（后端固化 127.0.0.1）：
#     打包包名带 -devtest 后缀，且需交互确认（或用 TFP_PACKAGE_ALLOW_DEV=1 跳过确认）。
# 产物输出到 dist/：
#   Debian 系：tabulexflow[-devtest]_<版本>_amd64.deb
#   Red Hat 系：tabulexflow[-devtest].x86_64.rpm
#   <名称>-<版本>-<形态>[-devtest]-x86_64.AppImage
# 说明：本脚本对 OSS 社区版与完整商业版一视同仁，仅对 dist 中已编译好的二进制打包；
#       版本号取自 config/version.txt 的 ProductVersion（scripts_py/tfpdesktop_version.py）；
#       图标由 app_icon.ico 经 Pillow 生成多尺寸 PNG。
# 参考：README.md（构建与发布说明）。
set -euo pipefail

# ==========================================
# 配置
# ==========================================
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_PATH/.." && pwd)"
DIST_DIR="$PROJECT_DIR/dist"
PKG_NAME="tabulexflow"           # 后续按产物类型调整（devtest 追加后缀）
DISPLAY_NAME="TabulexFlow"
COMMENT="TabulexFlow - open-source frontend with BuiltinProgram tools (AGPL v3)"
CATEGORIES="Utility;Office;"
ICON_SRC="$PROJECT_DIR/app_icon.ico"
LICENSE_SRC="$PROJECT_DIR/LICENSE.txt"
TOOLS_DIR="${HOME:-/tmp}/.local/bin"
APPIMAGETOOL_CACHE="$TOOLS_DIR/appimagetool"
ARCH_DEB="amd64"
ARCH_RPM="x86_64"
ARCH_APPIMAGE="x86_64"

# ==========================================
# Linux 发行版侦测（Debian 系 / Red Hat 系）
# Debian 系 → .deb（dpkg-deb）；Red Hat 系 → .rpm（rpmbuild）。
# 未识别的发行版 fail-closed（仅支持 Debian 系与 Red Hat 系）。
# ==========================================
DISTRO_FAMILY=""
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
fi
case "${ID:-} ${ID_LIKE:-}" in
    *debian*|*ubuntu*)
        DISTRO_FAMILY="debian"
        ;;
    *rhel*|*redhat*|*fedora*|*centos*)
        DISTRO_FAMILY="redhat"
        ;;
    *)
        echo "  [FAIL] Unsupported Linux distribution: ID='${ID:-?}' ID_LIKE='${ID_LIKE:-}' / 不支持的 Linux 发行版"
        echo "         Only Debian family (.deb) and Red Hat family (.rpm) are supported. / 仅支持 Debian 系（.deb）与 Red Hat 系（.rpm）。"
        exit 1
        ;;
esac
echo "  Distro family / 发行版家族: $DISTRO_FAMILY (ID=${ID:-?})"
NATIVE_PKG_OUT=""
NATIVE_PKG_KIND=""

# ==========================================
# Python venv（用于 Pillow 生成 PNG 图标）。可用环境变量 TFP_VENV 覆盖（默认为前端工程目录内的 venv）。
# ==========================================
PYTHON_VENV="${TFP_VENV:-$PROJECT_DIR/venv}"
if [ -d "$PYTHON_VENV/bin" ]; then
    source "$PYTHON_VENV/bin/activate" 2>/dev/null || true
fi

# ==========================================
# 1. 自动侦测已编译二进制
#    支持 Production / Local Test（-devtest）两种生成物，onefile 与 onedir 均可。
# ==========================================
# 候选：onefile=直接文件；onedir=目录内同名可执行文件。
# 名称格式 <名称>-<版本>-<形态>[-devtest]（如 TabulexFlow-1.0.0-OSS），按修改时间倒序（最新优先）
shopt -s nullglob
_ARTIFACT_CANDS=( "$DIST_DIR"/TabulexFlow-*/TabulexFlow-* "$DIST_DIR"/TabulexFlow-* )
shopt -u nullglob
FOUND=()
if [ "${#_ARTIFACT_CANDS[@]}" -gt 0 ]; then
    while IFS= read -r _cand; do
        if [ -f "$_cand" ] && [ -x "$_cand" ]; then
            FOUND+=("$_cand")
        fi
    done <<< "$(ls -1dt "${_ARTIFACT_CANDS[@]}" 2>/dev/null || true)"
fi

EXE_PATH=""
if [ -n "${TFP_PACKAGE_EXE:-}" ]; then
    # 环境变量显式指定（调试/自动化用）
    if [ -x "$TFP_PACKAGE_EXE" ]; then
        EXE_PATH="$TFP_PACKAGE_EXE"
        echo "  Explicit artifact / 显式指定产物: $EXE_PATH"
    else
        echo "  [FAIL] File specified by TFP_PACKAGE_EXE is not executable / TFP_PACKAGE_EXE 指定的文件不可执行: $TFP_PACKAGE_EXE"
        exit 1
    fi
elif [ "${#FOUND[@]}" -eq 1 ]; then
    EXE_PATH="${FOUND[0]}"
elif [ "${#FOUND[@]}" -gt 1 ]; then
    echo "  Multiple compiled artifacts detected, please select one to package / 检测到多个已编译产物，请选择要打包的一个:"
    i=1
    for c in "${FOUND[@]}"; do
        echo "    [$i] $c"
        i=$((i + 1))
    done
    CHOICE=""
    if [ -t 0 ]; then
        read -rp "Enter choice [1-${#FOUND[@]}]: " CHOICE
    fi
    CHOICE="${CHOICE:-1}"
    if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt "${#FOUND[@]}" ]; then
        echo "  [FAIL] Invalid choice / 无效选择: $CHOICE"
        exit 1
    fi
    EXE_PATH="${FOUND[$((CHOICE - 1))]}"
fi

if [ -z "$EXE_PATH" ]; then
    echo "  [FAIL] Compiled frontend artifact not found. / 未找到已编译的前端产物。"
    echo "         Please run scripts/tfpdesktop_build.sh to build first, then rerun this script. / 请先运行 scripts/tfpdesktop_build.sh 编译，再执行本脚本。"
    echo "         Supported artifacts / 支持的产物："
    echo "           Production : dist/TabulexFlow-<version>-<edition> (onefile) or dist/TabulexFlow-<version>-<edition>/TabulexFlow-<version>-<edition> (onedir) / 单文件或目录模式"
    echo "           Local Test : same name with -devtest suffix / 名称末尾追加 -devtest"
    exit 1
fi
echo "  Executable / 可执行文件: $EXE_PATH"

# 判定产物类型：名称带 -devtest → Local Test；否则 Production
EXE_NAME="$(basename "$EXE_PATH")"
if [[ "$EXE_NAME" == *-devtest ]]; then
    FLAVOR="devtest"
    PKG_NAME="tabulexflow-devtest"
    DISPLAY_NAME="TabulexFlow (Local Test - DO NOT DISTRIBUTE)"
    COMMENT="TabulexFlow LOCAL TEST build (backend 127.0.0.1). FOR DEVELOPMENT ONLY - NOT FOR DISTRIBUTION"
else
    FLAVOR="production"
fi

# 判定打包模式：exe 同目录存在 _internal → onedir；否则 onefile
if [ -d "$(dirname "$EXE_PATH")/_internal" ]; then
    MODE="onedir"
    echo "  Artifact type / 产物类型   : $FLAVOR / onedir（含 _internal 目录，将整目录安装）"
else
    MODE="onefile"
    echo "  Artifact type / 产物类型   : $FLAVOR / onefile（单文件）"
fi

# Local Test 禁止分发，安全确认（可用 TFP_PACKAGE_ALLOW_DEV=1 跳过）
if [ "$FLAVOR" = "devtest" ]; then
    echo ""
    echo "  ⚠️  Warning: packaging a Local Test (-devtest) artifact whose backend is hardcoded to http://127.0.0.1:8080, / 警告：当前打包的是 Local Test（-devtest）产物，其后端地址固化 http://127.0.0.1:8080，"
    echo "      This is a dev-test build that must not be distributed externally, for local installation verification only! / 属于【禁止对外分发】的开发测试版，仅可用于本地安装验证！"
    if [ "${TFP_PACKAGE_ALLOW_DEV:-0}" != "1" ]; then
        if [ -t 0 ]; then
            read -rp "  Confirm packaging for local testing only? [y/N] / 确认仅为本地测试而打包？[y/N]: " ans
        else
            ans=""
        fi
        case "${ans:-n}" in
            [yY]) : ;;
            *) echo "  Cancelled (to package Local Test automatically, set TFP_PACKAGE_ALLOW_DEV=1) / 已取消（如需自动化打包 Local Test，设 TFP_PACKAGE_ALLOW_DEV=1）。"; exit 1 ;;
        esac
    fi
    echo ""
fi

# ==========================================
# 1.1 OSS 合规（L-8）：打包前清理 dist 内可能残留的敏感凭据文件
# tfp_secure_storage 在 frozen 模式下把 fallback 凭据（如 .auth_token）写到
# exe 同级 config/ 目录；若曾在构建机本机测试运行过产物，可能残留在 dist/ 内。
# ==========================================
SENSITIVE_FOUND=$(find "$DIST_DIR" -type f \( \
    -name ".auth_*" -o -name "*.auth_token" -o -name ".session*" -o \
    -name ".tfp_fernet_key" -o -name "*.key" -o -name "*.pem" -o -name "credentials*" \) 2>/dev/null)
if [ -n "$SENSITIVE_FOUND" ]; then
    echo "  [SECURITY] Found and deleted residual sensitive credential files in dist / 发现并删除 dist 内残留的敏感凭据文件:"
    echo "$SENSITIVE_FOUND" | while read -r sf; do
        rm -f "$sf" && echo "    deleted: $sf"
    done
fi

# OSS 合规（L-8）补充：同时清理源码树 config/ 内运行时残留的凭据文件
# （本脚本可脱离 tfpdesktop_build.sh 单独执行，需独立兜底；仅删除运行时残留命名模式，
#  如 .auth_token、.tfp_fernet_key，不影响正常配置文件）
shopt -s nullglob
for _residual in "$PROJECT_DIR"/config/.auth_* "$PROJECT_DIR"/config/.session* "$PROJECT_DIR"/config/.tfp_fernet_key; do
    rm -f "$_residual"
    echo "  [SECURITY] deleted source-tree residual credential file: $_residual"
done
shopt -u nullglob

# 方案A补充：移除 dist 内运行时用户数据（user_setting/<用户id>/...），防止随安装包分发账号身份
for _us in "$DIST_DIR/user_setting" "$(dirname "$EXE_PATH")/user_setting"; do
    if [ -d "$_us" ]; then
        rm -rf "$_us"
        echo "  [SECURITY] removed runtime user data: $_us / 已移除运行时用户数据"
    fi
done

# ==========================================
# 2. 读取版本号（单一来源：config/version.txt 的 ProductVersion，共享 helper）
# ==========================================
VERSION="$(python3 "$SCRIPT_PATH/scripts_py/tfpdesktop_version.py" "$PROJECT_DIR" 2>/dev/null || true)"
VERSION="${VERSION:-1.0.0}"
# Debian 版本号规则：只允许字母数字 + . + - + ~，且不允许以 - 开头
DEB_VERSION=$(printf '%s' "$VERSION" | sed 's/[^0-9A-Za-z.~+-]/-/g')
echo "  Version / 版本号     : $VERSION (deb 用 $DEB_VERSION)"

# ==========================================
# 3. 生成多尺寸 PNG 图标（Pillow 转换 app_icon.ico）
# ==========================================
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ICON_DIR="$WORK/icons"
mkdir -p "$ICON_DIR"

if ! python3 -c "import PIL" 2>/dev/null; then
    echo "  [WARN] Pillow not found; cannot generate PNG icons; will try system convert/magick / 未找到 Pillow，无法生成 PNG 图标；将尝试用系统 convert/magick"
    for t in convert magick; do
        if command -v "$t" >/dev/null 2>&1; then
            "$t" "$ICON_SRC" -define icon:auto-resize=256,128,64 "$ICON_DIR/icon-%d.png" 2>/dev/null || true
            break
        fi
    done
fi
# Pillow 生成（最可靠）：取 ico 最大帧，缩放到各尺寸
python3 - "$ICON_SRC" "$ICON_DIR" <<'PYEOF'
import sys
from PIL import Image
src, out_dir = sys.argv[1], sys.argv[2]
img = Image.open(src)
# ico 可能是多帧，取尺寸最大的一帧
frames = []
try:
    while True:
        frames.append((img.size[0] * img.size[1], img.copy()))
        img.seek(img.tell() + 1)
except EOFError:
    pass
if frames:
    img = max(frames, key=lambda x: x[0])[1]
img = img.convert("RGBA")
for size in (512, 256, 128, 64, 48, 32):
    im = img.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.size[0]) // 2, (size - im.size[1]) // 2), im)
    canvas.save(f"{out_dir}/icon-{size}.png")
print("PNG icons generated")
PYEOF
echo "  Icons / 图标       : 已生成多尺寸 PNG"

# ==========================================
# 4. 构建原生安装包（Debian 系 → .deb；Red Hat 系 → .rpm）
# ==========================================
if [ "$DISTRO_FAMILY" = "debian" ]; then
echo ""
echo "=========================================="
echo " Building .deb package / 构建 .deb 安装包"
echo "=========================================="
DEB_ROOT="$WORK/deb_root"
DEB_OUT="$DIST_DIR/${PKG_NAME}_${DEB_VERSION}_${ARCH_DEB}.deb"
mkdir -p "$DEB_ROOT/usr/bin" \
         "$DEB_ROOT/usr/share/applications" \
         "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps" \
         "$DEB_ROOT/usr/share/icons/hicolor/128x128/apps" \
         "$DEB_ROOT/usr/share/icons/hicolor/64x64/apps" \
         "$DEB_ROOT/usr/share/doc/$PKG_NAME" \
         "$DEB_ROOT/DEBIAN"

if [ "$MODE" = "onedir" ]; then
    # onedir：整目录（可执行文件 + _internal/）安装到 /usr/lib/$PKG_NAME/，/usr/bin 用软链
    SRC_EXE_DIR="$(dirname "$EXE_PATH")"
    LIB_DEST="$DEB_ROOT/usr/lib/$PKG_NAME"
    mkdir -p "$LIB_DEST"
    cp -a "$SRC_EXE_DIR/." "$LIB_DEST/"
    chmod -R u+w "$LIB_DEST" 2>/dev/null || true
    chmod 755 "$LIB_DEST/$EXE_NAME"
    ln -s "/usr/lib/$PKG_NAME/$EXE_NAME" "$DEB_ROOT/usr/bin/$PKG_NAME"
    echo "  [onedir] Installed the whole directory to /usr/lib/$PKG_NAME/ (incl. _internal); /usr/bin/$PKG_NAME -> symlink / 已安装整目录到 /usr/lib/$PKG_NAME/（含 _internal），/usr/bin/$PKG_NAME -> 软链"
else
    cp "$EXE_PATH" "$DEB_ROOT/usr/bin/$PKG_NAME"
    chmod 755 "$DEB_ROOT/usr/bin/$PKG_NAME"
fi

cp "$ICON_DIR/icon-256.png" "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps/$PKG_NAME.png"
cp "$ICON_DIR/icon-128.png" "$DEB_ROOT/usr/share/icons/hicolor/128x128/apps/$PKG_NAME.png"
cp "$ICON_DIR/icon-64.png"  "$DEB_ROOT/usr/share/icons/hicolor/64x64/apps/$PKG_NAME.png"

cat > "$DEB_ROOT/usr/share/applications/$PKG_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$DISPLAY_NAME
Name[zh_CN]=灵表（TabulexFlow）
GenericName=$DISPLAY_NAME
Comment=$COMMENT
Comment[zh_CN]=灵表（TabulexFlow） - 开源前端（含内置工具）
Exec=$PKG_NAME
Icon=$PKG_NAME
Terminal=false
Categories=$CATEGORIES
StartupNotify=false
EOF

# 版权/许可页
if [ -f "$LICENSE_SRC" ]; then
    cp "$LICENSE_SRC" "$DEB_ROOT/usr/share/doc/$PKG_NAME/copyright"
else
    cat > "$DEB_ROOT/usr/share/doc/$PKG_NAME/copyright" <<'EOF'
This package is part of the TabulexFlow open-source project.
License: GNU Affero General Public License v3 or later (AGPL-3.0-or-later)
See https://www.gnu.org/licenses/agpl-3.0.html for the full license text.
EOF
fi

# OSS 合规（AGPL §6 第三方声明，M-6.1）：随包分发第三方依赖声明与完整许可证文本
if [ -f "$PROJECT_DIR/docs/NOTICE.txt" ]; then
    cp "$PROJECT_DIR/docs/NOTICE.txt" "$DEB_ROOT/usr/share/doc/$PKG_NAME/NOTICE.txt"
else
    echo "  [WARN] docs/NOTICE.txt not found; deb package will lack the third-party notice file / docs/NOTICE.txt 不存在，deb 包内将缺少第三方声明文件"
fi
if [ -f "$LICENSE_SRC" ]; then
    cp "$LICENSE_SRC" "$DEB_ROOT/usr/share/doc/$PKG_NAME/LICENSE.txt"
fi

cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $DEB_VERSION
Section: utils
Priority: optional
Architecture: $ARCH_DEB
Maintainer: TabulexFlow Developers <dev@tabulexflow.com>
Installed-Size: $(du -sk "$DEB_ROOT/usr" | awk '{print $1}')
Depends: libc6 (>= 2.17), libgtk-3-0 (>= 3.22)
Description: $COMMENT
  Open-source frontend main program with BuiltinProgram tools.
  Community (OSS) edition: no login, no backend, no remote tools.
  .
  Built with PyInstaller (self-contained Python runtime).
EOF

dpkg-deb --build --root-owner-group "$DEB_ROOT" "$DEB_OUT"
echo "  [OK] Generated: $DEB_OUT / 已生成: $DEB_OUT"
NATIVE_PKG_OUT="$DEB_OUT"
NATIVE_PKG_KIND="deb"

else
# ==========================================
# 4'. Red Hat 系：构建 .rpm 安装包（rpmbuild）
# ==========================================
echo ""
echo "=========================================="
echo " Building .rpm package / 构建 .rpm 安装包"
echo "=========================================="
if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "  [FAIL] rpmbuild not found; install it first: sudo dnf install rpm-build / 未找到 rpmbuild，请先安装: sudo dnf install rpm-build"
    exit 1
fi

# RPM 版本号规则：只允许字母数字 + . _ + ~，不接受 '-'
RPM_VERSION="$(printf '%s' "$VERSION" | sed 's/[^0-9A-Za-z._+~]/./g; s/^\.*//')"
RPM_VERSION="${RPM_VERSION:-1.0.0}"

STAGE="$WORK/rpm_stage"
mkdir -p "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps" \
         "$STAGE/usr/share/icons/hicolor/128x128/apps" \
         "$STAGE/usr/share/icons/hicolor/64x64/apps" \
         "$STAGE/usr/share/doc/$PKG_NAME"

if [ "$MODE" = "onedir" ]; then
    # onedir：整目录安装到 /usr/lib/$PKG_NAME/，/usr/bin 用软链
    SRC_EXE_DIR="$(dirname "$EXE_PATH")"
    mkdir -p "$STAGE/usr/lib/$PKG_NAME"
    cp -a "$SRC_EXE_DIR/." "$STAGE/usr/lib/$PKG_NAME/"
    chmod -R u+w "$STAGE/usr/lib/$PKG_NAME" 2>/dev/null || true
    chmod 755 "$STAGE/usr/lib/$PKG_NAME/$EXE_NAME"
    ln -s "/usr/lib/$PKG_NAME/$EXE_NAME" "$STAGE/usr/bin/$PKG_NAME"
    echo "  [onedir] Installed the whole directory to /usr/lib/$PKG_NAME/ (incl. _internal); /usr/bin/$PKG_NAME -> symlink / 已安装整目录到 /usr/lib/$PKG_NAME/（含 _internal），/usr/bin/$PKG_NAME -> 软链"
else
    cp "$EXE_PATH" "$STAGE/usr/bin/$PKG_NAME"
    chmod 755 "$STAGE/usr/bin/$PKG_NAME"
fi

cp "$ICON_DIR/icon-256.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/$PKG_NAME.png"
cp "$ICON_DIR/icon-128.png" "$STAGE/usr/share/icons/hicolor/128x128/apps/$PKG_NAME.png"
cp "$ICON_DIR/icon-64.png"  "$STAGE/usr/share/icons/hicolor/64x64/apps/$PKG_NAME.png"

cat > "$STAGE/usr/share/applications/$PKG_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$DISPLAY_NAME
Name[zh_CN]=灵表（TabulexFlow）
GenericName=$DISPLAY_NAME
Comment=$COMMENT
Comment[zh_CN]=灵表（TabulexFlow） - 开源前端（含内置工具）
Exec=$PKG_NAME
Icon=$PKG_NAME
Terminal=false
Categories=$CATEGORIES
StartupNotify=false
EOF

# 版权/许可页（与 .deb 一致）
if [ -f "$LICENSE_SRC" ]; then
    cp "$LICENSE_SRC" "$STAGE/usr/share/doc/$PKG_NAME/copyright"
else
    cat > "$STAGE/usr/share/doc/$PKG_NAME/copyright" <<'EOF'
This package is part of the TabulexFlow open-source project.
License: GNU Affero General Public License v3 or later (AGPL-3.0-or-later)
See https://www.gnu.org/licenses/agpl-3.0.html for the full license text.
EOF
fi
if [ -f "$PROJECT_DIR/docs/NOTICE.txt" ]; then
    cp "$PROJECT_DIR/docs/NOTICE.txt" "$STAGE/usr/share/doc/$PKG_NAME/NOTICE.txt"
else
    echo "  [WARN] docs/NOTICE.txt not found; rpm package will lack the third-party notice file / docs/NOTICE.txt 不存在，rpm 包内将缺少第三方声明文件"
fi
if [ -f "$LICENSE_SRC" ]; then
    cp "$LICENSE_SRC" "$STAGE/usr/share/doc/$PKG_NAME/LICENSE.txt"
fi

# 组装 %files 清单（按打包模式与可选文件存在性动态生成）
RPM_FILES="/usr/bin/$PKG_NAME
/usr/share/applications/$PKG_NAME.desktop
/usr/share/icons/hicolor/256x256/apps/$PKG_NAME.png
/usr/share/icons/hicolor/128x128/apps/$PKG_NAME.png
/usr/share/icons/hicolor/64x64/apps/$PKG_NAME.png
/usr/share/doc/$PKG_NAME/copyright"
if [ "$MODE" = "onedir" ]; then
    RPM_FILES="$RPM_FILES
/usr/lib/$PKG_NAME"
fi
if [ -f "$STAGE/usr/share/doc/$PKG_NAME/LICENSE.txt" ]; then
    RPM_FILES="$RPM_FILES
/usr/share/doc/$PKG_NAME/LICENSE.txt"
fi
if [ -f "$STAGE/usr/share/doc/$PKG_NAME/NOTICE.txt" ]; then
    RPM_FILES="$RPM_FILES
/usr/share/doc/$PKG_NAME/NOTICE.txt"
fi

RPM_TOPDIR="$WORK/rpmbuild"
mkdir -p "$RPM_TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
RPM_SPEC="$RPM_TOPDIR/SPECS/$PKG_NAME.spec"
cat > "$RPM_SPEC" <<EOF
Name:           $PKG_NAME
Version:        $RPM_VERSION
Release:        1
Summary:        $COMMENT
License:        AGPL-3.0-or-later
URL:            https://tabulexflow.com
AutoReqProv:    no
Requires:       glibc >= 2.17, gtk3
BuildArch:      $ARCH_RPM

%description
Open-source TabulexFlow frontend main program with BuiltinProgram tools.
Community (OSS) edition: no login, no backend, no remote tools.
Built with PyInstaller (self-contained Python runtime).

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a "$STAGE/." "%{buildroot}/"

%files
$RPM_FILES
EOF

rpmbuild -bb --define "_topdir $RPM_TOPDIR" "$RPM_SPEC"
RPM_BUILT="$(find "$RPM_TOPDIR/RPMS" -type f -name '*.rpm' | head -n 1)"
if [ -z "$RPM_BUILT" ]; then
    echo "  [FAIL] rpmbuild did not produce an .rpm / rpmbuild 未生成 .rpm"
    exit 1
fi
RPM_OUT="$DIST_DIR/$PKG_NAME.$ARCH_RPM.rpm"
cp -f "$RPM_BUILT" "$RPM_OUT"
echo "  [OK] Generated: $RPM_OUT / 已生成: $RPM_OUT"
NATIVE_PKG_OUT="$RPM_OUT"
NATIVE_PKG_KIND="rpm"
fi

# ==========================================
# 5. 构建 .AppImage 免安装包
# ==========================================
echo ""
echo "=========================================="
echo " Building .AppImage portable package / 构建 .AppImage 免安装包"
echo "=========================================="
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/doc/$PKG_NAME"

APP_BIN_REL=""   # AppRun 实际执行的相对路径（相对 AppDir）
if [ "$MODE" = "onedir" ]; then
    LIB_DEST_AI="$APPDIR/usr/lib/$PKG_NAME"
    mkdir -p "$LIB_DEST_AI"
    SRC_EXE_DIR="$(dirname "$EXE_PATH")"
    cp -a "$SRC_EXE_DIR/." "$LIB_DEST_AI/"
    chmod 755 "$LIB_DEST_AI/$EXE_NAME"
    APP_BIN_REL="usr/lib/$PKG_NAME/$EXE_NAME"
    echo "  [onedir] Installed the whole directory into AppImage usr/lib/$PKG_NAME/ / 已整目录装入 AppImage usr/lib/$PKG_NAME/"
else
    cp "$EXE_PATH" "$APPDIR/usr/bin/$PKG_NAME"
    chmod 755 "$APPDIR/usr/bin/$PKG_NAME"
    APP_BIN_REL="usr/bin/$PKG_NAME"
fi

cp "$ICON_DIR/icon-256.png" "$APPDIR/$PKG_NAME.png"

# OSS 合规（AGPL §5(a)/§6，M-6.2）：随包分发完整许可证与第三方声明文件
if [ -f "$LICENSE_SRC" ]; then
    cp "$LICENSE_SRC" "$APPDIR/usr/share/doc/$PKG_NAME/LICENSE.txt"
else
    echo "  [WARN] LICENSE.txt not found; AppImage will lack the full license text / LICENSE.txt 不存在，AppImage 内将缺少许可证全文"
fi
if [ -f "$PROJECT_DIR/docs/NOTICE.txt" ]; then
    cp "$PROJECT_DIR/docs/NOTICE.txt" "$APPDIR/usr/share/doc/$PKG_NAME/NOTICE.txt"
else
    echo "  [WARN] docs/NOTICE.txt not found; AppImage will lack the third-party notice file / docs/NOTICE.txt 不存在，AppImage 内将缺少第三方声明文件"
fi

cat > "$APPDIR/$PKG_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$DISPLAY_NAME
Name[zh_CN]=灵表（TabulexFlow）
GenericName=$DISPLAY_NAME
Comment=$COMMENT
Comment[zh_CN]=灵表（TabulexFlow） - 开源前端（含内置工具）
Exec=$PKG_NAME
Icon=$PKG_NAME
Terminal=false
Categories=$CATEGORIES
StartupNotify=false
EOF

# AppRun：把 AppImage 内路径加入 PATH 并启动实际可执行文件
# OSS 合规（M-6.2）：设置 XDG_DATA_DIRS 指向 AppImage 内部数据目录，便于桌面环境/工具发现随包的文档与许可信息
cat > "$APPDIR/AppRun" <<EOF
#!/bin/sh
SELF="\$(readlink -f "\$0")"
APPDIR="\$(dirname "\$SELF")"
export PATH="\$APPDIR/usr/bin:\$PATH"
export LD_LIBRARY_PATH="\$APPDIR/usr/lib:\${LD_LIBRARY_PATH:-}"
export XDG_DATA_DIRS="\$APPDIR/usr/share:\${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
exec "\$APPDIR/$APP_BIN_REL" "\$@"
EOF
chmod 755 "$APPDIR/AppRun"

# 复用产物名（<名称>-<版本>-<形态>[-devtest]）以保持命名一致，如 TabulexFlow-1.0.0-OSS-x86_64.AppImage
APPIMAGE_OUT="$DIST_DIR/${EXE_NAME}-${ARCH_APPIMAGE}.AppImage"

# 定位 appimagetool：PATH / 缓存 / 自动下载
APPIMAGETOOL=""
if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
elif [ -x "$APPIMAGETOOL_CACHE" ]; then
    APPIMAGETOOL="$APPIMAGETOOL_CACHE"
else
    echo "  appimagetool not found; trying auto-download to $APPIMAGETOOL_CACHE ... / 未找到 appimagetool，尝试自动下载到 $APPIMAGETOOL_CACHE ..."
    mkdir -p "$TOOLS_DIR"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 2 -o "$APPIMAGETOOL_CACHE" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH_APPIMAGE.AppImage" \
            && chmod 755 "$APPIMAGETOOL_CACHE" \
            && APPIMAGETOOL="$APPIMAGETOOL_CACHE" || echo "  [WARN] appimagetool download failed / appimagetool 下载失败"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$APPIMAGETOOL_CACHE" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH_APPIMAGE.AppImage" \
            && chmod 755 "$APPIMAGETOOL_CACHE" \
            && APPIMAGETOOL="$APPIMAGETOOL_CACHE" || echo "  [WARN] appimagetool download failed / appimagetool 下载失败"
    else
        echo "  [WARN] No curl/wget; cannot download appimagetool / 无 curl/wget，无法下载 appimagetool"
    fi
fi

if [ -n "$APPIMAGETOOL" ]; then
    # --appimage-extract-and-run：避免依赖 FUSE
    if ARCH="$ARCH_APPIMAGE" "$APPIMAGETOOL" --appimage-extract-and-run \
        "$APPDIR" "$APPIMAGE_OUT" >/dev/null 2>&1; then
        echo "  [OK] Generated: $APPIMAGE_OUT / 已生成: $APPIMAGE_OUT"
    else
        echo "  [WARN] appimagetool failed; keeping the unpacked AppDir: $WORK/AppDir / appimagetool 执行失败，保留未打包的 AppDir: $WORK/AppDir"
        trap - EXIT
        echo "        AppDir kept at: $WORK/AppDir (can be packaged manually with appimagetool) / AppDir 留在: $WORK/AppDir（可手动用 appimagetool 打包）"
    fi
else
    echo "  [WARN] Missing appimagetool; skipping AppImage generation / 缺少 appimagetool，跳过 AppImage 生成"
    echo "        AppDir fully built (.desktop + icons + AppRun complete): $WORK/AppDir / 已构建好 AppDir（.desktop + 图标 + AppRun 完整）：$WORK/AppDir"
    echo "        You can run it manually after installing appimagetool later / 可稍后安装 appimagetool 后手动执行:"
    echo "          appimagetool \"$WORK/AppDir\" \"$APPIMAGE_OUT\""
fi

# ==========================================
# 6. 生成 SHA256 校验和与 GPG 签名（Linux 发布完整性保障）
#    - SHA256SUMS.txt：所有发布产物的哈希清单（无 GPG 环境也可供用户校验）
#    - SHA256SUMS.gpg：分离签名（若本机配置了 GPG 私钥则自动生成，签名对象为 SHA256SUMS.txt）
#    用户校验方法见 README.md "校验下载文件 / Verify Downloads" 章节。
# ==========================================
echo ""
echo "=========================================="
echo " Generating SHA256 checksums and GPG signature / 生成 SHA256 校验和与 GPG 签名"
echo "=========================================="
SUMS_FILE="$DIST_DIR/SHA256SUMS.txt"
# 合并式写入：仅移除同平台（Linux：以 .deb/.rpm/.AppImage 结尾）旧记录，以及与本次
# 新产物相对路径完全相同的旧记录（覆盖无扩展名的 onefile 二进制）；保留另一平台
# （Windows）及其他记录，再追加本次新产物记录，两平台互不覆盖。
# 纳入清单：原生安装包（.deb 或 .rpm）+ .AppImage；onefile 额外纳入原始单文件产物
SUMS_ITEMS=("$NATIVE_PKG_OUT" "$APPIMAGE_OUT")
if [ "$MODE" = "onefile" ]; then
    SUMS_ITEMS+=("$EXE_PATH")
fi
SUMS_PAIRS=()
for artifact in "${SUMS_ITEMS[@]}"; do
    if [ -f "$artifact" ]; then
        SUMS_PAIRS+=("$(basename "$artifact")=$artifact")
        echo "  Added to manifest: $(basename "$artifact") / 已加入清单: $(basename "$artifact")"
    fi
done
if [ "${#SUMS_PAIRS[@]}" -gt 0 ]; then
    python3 "$SCRIPT_PATH/scripts_py/tfpdesktop_checksum_manifest.py" \
        --platform linux --manifest "$SUMS_FILE" "${SUMS_PAIRS[@]}"
fi
echo "  [OK] Checksum manifest: $SUMS_FILE / 校验和清单: $SUMS_FILE"

# GPG 签名（可选）：优先使用环境变量 GPG_SIGN_ID 指定的密钥，
# 否则使用本机默认私钥（仅当存在密钥时）；两者皆无则跳过并给出提示。
if command -v gpg >/dev/null 2>&1; then
    GPG_ARGS=()
    CAN_SIGN=0
    if [ -n "${GPG_SIGN_ID:-}" ]; then
        GPG_ARGS=(--local-user "$GPG_SIGN_ID")
        CAN_SIGN=1
    elif gpg --list-secret-keys --with-colons 2>/dev/null | grep -q "^sec:"; then
        CAN_SIGN=1
    fi
    if [ "$CAN_SIGN" -eq 1 ]; then
        if gpg --batch --yes --detach-sign --armor \
               "${GPG_ARGS[@]}" -o "$DIST_DIR/SHA256SUMS.gpg" "$SUMS_FILE" 2>/dev/null; then
            echo "  [OK] GPG detached signature: $DIST_DIR/SHA256SUMS.gpg / GPG 分离签名: $DIST_DIR/SHA256SUMS.gpg"
        else
            echo "  [WARN] GPG signing failed (if the key passphrase needs interactive input, use gpg-agent or pre-configured signpass); only SHA256SUMS.txt is provided / GPG 签名失败（密钥口令需要交互输入时请使用 gpg-agent 或预先 signpass），仅提供 SHA256SUMS.txt"
            rm -f "$DIST_DIR/SHA256SUMS.gpg"
        fi
    else
        echo "  [INFO] No GPG private key on this machine; skipping signature (users can still verify integrity with SHA256SUMS.txt) / 本机无 GPG 私钥，跳过签名（用户仍可用 SHA256SUMS.txt 校验完整性）"
        echo "         To sign: run gpg --full-generate-key then rerun this script, or export GPG_SIGN_ID=<key-ID> / 如需签名：gpg --full-generate-key 后重跑本脚本，或 export GPG_SIGN_ID=<密钥ID>"
    fi
else
    echo "  [INFO] gpg not installed; skipping signature / 未安装 gpg，跳过签名"
fi

# ==========================================
# 7. 汇总
# ==========================================
echo ""
echo "=========================================="
echo " Packaging complete / 打包完成"
echo "=========================================="
echo "  Artifact type / 产物类型   : $FLAVOR / $MODE"
echo "  .$NATIVE_PKG_KIND package / .$NATIVE_PKG_KIND 安装包 : $NATIVE_PKG_OUT"
if [ "$NATIVE_PKG_KIND" = "deb" ]; then
    echo "    Install: sudo apt install $NATIVE_PKG_OUT   or  double-click to install / 安装: sudo apt install $NATIVE_PKG_OUT   或  双击安装"
    echo "    Remove: sudo apt remove $PKG_NAME / 卸载: sudo apt remove $PKG_NAME"
else
    echo "    Install: sudo dnf install $NATIVE_PKG_OUT / 安装: sudo dnf install $NATIVE_PKG_OUT"
    echo "    Remove: sudo dnf remove $PKG_NAME / 卸载: sudo dnf remove $PKG_NAME"
fi
echo ""
if [ -f "$APPIMAGE_OUT" ]; then
    echo "  .AppImage   : $APPIMAGE_OUT"
fi
echo "    Run: chmod +x <file> && ./<file> / 运行: chmod +x <文件> && ./<文件>"
echo ""
echo "  Integrity checksum / 完整性校验  : $DIST_DIR/SHA256SUMS.txt"
if [ -f "$DIST_DIR/SHA256SUMS.gpg" ]; then
    echo "  GPG signature / GPG 签名    : $DIST_DIR/SHA256SUMS.gpg（校验方法见 README.md）"
fi
echo ""
if [ "$FLAVOR" = "devtest" ]; then
    echo "  ⚠️  Warning: this is a Local Test (-devtest) build with backend hardcoded to 127.0.0.1, / 警告：本包为 Local Test（-devtest）构建，后端固化 127.0.0.1，"
    echo "      Do NOT publish externally; for local installation verification only! / 禁止对外发布，仅供本地安装验证！"
fi
echo "  Note: the packaged artifact is based on the currently compiled binary (OSS community edition has no backend/login/remote tools). / 提示: 打包产物基于当前已编译二进制（OSS 社区版不含后端/登录/远程工具）。"