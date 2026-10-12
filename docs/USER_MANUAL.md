# TabulexFlow User Manual

> **Document Version**: 3.1.0
> **Last Updated**: 2026-10-12
> **Applies to**: TabulexFlow v1.0.0
> **Target Audience**: End users

> **中文版请翻到后面阅读 / Chinese version below** ↓

> **Community Edition (open source)**: This manual covers the desktop frontend main program + BuiltinProgram tools only.
> A build of this edition connects to **no** backend; login/account, RemoteProgram and RemoteWebpage are Commercial Edition
> features. Section 1.4 compares Community Edition and Commercial Edition capabilities.
>
> **开源社区版**：本手册仅覆盖桌面前端主程序 + BuiltinProgram 工具。本版本**不连接任何后端**；登录/账号、RemoteProgram、
> RemoteWebpage 属商业版功能。开源社区版与商业版的能力对比见 1.4 节。

## 1. Product Overview

### 1.1 Introduction

TabulexFlow is a table-driven batch-task automation platform that uses spreadsheets as its unified interface. Its brand tagline: "TabulexFlow: Table-driven batch task flow that automates repetitive work."

- **Product Nature**: A table-driven batch-task automation platform using spreadsheets (Excel/CSV) as the unified input and output interface. The frontend and built-in tools are open source under AGPL v3 (Community Edition); the backend and commercial tools are under a commercial license (Commercial Edition)
- **Operation Mode**: Manually fill in data in the spreadsheet → Click the corresponding tool button to execute → Results are automatically written back to the spreadsheet
- **Platform**: PC (Windows / Linux)

### 1.2 System Requirements

| Item | Requirement |
|------|-------------|
| Operating System | Windows 10/11, or Linux (Mint/Debian/Ubuntu) |
| Memory | Minimum 4GB, recommended 8GB |
| Disk Space | At least 500MB available |
| Network | Some features require network connection |

### 1.3 Installation

#### Windows

1. Download `TabulexFlow-<version>-OSS-windows-x64.exe` (portable single file — no installation, no extraction needed)
2. Double-click to run

> Note: The EXE is not code-signed yet, so Microsoft Defender SmartScreen may show
> "Windows protected your PC" on first run. Click "More info" → "Run anyway" to
> proceed. Download the EXE only from the official GitHub Releases page.

#### Linux (Debian family: Mint/Debian/Ubuntu; Red Hat family: RHEL/CentOS/Fedora/Rocky/Alma)

**Option A — .deb package, Debian family (recommended)**

1. Download `tabulexflow_<version>_amd64.deb`
2. Install: double-click and choose "Install", or run `sudo apt install ./tabulexflow_<version>_amd64.deb`
3. Launch **TabulexFlow** from the application menu
4. Uninstall: `sudo apt remove tabulexflow`

**Option B — .rpm package, Red Hat family**

1. Download `tabulexflow.x86_64.rpm`
2. Install: `sudo dnf install ./tabulexflow.x86_64.rpm`
3. Launch **TabulexFlow** from the application menu
4. Uninstall: `sudo dnf remove tabulexflow`

**Option C — .AppImage (portable, no installation)**

1. Download `TabulexFlow-<version>-OSS-x86_64.AppImage`
2. Make it executable and run: `chmod +x ./TabulexFlow*.AppImage && ./TabulexFlow*.AppImage`
3. If the system lacks FUSE, install it (`sudo apt install libfuse2`) or run with extraction: `./TabulexFlow-<version>-OSS-x86_64.AppImage --appimage-extract && ./squashfs-root/AppRun`

> **Note**: On first run, Windows may show a security prompt. Click "More info" → "Run anyway".

### 1.4 Community Edition vs Commercial Edition

| Capability | Community Edition (open source) | Commercial Edition |
|------------|-------------------------------|--------------------|
| Frontend main program | Yes | Yes |
| Built-in tools (BuiltinProgram, AGPL v3) | Yes | Yes |
| Account, login and tool subscription | No | Yes |
| Remote tools (RemoteProgram) | No | Yes |
| Web tools (RemoteWebpage) | No | Yes |
| Runtime permission control | No | Yes |
| Enterprise management and support | No | Yes |

