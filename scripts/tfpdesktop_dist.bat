:: Copyright (C) 2024-present TabulexFlow Team
:: SPDX-License-Identifier: AGPL-3.0-or-later
:: tfpdesktop_dist.bat - 启动编译后的 TabulexFlowDesktop 前端程序（Windows）
:: 与 tfpdesktop_dist.sh（Linux）对应；启动前先切换到可执行文件所在目录
:: 自动探测产物（PyInstaller）：名称格式 <名称>-<版本>-<形态>[-devtest]（如 TabulexFlow-1.0.0-OSS）
::   onedir : dist\<名称>\<名称>.exe    例：dist\TabulexFlow-1.0.0-OSS\TabulexFlow-1.0.0-OSS.exe
::   onefile: dist\<名称>.exe          例：dist\TabulexFlow-1.0.0-OSS-devtest.exe
:: 注意：本文件必须保持 CRLF 行尾符保存！cmd.exe 解析 .bat 严格要求 CRLF（LF-only 会导致 goto/括号块解析错乱）。
::       文件编码 UTF-8（无 BOM），配合下方 chcp 65001 正常显示中文。
@echo off
setlocal
chcp 65001 >nul
title TabulexFlowDesktop Frontend (dist run)

set "scriptPath=%~dp0"
set "FE_DIST=%scriptPath%..\dist"

cls
echo ============================================================
echo   TabulexFlowDesktop Frontend - Build Artifact Launcher (Windows) / TabulexFlowDesktop 前端 - 编译产物启动（Windows）
echo ============================================================
echo.

:: 自动探测：名称形如 TabulexFlow-<版本>-<形态>[-devtest]；
:: onedir 优先于 onefile，各自按修改时间取最新（dir /o-d）
set "EXE_PATH="
set "EXE_IS_DEVTEST=0"
for /f "delims=" %%D in ('dir /b /ad /o-d "%FE_DIST%\TabulexFlow-*" 2^>nul') do (
    if not defined EXE_PATH if exist "%FE_DIST%\%%D\%%D.exe" set "EXE_PATH=%FE_DIST%\%%D\%%D.exe"
)
for /f "delims=" %%F in ('dir /b /a-d /o-d "%FE_DIST%\TabulexFlow-*.exe" 2^>nul') do (
    if not defined EXE_PATH set "EXE_PATH=%FE_DIST%\%%F"
)

if not defined EXE_PATH (
    echo   [FAIL] Compiled frontend executable not found: %FE_DIST% / 未找到编译后的前端可执行文件：%FE_DIST%
    echo          Expected name pattern: TabulexFlow-^<version^>-^<OSS^|Full^>[-devtest] / 期望命名：TabulexFlow-^<版本^>-^<OSS^|Full^>[-devtest]
    echo            onedir : dist\TabulexFlow-^<version^>-^<edition^>\TabulexFlow-^<version^>-^<edition^>.exe / （目录模式）
    echo            onefile: dist\TabulexFlow-^<version^>-^<edition^>.exe / （单文件模式）
    echo          Please run scripts\tfpdesktop_build.bat to build first. / 请先运行 scripts\tfpdesktop_build.bat 进行编译。
    pause
    exit /b 1
)

:: 标记是否为 Local Test 开发版产物（路径包含 -devtest）
echo "%EXE_PATH%" | findstr /i "devtest" >nul && set "EXE_IS_DEVTEST=1"

for %%P in ("%EXE_PATH%") do set "EXE_DIR=%%~dpP"

echo   Frontend program dir / 前端程序目录 : %EXE_DIR%
echo   Executable / 可执行文件   : %EXE_PATH%
echo.

:: Local Test 开发版产物提示（后端指向本地 127.0.0.1:8080，禁止分发）
if "%EXE_IS_DEVTEST%"=="1" (
    echo   [WARN] LOCAL TEST dev-test artifact detected, backend points to local 127.0.0.1:8080 / 检测到 LOCAL TEST 开发测试产物 ^(backend 指向本地 127.0.0.1:8080^)^!
    echo          This artifact is for development testing only, do NOT distribute / 该产物仅用于开发测试，请勿分发！
    echo.
)

:: 切换到可执行文件所在目录，保证相对路径正确
cd /d "%EXE_DIR%"
echo   Starting frontend program (close the window to exit)... / 正在启动前端程序（关闭窗口即退出）...
echo ============================================================
echo.
"%EXE_PATH%"

exit /b %errorlevel%