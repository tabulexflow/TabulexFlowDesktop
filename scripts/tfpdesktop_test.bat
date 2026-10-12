:: Copyright (C) 2024-present TabulexFlow Team
:: SPDX-License-Identifier: AGPL-3.0-or-later
:: tfpdesktop_test.bat - Run TabulexFlowDesktop frontend tests (Windows)
:: Equivalent to tfpdesktop_test.sh
::
:: Usage:
::   tfpdesktop_test.bat                            - run all tests
::   tfpdesktop_test.bat tests\test_config.py       - run a single test file
::   tfpdesktop_test.bat -k config                  - pass through pytest options
:: 覆盖率汇总在启动时的交互菜单中选择，无需传参。
:: 注意：字符编码是ANSI，确保在Windows上运行，不是UTF-8编码
:: 重要：本文件必须保持 CRLF 行尾符保存！cmd.exe 解析 .bat 严格要求 CRLF，
:: LF-only 会导致 goto/括号块解析错乱（本仓库 .bat 统一使用 CRLF 行尾）。
@echo off
chcp 65001 >nul
echo ========================================
echo TabulexFlow - Frontend Tests
echo ========================================
echo.
echo   请选择测试模式：
echo     [1] 仅运行测试（默认，速度优先）
echo     [2] 运行测试并汇总覆盖率（耗时明显增加）
set "COV_CHOICE="
set /p "COV_CHOICE=  请输入选项 [1]: "
set "COV_ENABLE=0"
if "%COV_CHOICE%"=="2" set "COV_ENABLE=1"
echo.

set "scriptPath=%~dp0"
:: 工程根目录在脚本上级目录 TabulexFlowDesktop\
cd /d "%scriptPath%.."
for %%I in ("%scriptPath%..") do set "PROJECT_DIR=%%~fI"
:: 测试日志固定路径，每次运行先清空（仅保留本次输出）
set "LOG_FILE=%PROJECT_DIR%\logs\tfpdesktop_test.log"

call conda activate py312tf

:: 覆盖率由启动时交互菜单决定；pytest-cov 未在 requirements.txt 声明，需自行安装。
set "COV_OPTS="
if "%COV_ENABLE%"=="1" (
    python -c "import pytest_cov" >nul 2>&1
    if errorlevel 1 (
        echo   [FAIL] pytest-cov not installed in py312tf
        echo          pip install pytest-cov
        exit /b 1
    )
    set "COV_OPTS=--cov=tfp_auth --cov=tfp_utils --cov=tfp_toolkit --cov=tfp_mixins --cov-report=term:skip-covered"
)

if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"
type nul > "%LOG_FILE%"

python -m pytest tests\ %* %COV_OPTS% > "%LOG_FILE%" 2>&1
set "pytest_rc=%errorlevel%"

type "%LOG_FILE%"
echo.
if %pytest_rc% equ 0 (
    echo   [OK] All frontend tests passed
) else (
    echo   [FAIL] Frontend tests failed ^(exit code: %pytest_rc%^)
)
echo   Test log: %LOG_FILE%

exit /b %pytest_rc%