> **Commercial Edition**: coming soon. For product information and early-access applications, contact `tabulexflow@outlook.com`.
>
> **Product roadmap**: the set of built-in open-source tools will keep growing, and more official and third-party tools (including Commercial Edition tools) are under active development.

---

## 2. Quick Start

### 2.1 Launching the Application

Double-click the desktop icon or run `python main.py` to start TabulexFlow.

### 2.2 Main Interface Overview

After launching, the main window displays:

- **Search Bar**: A favorites dropdown button + search input box + search icon + a sort dropdown (Default / Recent / Name / Type / Free local; the "Popular" sort is a Commercial Edition option)
- **Tool Grid Area**: All tool cards displayed in a scrollable grid layout
  - Each card shows the tool icon, name, description, and tags (Open Source/Free/Paid, Local/Cloud)
- **Status Bar**: Displays the current tool and tool-list loading status

> **Note**: Tools are no longer separated into tabs by type. All tools are displayed together, with type indicated by tags on each card.

### 2.3 Menu Descriptions

| Menu | Function |
|------|----------|
| File | Refresh tool list (F5), clear cache, close all tools, exit (Ctrl+Q) |
| Tools | Open built-in tools (Commercial Edition also lists remote/web tools) |
| Window | Home (Ctrl+H), minimize, maximize, list of open tools |
| Settings | Language, theme, preferences |
| Help | About (F1) |

> **Community Edition**: The **Account** menu (login, user info, order center, feedback) is a Commercial Edition feature and is hidden in the Community Edition.

---

## 3. Account Management

Login, registration, subscriptions, and offline authorization are Commercial Edition features: contact `tabulexflow@outlook.com` for product information and early access. The Community Edition requires no account.

---

## 4. Using Tools

### 4.1 Launching Tools

#### From the Main Window

1. Find the target tool in the tool grid on the main window (use the search bar to filter if needed)
2. Click the tool card
3. The tool launches

#### Using Favorites and Pins

- **Favorites** require login (Commercial Edition): right-click a tool card to add it to favorites; click the favorites dropdown button in the search bar to quickly access favorited tools; logged-in changes sync with your account automatically. In the Community Edition (no login), favorites are unavailable.
- **Pin** works **without login** (saved locally): right-click a tool card and choose "Pin" to keep it visible at the top of the tool grid.

### 4.2 Tool Types

#### Built-in Tool (BuiltinProgram)

- Fully integrated into the main application (AGPL v3 open source)
- No additional installation required
- Runs embedded within the main window content area
- Automatically hides/shows when switching tools

#### Remote Tool / Web Tool (Commercial Edition Only)

Remote tools (RemoteProgram) and web tools (RemoteWebpage) are provided by the TabulexFlow Commercial Edition: contact `tabulexflow@outlook.com` for product information and early access.

### 4.3 Tool Window Management

#### Switching Tools

- Click the "Home" button or press Ctrl+H to return to the tool list
- Switch between open tools through the **Window** menu

#### Closing Tools

- Built-in Tool: Return to home (the tool panel is hidden, not destroyed)
- Remote Tool: Click the window close button; the main window restores automatically
- Web Tool: Click the dialog close button

### 4.4 Tool Permissions

> **Commercial Edition**: Runtime permission control (login checks and feature-level permission verification) is provided by the TabulexFlow Commercial Edition. The Community Edition has no permission gates: all built-in tools are free and unrestricted.

---

## 5. Tool Details

### 5.1 TabulexFileOperator (Bulk File Processing)

TabulexFileOperator is a built-in bulk file processing tool (open source, AGPL v3) that supports search, rename, move, copy, compress, decompress, delete, and duplicate detection operations.

> **Detailed guide (recommended)**: [TabulexFileOperator User Manual](manual/TabulexFileOperator.md) — English + 中文, covering every tab, parameters, Apply/Preview/Execute, conflicts, undo/redo and FAQ.

