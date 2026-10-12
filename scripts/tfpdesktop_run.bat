:: Copyright (C) 2024-present TabulexFlow Team
:: SPDX-License-Identifier: AGPL-3.0-or-later
:: 注意：本文件编码为 UTF-8（无 BOM），配合下方 chcp 65001 正常显示中文
::              必须保持 CRLF 行尾符保存！cmd.exe 解析 .bat 严格要求 CRLF
@echo off
chcp 65001 >nul
cls
set "scriptPath=%~dp0"

cd /d "%scriptPath%.."
:: 本地 conda 环境（py312tf）仅开发主机使用；其他开发者改为自己的 Python 环境
call conda activate py312tf
:: echo Starting Flask development server...

:: 依赖检查：确保 wxPython 已安装（与 tfpdesktop_run.sh 逻辑一致）
python -c "import wx" 2>nul
if errorlevel 1 (
    echo   [FAIL] wxPython not installed in py312tf environment
    echo         Install frontend dependencies: pip install -r requirements.txt
    exit /b 1
)

@echo on
python main.py
