# Changelog / 更新日志

> **中文版请翻到后面阅读 / Chinese version below** ↓

## English Version

All notable changes to the TabulexFlowDesktop **Community Edition** (this open-source repository) will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

### [Unreleased]
- Rebranded built-in Chinese tool names with the "灵表" (Lingbiao) prefix: TabulexFileOperator → 灵表文件处理, TabulexDocCreator → 灵表文档创建, TabulexBomComparator → 灵表BOM比对
- Window title now follows the selected UI language (Simplified Chinese shows 灵表矩阵 instead of TabulexFlow)

### [1.0.0] - 2026-10-12

#### Added (Community Edition, open source)
- Initial open-source release of the TabulexFlowDesktop frontend main program (AGPL v3)
- Main window: searchable tool grid with favorites and pinned tools; six UI languages (English, 简体中文, Français, Español, Русский, العربية)
- Built-in open-source tools (BuiltinProgram, bundled with the app): TabulexFileOperator (bulk file operations) and TabulexDocCreator (bulk document creation), using spreadsheets as the unified input/output interface
- Distribution: Windows portable single-file EXE (no installation); Linux .deb package and .AppImage (both shipped uncompressed)

#### Build provenance (Community Edition binaries)
- The distributed Community Edition binaries are built from this repository at the release tag with
  `build_mode.IS_OSS_COMMUNITY_BUILD` temporarily set to `True` by `scripts/tfpdesktop_build.sh` / `scripts/tfpdesktop_build.bat`
  (select `[1] OSS Community Edition`) and automatically reverted to `False` afterwards. The Corresponding Source of a
  Community Edition binary is therefore this repository at the release tag plus that documented single-flag build
  transformation; every other source file is identical.
- A bare `python -m PyInstaller config/build.spec` (without that flag) builds the backend-connected full edition, not
  the Community Edition.

#### Platform capabilities (Commercial Edition; not part of this open-source release)
- Support for the RemoteProgram and RemoteWebpage tool types (require backend connection and login)
- Account login with status-bar user info display

## 中文版

本文件记录 TabulexFlowDesktop **开源社区版**（本开源仓库）的所有重要变更。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

### [未发布]
- 内置工具中文名加"灵表"品牌前缀：TabulexFileOperator → 灵表文件处理，TabulexDocCreator → 灵表文档创建，TabulexBomComparator → 灵表BOM比对
- 窗口标题随所选界面语言显示（简体中文显示"灵表矩阵"，不再固定为 TabulexFlow）

### [1.0.0] - 2026-10-12

#### 新增（开源社区版）
- TabulexFlowDesktop 前端主程序首次开源发布（AGPL v3）
- 主窗口：可搜索的工具网格、收藏与置顶；六种界面语言（English、简体中文、Français、Español、Русский、العربية）
- 内置开源工具（BuiltinProgram，随主程序分发）：TabulexFileOperator（批量文件操作）与 TabulexDocCreator（批量文档创建），以电子表格作为统一输入输出界面
- 发行形态：Windows 免安装单文件 EXE；Linux 提供 .deb 安装包与 .AppImage（均不压缩直发）

#### 构建来源（社区版二进制）
- 分发的社区版二进制由本仓库发布标签（tag）对应的源码构建，构建期间由 `scripts/tfpdesktop_build.sh` /
  `scripts/tfpdesktop_build.bat`（选择 `[1] OSS 社区版`）将 `build_mode.IS_OSS_COMMUNITY_BUILD` 临时置为 `True`，
  构建结束后自动还原为 `False`。因此社区版二进制对应的完整源码 = 发布标签对应的本仓库源码 + 该处已固化的
  单标记构建变换，其余源码文件完全相同。
- 直接执行 `python -m PyInstaller config/build.spec`（不做该标记变换）构建的是连接后端的完整版，而非社区版。

#### 平台能力（商业版；不属于本次开源发布）
- 支持 RemoteProgram 与 RemoteWebpage 工具类型（需连接后端并登录）
- 账号登录与状态栏用户信息显示