#### Main Features

| Feature Tab | Description |
|-------------|-------------|
| Search | Find files/folders by name, extension, wildcard or regex and add them to the grid |
| Rename | Batch rename with 10 methods (text/position/prefix-suffix/case/regex/number/placeholder/MP3) |
| Move | Move files/folders to a target folder, with folder-structure and conflict options |
| Copy | Batch copy files/folders |
| Compress | Group rows and create one ZIP per group |
| Decompress | Extract `.zip` / `.tar` / `.tar.gz` / `.tar.bz2` / `.tar.xz` / `.7z` archives |
| Delete | Batch delete (to Recycle Bin) with filters |
| Duplicates | Find duplicate files by name, size, fingerprint or hash |

#### Usage

1. Find TabulexFileOperator in the tool grid on the main window
2. Click the card to launch
3. Fill the grid (Search → Apply & Add, type paths, or Import), then on the target tab click **Apply → (Preview) → Execute**

### 5.2 TabulexDocCreator (Bulk Document Creation)

TabulexDocCreator is a built-in bulk document processing tool (open source, AGPL v3) that supports creating and modifying Excel, Word, PPT, and PDF documents.

> **Detailed guide (recommended)**: [TabulexDocCreator User Manual](manual/TabulexDocCreator.md) — English + 中文, covering every tab, fill methods, placeholders, Create Doc/Get Doc Info, preview/execute and FAQ.

#### Main Features

- Batch create documents based on templates
- Placeholder replacement
- Content insertion
- Supports Excel/Word/PPT/PDF formats

#### Usage

1. Find TabulexDocCreator in the tool grid on the main window
2. Click the card to launch
3. Select a template file
4. Configure the data source
5. Execute batch creation

---

## 6. System Settings

### 6.1 Language Settings

1. Click menu **Settings** → **Language**
2. Select a language from the submenu:
   - English (en)
   - 简体中文 (zh)
   - Français (fr)
   - Русский (ru)
   - Español (es)
   - العربية (ar)
3. A prompt will indicate that a restart is required for the language change to take effect

### 6.2 Clearing Cache

1. Click menu **File** → **Clear Cache**
2. Confirm the operation in the dialog
3. This will delete all locally cached tool files and reset non-builtin tool versions (the "non-builtin tool versions" reset applies to the Commercial Edition; the Community Edition only has built-in tools)

---

## 7. FAQ

### 7.1 Login Issues

Login is a Commercial Edition feature (see Section 3); the Community Edition needs no login.

### 7.2 Tool Launch Issues

**Problem: Tool cannot start**

Solutions:
1. Restart the application
2. Check error logs (see Section 10.3)

**Problem: Tool becomes unresponsive after launch**

Solutions:
1. Wait a few seconds
2. Close and restart the tool
3. Restart the main application
4. Check if system resources are sufficient

### 7.3 Offline Usage Issues

- **Community Edition**: Built-in tools fully support offline use; no login and no offline time limit.
- **Commercial Edition**: Offline authorization and offline grace handling are provided by the Commercial Edition.

### 7.4 Performance Issues

**Problem: Application runs slowly**

Solutions:
1. Close unnecessary tool windows
2. Clear cache data
3. Check system resource usage
4. Restart the application

### 7.5 File Is Locked / "File Is in Use" Prompt

When an opened file is locked by another program (for example, an Excel/CSV file opened in Excel or WPS):

- TabulexFileOperator skips locked files and shows a warning ("File is locked by another program, skipped"), or shows "File is in use, please close it first" for the file being written
- Solution: close the file in the other program (Excel/WPS/editors) first, then re-run the operation

---

## 8. Keyboard Shortcuts

| Shortcut | Function |
|----------|----------|
| F5 | Refresh tool list |
| Ctrl+H | Go to home page |
| Ctrl+Q | Exit application |
| F1 | About dialog |

---

## 9. Security

### 9.1 Data Security

