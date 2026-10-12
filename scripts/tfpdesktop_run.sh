#!/usr/bin/env bash
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
# tfpdesktop.sh - Start TabulexFlowDesktop frontend (source mode, Linux/macOS)
# Equivalent to tfpdesktop.bat
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_PATH/.." && pwd)"
# 本地 Python 环境路径，可用环境变量 TFP_VENV 覆盖（默认为前端工程目录内的 venv：$PROJECT_DIR/venv）：
#   export TFP_VENV=/path/to/your/py312-venv
# venv 需已安装 requirements.txt 依赖。
PYTHON_VENV="${TFP_VENV:-$PROJECT_DIR/venv}"

clear

cd "$PROJECT_DIR" || { echo "  [FAIL] Could not switch to frontend dir"; exit 1; }

if [ ! -d "$PYTHON_VENV/bin" ]; then
    echo "  [FAIL] Python venv not found: $PYTHON_VENV"
    exit 1
fi

source "$PYTHON_VENV/bin/activate" || { echo "  [FAIL] Could not activate venv: $PYTHON_VENV"; exit 1; }

if [ "${VIRTUAL_ENV:-}" != "$PYTHON_VENV" ]; then
    echo "  [FAIL] Python venv activation failed (VIRTUAL_ENV != $PYTHON_VENV)"
    exit 1
fi

if ! python3 -c "import wx" 2>/dev/null; then
    echo "  [FAIL] wxPython not installed in $PYTHON_VENV"
    echo "        Install frontend dependencies:"
    echo "          $PYTHON_VENV/bin/pip install -r requirements.txt"
    exit 1
fi

python3 main.py
