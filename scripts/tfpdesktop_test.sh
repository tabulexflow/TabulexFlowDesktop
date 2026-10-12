#!/usr/bin/env bash
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
# tfpdesktop_test.sh - Run TabulexFlowDesktop frontend tests (Linux/macOS)
# Equivalent to tfpdesktop_test.bat
#
# Usage:
#   bash tfpdesktop_test.sh                        # run all tests (interactive menu)
#   bash tfpdesktop_test.sh tests/test_config.py   # run a single test file
#   bash tfpdesktop_test.sh -k config              # pass through pytest options
# 覆盖率汇总在启动时的交互菜单中选择，无需传参。
set -euo pipefail

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_PATH/.." && pwd)"
# 本地 Python 环境路径，可用环境变量 TFP_VENV 覆盖（默认为前端工程目录内的 venv：$PROJECT_DIR/venv）：
#   export TFP_VENV=/path/to/your/py312-venv
# venv 需已安装 requirements.txt 依赖（含 pytest）。
PYTHON_VENV="${TFP_VENV:-$PROJECT_DIR/venv}"
# 测试日志固定路径，每次运行先清空（仅保留本次输出）
LOG_FILE="$PROJECT_DIR/logs/tfpdesktop_test.log"

clear 2>/dev/null || true

echo "========================================"
echo "TabulexFlow - Frontend Tests"
echo "========================================"
echo ""
echo "  请选择测试模式："
echo "    [1] 仅运行测试（默认，速度优先）"
echo "    [2] 运行测试并汇总覆盖率（耗时明显增加）"
read -r -p "  请输入选项 [1]: " cov_choice || true
cov_enable=0
if [ "${cov_choice:-}" = "2" ]; then
    cov_enable=1
fi
echo ""

cd "$PROJECT_DIR" || { echo "  [FAIL] Could not switch to frontend dir"; exit 1; }

if [ ! -d "$PYTHON_VENV/bin" ]; then
    echo "  [FAIL] Python venv not found: $PYTHON_VENV"
    echo "        Set env TFP_VENV to your venv path, e.g.:"
    echo "          export TFP_VENV=/path/to/your/py312-venv"
    exit 1
fi

source "$PYTHON_VENV/bin/activate" || { echo "  [FAIL] Could not activate venv: $PYTHON_VENV"; exit 1; }

if [ "${VIRTUAL_ENV:-}" != "$PYTHON_VENV" ]; then
    echo "  [FAIL] Python venv activation failed (VIRTUAL_ENV != $PYTHON_VENV)"
    exit 1
fi

if ! python3 -c "import pytest" 2>/dev/null; then
    echo "  [FAIL] pytest not installed in $PYTHON_VENV"
    echo "        Install frontend test dependencies:"
    echo "          $PYTHON_VENV/bin/pip install -r requirements.txt"
    echo "          $PYTHON_VENV/bin/pip install pytest"
    exit 1
fi

# 区分 pytest 目标与选项：指定了测试路径/文件则只收集该目标，
# 仅传选项（如 -k / -v）则仍走 pytest.ini 的 testpaths（tests/）
# 覆盖率由启动时交互菜单决定；pytest-cov 未在 requirements.txt 声明，需自行安装。
pytest_todo=()
have_target=0
for arg in "$@"; do
    case "$arg" in
        -*) pytest_todo+=("$arg") ;;
        *)  pytest_todo+=("$arg"); have_target=1 ;;
    esac
done
if [ "$cov_enable" -eq 1 ]; then
    if ! python3 -c "import pytest_cov" 2>/dev/null; then
        echo "  [FAIL] pytest-cov not installed in $PYTHON_VENV"
        echo "          $PYTHON_VENV/bin/pip install pytest-cov"
        exit 1
    fi
    pytest_todo+=(--cov=tfp_auth --cov=tfp_utils --cov=tfp_toolkit --cov=tfp_mixins --cov-report=term:skip-covered)
fi
if [ "$have_target" -eq 0 ]; then
    pytest_todo+=("tests/")
fi

mkdir -p "$(dirname "$LOG_FILE")" || { echo "  [FAIL] Could not create log dir: $(dirname "$LOG_FILE")"; exit 1; }
: > "$LOG_FILE" || { echo "  [FAIL] Could not clear log file: $LOG_FILE"; exit 1; }

pytest_rc=0
set +e
python3 -m pytest "${pytest_todo[@]}" 2>&1 | tee "$LOG_FILE"
pytest_rc=${PIPESTATUS[0]}
set -e

echo ""
if [ "$pytest_rc" -eq 0 ]; then
    echo "  [OK] All frontend tests passed" | tee -a "$LOG_FILE"
else
    echo "  [FAIL] Frontend tests failed (exit code: $pytest_rc)" | tee -a "$LOG_FILE"
fi
echo "  Test log: $LOG_FILE"

exit "$pytest_rc"