- All sensitive data (such as tokens) are stored using encrypted storage (keyring or Fernet encryption fallback)
- Temporary tool context files use random filenames and restricted permissions, are cleaned up after use; tokens are passed via environment variables (never written to files)

### 9.2 Account Security

Account security (password policy, account sharing protection) is a Commercial Edition feature; the Community Edition stores no account data locally.

### 9.3 Network Security

- All network communication uses HTTPS encryption
- Do not save login status on public networks
- Non-local HTTP URLs are rejected for security

---

## 10. Technical Support

### 10.1 Getting Help

- **Documentation**: See the `docs/` directory in this repository
- **FAQ**: See Chapter 7 of this manual
- **Community**: Ask questions and exchange ideas via GitHub Issues
- **Commercial Edition**: For product information and early-access applications, contact `tabulexflow@outlook.com`

> **Note**: The official website `https://tabulexflow.com` (including the download and feedback pages linked inside the
> app) is **not live yet**; the links are placeholders and will become available when the site launches.

### 10.2 Reporting Issues

1. Describe the problem and steps to reproduce
2. Optionally attach log files
3. Submit feedback through the support channel

### 10.3 Viewing Logs

Log file locations:
- Packaged application: `<directory containing the executable>/logs/`
- Running from source: `<repository root>/logs/`

---

## 11. Updates

- **Community Edition**: Updates are released via GitHub Releases; check the repository Release page manually.
- **Commercial Edition**: The application automatically checks for tool-list updates at startup, and remote tools (RemoteProgram) support online updates via the backend.

---

## 12. Appendix

### 12.1 Glossary

| Term | Description |
|------|-------------|
| Token | Access token used for authentication (encrypted storage) |
| Offline Use | When the backend is unreachable, built-in tools remain usable offline; there is no offline grace-period limit |
| BuiltinProgram | Built-in Tool, shipped with the main application (AGPL v3 open source) |
| RemoteProgram | Remote Tool provided by the TabulexFlow platform (commercial license, paid features) |
| RemoteWebpage | Web Tool provided by the TabulexFlow platform (commercial license, requires network) |
| DPI Scale Factor | Display scaling factor for high-DPI screen adaptation |

---

> **Document Version**: 3.1.0
> **Last Updated**: 2026-10-12

---
---

## 中文版

## 1. 产品概述

### 1.1 简介

TabulexFlow 是一款以表格为统一界面的批量任务自动化平台。品牌标语："TabulexFlow: Table-driven batch task flow that automates repetitive work."

- **产品本质**：以表格（Excel/CSV）为统一输入与输出界面的批量任务自动化平台。前端与内置工具以 AGPL v3 开源（开源社区版）；后端与收费工具为商业许可（商业版）
- **操作模式**：手动在表格中填写数据 → 点击对应工具按钮执行 → 结果自动写回表格
- **运行平台**：PC端（Windows / Linux）

### 1.2 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11，或 Linux（Mint/Debian/Ubuntu） |
| 内存 | 最低 4GB，推荐 8GB |
| 磁盘空间 | 至少 500MB 可用空间 |
| 网络 | 部分功能需要网络连接 |

### 1.3 安装

#### Windows 系统

1. 下载 `TabulexFlow-<版本>-OSS-windows-x64.exe`（免安装单文件，无需解压）
2. 双击运行即可

> 说明：EXE 暂未做代码签名，首次运行时 Microsoft Defender SmartScreen 可能弹出
> "Windows 已保护你的电脑"提示，点击"更多信息"→"仍要运行"即可继续。
> 请仅从官方 GitHub Releases 页面下载 EXE。

#### Linux 系统（Debian 系：Mint/Debian/Ubuntu；Red Hat 系：RHEL/CentOS/Fedora/Rocky/Alma）

**方式 A — .deb 安装包（Debian 系，推荐）**

1. 下载 `tabulexflow_<版本>_amd64.deb`
2. 安装：双击后选择"安装"，或终端执行 `sudo apt install ./tabulexflow_<版本>_amd64.deb`
3. 从开始菜单打开 **TabulexFlow**
4. 卸载：`sudo apt remove tabulexflow`

**方式 B — .rpm 安装包（Red Hat 系）**

1. 下载 `tabulexflow.x86_64.rpm`
2. 安装：终端执行 `sudo dnf install ./tabulexflow.x86_64.rpm`
3. 从开始菜单打开 **TabulexFlow**
4. 卸载：`sudo dnf remove tabulexflow`

**方式 C — .AppImage 免安装**

1. 下载 `TabulexFlow-<版本>-OSS-x86_64.AppImage`
2. 赋予可执行权限后运行：`chmod +x ./TabulexFlow*.AppImage && ./TabulexFlow*.AppImage`
3. 如系统缺少 FUSE，先安装（`sudo apt install libfuse2`），或用解压方式运行：`./TabulexFlow-<版本>-OSS-x86_64.AppImage --appimage-extract && ./squashfs-root/AppRun`

> **注意**：首次运行时，Windows 可能弹出安全提示，请点击"更多信息" → "仍要运行"。

### 1.4 开源社区版与商业版对比

| 能力 | 开源社区版 | 商业版 |
|------|-----------|--------|
| 前端主程序 | 支持 | 支持 |
| 内置工具（BuiltinProgram，AGPL v3） | 支持 | 支持 |
| 账号、登录与工具订购 | 不支持 | 支持 |
| 远程工具（RemoteProgram） | 不支持 | 支持 |
| 网页工具（RemoteWebpage） | 不支持 | 支持 |
| 运行时权限控制 | 不支持 | 支持 |
| 企业级管理与支持 | 不支持 | 支持 |

> **商业版**：即将推出。如需产品信息或申请内测，请联系 `tabulexflow@outlook.com`。
>
> **产品路线图**：内置开源工具将持续增加，更多官方与第三方工具（含商业版工具）正在开发中。

---

## 2. 快速入门

### 2.1 启动程序

双击桌面图标或运行 `python main.py` 启动 TabulexFlow。

### 2.2 主界面介绍

启动后显示主窗口，包含：

- **搜索栏**：收藏下拉按钮 + 搜索输入框 + 搜索图标 + 排序下拉框（默认/最近使用/名称/类型/免费本地；"热门"排序为商业版选项）
- **工具Grid区域**：所有工具卡片统一排列在可滚动的网格布局中
  - 每张卡片显示工具图标、名称、描述和标签（开源/免费/付费、本地/云端）
- **状态栏**：显示当前工具与工具列表加载状态

> **注意**：工具不再按类型分Tab显示，所有工具统一展示，类型通过卡片上的标签区分。

### 2.3 菜单说明

| 菜单 | 功能 |
|------|------|
| 文件 | 刷新工具列表(F5)、清除缓存、关闭所有工具、退出(Ctrl+Q) |
| 工具 | 打开内置工具（商业版还包含远程/网页工具列表） |
| 窗口 | 主页(Ctrl+H)、最小化、最大化、已打开的工具列表 |
| 设置 | 语言、主题、偏好设置 |
| 帮助 | 关于(F1) |

> **开源社区版**：**账户**菜单（登录、用户信息、订购中心、问题反馈）属商业版功能，社区版已隐藏该菜单。

---

## 3. 账户管理

登录、注册、订阅与离线授权属商业版功能：如需产品信息或申请内测，请联系 `tabulexflow@outlook.com`。开源社区版无需账号。

---

## 4. 工具使用

### 4.1 启动工具

#### 通过主窗口启动

1. 在主窗口的工具Grid中找到目标工具（可使用搜索栏过滤）
2. 点击工具卡片
3. 工具启动

#### 使用收藏与置顶

- **收藏**需登录（商业版）：右键工具卡片可添加到收藏；点击搜索栏中的收藏下拉按钮可快速访问已收藏工具；登录后变更会自动与账号同步。开源社区版（无登录）下收藏功能不可用。
- **置顶****无需登录**即可使用（保存在本地）：右键工具卡片选择"置顶"，可将该工具固定显示在工具网格顶部。

### 4.2 工具类型

#### 内置工具 (BuiltinProgram)

- 完全集成在主程序中（AGPL v3 开源）
- 无需额外安装
- 在主窗口内容区域嵌入式运行
- 切换工具时自动隐藏/显示

#### 远程工具 / 网页工具（仅商业版）

远程工具（RemoteProgram）和网页工具（RemoteWebpage）由 TabulexFlow 商业版提供：如需产品信息或申请内测，请联系 `tabulexflow@outlook.com`。

### 4.3 工具窗口管理

#### 切换工具

- 点击"主页"按钮或按 Ctrl+H 返回工具列表
- 通过 **窗口** 菜单切换已打开的工具

#### 关闭工具

- 内置工具：返回主页即可（工具面板隐藏而非销毁）
- 远程工具：点击窗口关闭按钮，主程序窗口自动恢复
- 网页工具：点击对话框关闭按钮

### 4.4 工具权限

> **商业版**：运行时权限控制（登录检查、功能级权限校验）由 TabulexFlow 商业版提供。开源社区版无权限门槛：内置工具全部免费、无限制使用。

---

## 5. 工具详细说明

### 5.1 TabulexFileOperator（灵表文件处理）

TabulexFileOperator 是一款内置的灵表文件处理工具（开源，AGPL v3），支持搜索、重命名、移动、复制、压缩、解压、删除和查重等操作。

> **详细手册（推荐）**：[灵表文件处理使用手册](manual/TabulexFileOperator.md) —— 中英双语，涵盖各标签页、参数、应用/预览/执行、冲突处理、撤销/重做与常见问题。

#### 主要功能

| 功能标签页 | 说明 |
|-----------|------|
| 搜索 | 按文件名、扩展名、通配符或正则查找文件/目录并加入表格 |
| 重命名 | 10 种批量重命名方式（文本/位置/前后缀/大小写/正则/编号/占位符/MP3） |
| 移动 | 移动文件/目录到目标目录，支持目录结构与冲突选项 |
| 复制 | 批量复制文件/目录 |
| 压缩 | 分组并把每组压缩为一个 ZIP |
| 解压 | 解压 `.zip` / `.tar` / `.tar.gz` / `.tar.bz2` / `.tar.xz` / `.7z` |
| 删除 | 按过滤条件批量删除（移入回收站） |
| 去重 | 按文件名、大小、指纹或哈希查找重复文件 |

#### 使用方法

1. 在主窗口工具 Grid 中找到 **灵表文件处理**
2. 点击卡片启动
3. 填充表格（搜索 → 应用并添加，或手动输入、导入），然后在目标标签页依次点击 **应用 →（预览）→ 执行**

### 5.2 TabulexDocCreator（灵表文档创建）

TabulexDocCreator 是一款内置的批量文档处理工具（开源，AGPL v3），支持创建和修改 Excel、Word、PPT、PDF 文档。

> **详细手册（推荐）**：[灵表文档创建使用手册](manual/TabulexDocCreator.md) —— 中英双语，涵盖各标签页、填写方式、占位符、创建文档/获取文档信息、预览/执行与常见问题。

#### 主要功能

- 基于模板批量创建文档
- 占位符替换
- 内容插入
- 支持 Excel/Word/PPT/PDF 格式

#### 使用方法

1. 在主窗口工具Grid中找到 TabulexDocCreator
2. 点击卡片启动
3. 选择模板文件
4. 配置数据源
5. 执行批量创建

---

## 6. 系统设置

### 6.1 语言设置

1. 点击菜单 **设置** → **语言**
2. 从子菜单中选择语言：
   - English (en)
   - 简体中文 (zh)
   - Français (fr)
   - Русский (ru)
   - Español (es)
   - العربية (ar)
3. 系统会提示需要重启才能使语言切换生效

### 6.2 清除缓存

1. 点击菜单 **文件** → **清除缓存**
2. 在对话框中确认操作
3. 此操作将删除所有本地缓存的工具文件，并重置非内置工具版本号（"重置非内置工具版本"适用于商业版；开源社区版仅含内置工具）

---

## 7. 常见问题

### 7.1 登录问题

登录属商业版功能（见第 3 章），开源社区版无需登录。

### 7.2 工具启动问题

**问题：工具无法启动**

解决方案：
1. 重启程序
2. 查看错误日志（见 10.3 节）

**问题：工具启动后无响应**

解决方案：
1. 等待几秒钟
2. 关闭并重新启动工具
3. 重启主程序
4. 检查系统资源是否充足

### 7.3 离线使用问题

- **开源社区版**：内置工具完全支持离线使用，无需登录，无离线时限。
- **商业版**：离线授权与离线宽限处理由商业版提供。

### 7.4 性能问题

**问题：程序运行缓慢**

解决方案：
1. 关闭不需要的工具窗口
2. 清理缓存数据
3. 检查系统资源占用
4. 重启程序

### 7.5 文件被占用 / "文件正在使用中"提示

当文件已被其他程序打开（如 Excel/CSV 文件在 Excel 或 WPS 中打开）时，文件会被占用：

- TabulexFileOperator 会自动跳过被占用文件并提示（"文件被其他程序锁定，已跳过"），或对写入中的文件提示"文件正在使用中，请先关闭"
- 解决方法：先在其他程序（Excel/WPS/编辑器）中关闭该文件，再重新执行操作

---

## 8. 快捷键

| 快捷键 | 功能 |
|--------|------|
| F5 | 刷新工具列表 |
| Ctrl+H | 返回主页 |
| Ctrl+Q | 退出程序 |
| F1 | 关于对话框 |

---

## 9. 安全说明

### 9.1 数据安全

- 所有敏感数据（如 Token）使用加密方式安全存储（keyring 或 Fernet 加密回退方案）
- 工具临时上下文文件使用随机文件名与权限收紧保护，使用后自动清理；Token 通过环境变量传递（不写入文件）

### 9.2 账户安全

账户安全（密码策略、账户共享防护）属商业版功能；开源社区版不在本地存储任何账号数据。

### 9.3 网络安全

- 所有网络通信使用 HTTPS 加密
- 不在公共网络保存登录状态
- 非本地 HTTP URL 会被安全策略拒绝

---

## 10. 技术支持

### 10.1 获取帮助

- **文档**：参见本仓库的 `docs/` 目录
- **常见问题**：查看本手册第7章
- **社区**：通过 GitHub Issues 提问与交流
- **商业版**：如需产品信息或申请内测，请联系 `tabulexflow@outlook.com`

> **说明**：官方网站 `https://tabulexflow.com`（包括程序内链接的下载页与反馈页）**尚未上线**；
> 相关链接为占位，待官网上线后即可访问。

### 10.2 反馈问题

1. 描述问题和复现步骤
2. 可选上传日志文件
3. 通过支持渠道提交反馈

### 10.3 查看日志

日志文件位置：
- 打包后的程序：`<可执行文件所在目录>/logs/`
- 源码运行：`<仓库根目录>/logs/`

---

## 11. 更新说明

- **开源社区版**：通过 GitHub Releases 发布更新，请手动检查仓库 Release 页面。
- **商业版**：应用启动时自动检查工具列表更新；远程工具（RemoteProgram）支持通过后端在线更新。

---

## 12. 附录

### 12.1 术语表

| 术语 | 说明 |
|------|------|
| Token | 访问令牌，用于身份验证（加密存储） |
| 离线使用 | 后端不可达时内置工具仍可离线使用，无离线宽限期限制 |
| BuiltinProgram | 内置工具，随主程序一起发布（AGPL v3 开源） |
| RemoteProgram | 远程工具，由 TabulexFlow 平台提供（商业许可，收费功能） |
| RemoteWebpage | 网页工具，由 TabulexFlow 平台提供（商业许可，需网络） |
| DPI缩放因子 | 高DPI屏幕适配的显示缩放因子 |

---

> **文档版本**: 3.1.0
> **最后更新**: 2026-10-12
