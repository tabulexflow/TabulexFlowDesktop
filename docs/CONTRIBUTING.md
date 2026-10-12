# Contributing Guide / 贡献指南

> **Last Updated / 最后更新**: 2026-10-12
> **Applies to / 适用版本**: TabulexFlow v1.0.0
> **Target Audience / 目标读者**: Open-source contributors / 开源贡献者

---

> **中文版请翻到后面阅读 / Chinese version below** ↓

---
> **Community Edition (open source)**: This repository contains the desktop **frontend main program + BuiltinProgram (AGPL v3) tools** only.
> Login/account, backend services, RemoteProgram and RemoteWebpage belong to the closed-source Commercial Edition. The **Community Edition** build
> (produced by `scripts/tfpdesktop_build.sh` / `scripts/tfpdesktop_build.bat` by selecting `[1] OSS Community Edition`) excludes them; the plain
> `config/build.spec` build produces the backend-connected full edition instead.
> Repository note: shared framework/auth component code (e.g. `tfp_auth`) is retained for general framework use; the community build compiles with the `IS_OSS_COMMUNITY_BUILD` flag, which disables account/login features and connects to no backend.
>
> **开源社区版**：本仓库包含桌面**前端主程序 + BuiltinProgram（AGPL v3）工具**。登录/账号、后端服务、RemoteProgram、
> RemoteWebpage 属闭源商业版；**开源社区版**构建（由 `scripts/tfpdesktop_build.sh` / `scripts/tfpdesktop_build.bat` 选择
> `[1] OSS 社区版` 产出）不包含这些功能，而裸 `config/build.spec` 构建产出的是连接后端的完整版。
> 仓库说明：本仓库保留 `tfp_auth` 等通用框架/认证组件源码，供框架统一使用；社区版构建通过 `IS_OSS_COMMUNITY_BUILD`
> 开关禁用账户/登录功能，且不连接任何后端。

---

## English Version

Thank you for your interest in contributing to the TabulexFlow project! This document will help you understand how to participate in the development.

---

### Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Environment Setup](#development-environment-setup)
- [Code Standards](#code-standards)
- [Commit Workflow](#commit-workflow)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Contributing Third-Party Tools](#contributing-third-party-tools)
- [Bug Reports](#bug-reports)
- [Feature Requests](#feature-requests)

---

### Code of Conduct

#### Our Pledge

In the interest of fostering an open and welcoming environment, we as contributors and maintainers pledge to making participation in our project and our community a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity and expression, level of experience, education, socio-economic status, nationality, personal appearance, race, religion, or sexual identity and orientation.

#### Our Standards

**Examples of positive behavior:**

- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

**Examples of unacceptable behavior:**

- The use of sexualized language or imagery and unwelcome sexual attention or advances
- Trolling, insulting/derogatory comments, and personal or political attacks
- Public or private harassment
- Publishing others' private information without explicit permission
- Other conduct which could reasonably be considered inappropriate in a professional setting

#### Responsibility

Project maintainers are responsible for clarifying the standards of acceptable behavior and are expected to take appropriate and fair corrective action in response to any instances of unacceptable behavior.

---

### How to Contribute

#### Types of Contributions

We welcome the following types of contributions:

- **Bug fixes**: Fix known issues
- **New features**: Add new functionality
- **Documentation improvements**: Improve or translate documentation
- **Code optimization**: Improve code quality
- **Translation**: Add new language support
- **Testing**: Add or improve test cases

#### Before You Begin

1. **Sign the CLA**: Read and agree to [CLA.md](CLA.md) before your first contribution
2. **Check Issues**: Review existing Issues for current tasks
3. **Discuss ideas**: For major changes, please discuss first

---

### Development Environment Setup

#### System Requirements

- Python 3.12.3 or higher
- Git version control
- pip package manager

#### Clone the Repository

```bash
git clone https://github.com/TabulexFlow/tabulexflow-desktop.git
cd tabulexflow-desktop
```

#### Create a Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python -m venv venv
source venv/bin/activate
```

> Linux 打包脚本（`scripts/tfpdesktop_build.sh` 等）通过环境变量 `TFP_VENV` 定位 Python 3.12
> venv（默认为原作者本机路径，请在 shell 中 `export TFP_VENV=/path/to/your/py312-venv` 覆盖）。
> Linux 上 wxPython 由系统 apt 包提供（python3-wxgtk4.0），勿用 pip 安装。

#### Install Dependencies

```bash
pip install -r requirements.txt
```

#### Run Tests

```bash
# Run all tests
python -m pytest tests/

# Run a specific test file
python -m pytest tests/test_base_tool.py

# Run tests with coverage
python -m pytest tests/ --cov=TabulexFlowDesktop --cov-report=html
```

#### Code Linting

```bash
# Run code format check
python -m flake8 .

# Run type checking
python -m mypy .

# Auto-format code
python -m black .
python -m isort .
```

---

### Code Standards

#### Python Code Standards

We follow PEP 8 coding conventions with the following additional requirements:

**Naming Conventions**:

```python
# Module names: lowercase, underscore-separated, tfp_ prefix
tfp_my_module.py

# Class names: PascalCase, TFP_ prefix
class TFP_MyClass:
    pass

# Function/method names: lowercase, underscore-separated
def my_function():
    pass

# Constants: UPPERCASE, underscore-separated
MAX_CONNECTIONS = 100

# Private attributes: single underscore prefix
_private_var = "private"
```

**Type Annotations**:

```python
from typing import Dict, List, Optional, Any

def process_data(
    data: List[Dict[str, Any]],
    options: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Process data

    Args:
        data: Input data list
        options: Optional configuration

    Returns:
        Processed data dictionary
    """
    pass
```

**Import Order**:

```python
# Standard library
import os
import sys
from typing import Dict, List

# Third-party libraries
import pytest
import wx

# Local modules
from tfp_toolkit.tfp_base_tool import TFP_BaseTool
from tfp_auth.tfp_auth_manager import TFP_AuthManager
```

#### Code Quality Requirements

- All functions must have docstrings
- Use type annotations
- Single function should not exceed 50 lines
- Single file should not exceed 500 lines
- Code complexity should not exceed 10

---

### Commit Workflow

#### Branch Naming

```bash
# Feature branch
feature/add-new-tool

# Fix branch
fix/authorization-error

# Documentation branch
docs/update-readme

# Refactoring branch
refactor/ipc-module
```

#### Commit Message Format

```
<type>: <short description>

[optional body]
```

The description may be written in English or Chinese; there is no language requirement.

**Types**:

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `perf` | Performance improvement |
| `refactor` | Code refactoring (no functionality change) |
| `docs` | Documentation only |
| `style` | Code formatting (no functionality change) |
| `test` | Adding or modifying tests |
| `build` | Build system or external dependency changes |
| `chore` | Configuration, housekeeping, or other tooling changes |
| `revert` | Reverting previous commits |
| `merge` | Merging branches |

**Examples**:

```bash
# Good commit messages
feat: 添加用户偏好设置功能
fix: Fix Socket connection timeout issue
perf: 提升工具列表加载速度
docs: 更新安装说明

# Bad commit messages
update code
fix bug
add feature
修改了一些东西
```

#### Commit Steps

```bash
# 1. Create and switch to a new branch
git checkout -b feature/my-new-feature

# 2. Make changes and stage
git add .

# 3. Commit changes
git commit -m "feat: 添加新功能描述"

# 4. Push to remote
git push origin feature/my-new-feature

# 5. Create a Pull Request
```

---

### Pull Request Guidelines

#### PR Checklist

Before submitting a PR, please ensure:

- [ ] Code passes all tests
- [ ] Code passes lint checks
- [ ] Necessary documentation has been added
- [ ] Code follows style guidelines
- [ ] Commit messages follow the format
- [ ] CLA has been signed

#### PR Title Format

```
[type] short description
```

Examples:
- `[feat] 添加工具自动更新功能`
- `[fix] 修复授权验证失败问题`
- `[docs] 更新贡献指南`

#### PR Description Template

```markdown
## Change Type
- [ ] New feature
- [ ] Bug fix
- [ ] Documentation update
- [ ] Code refactoring
- [ ] Other

## Description
Brief description of the changes in this PR

## Related Issue
Closes #issue_number

## Testing
Describe how to test these changes

## Screenshots
If applicable, add screenshots

## CLA Confirmation
- [ ] I have read and agree to CLA.md
```

#### Code Review

All PRs require at least one maintainer's review. Reviewers will check:

- Code quality and style
- Test coverage
- Documentation completeness
- Alignment with project goals

---

### Bug Reports

If you find a bug, please create an Issue with the following information:

```markdown
## Bug Description
A clear and concise description of the bug

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. Scroll down to '...'
4. See error

## Expected Behavior
Describe what you expected to happen

## Actual Behavior
Describe what actually happened

## Screenshots
If applicable, add screenshots

## Environment
- OS: [e.g., Windows 11]
- Python version: [e.g., 3.12]
- TabulexFlow version: [e.g., 1.0.0]

## Additional Context
Any other context about the problem
```

#### Security Vulnerabilities

If you discover a security vulnerability, please **do not** create a public Issue. Use GitHub's private vulnerability reporting instead: open the repository's **Security** tab → **Report a vulnerability** (https://github.com/TabulexFlow/tabulexflow-desktop/security).

---

### Feature Requests

If you have a feature request, please create an Issue with:

```markdown
## Feature Description
A clear and concise description of the feature you'd like

## Problem Background
What problem does this feature solve?

## Proposed Solution
Describe your proposed solution

## Alternatives Considered
Describe alternative solutions you've considered

## Additional Context
Any other context or screenshots
```

---

### Development Tips

#### Debug Mode

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Run a Single Tool

```bash
# Run a built-in tool
python -m tools_fe.tools_builtin_program.TabulexDocCreator.tool_main
```

#### Test IPC Communication

```bash
# Run IPC capability tests
python -m pytest tests/test_ipc_capabilities.py -v
```

---

### Contributing Third-Party Tools

TabulexFlow welcomes third-party developers to contribute sub-tools. There are two contribution paths depending on the tool type:

#### BuiltinProgram (Open Source, AGPL v3)

- Submit via GitHub Pull Request
- Must sign the [CLA](CLA.md) (Contributor License Agreement)
- Tool code is licensed under AGPL v3
- Tool is bundled with the frontend and distributed together
- Development guide: [TOOL_BUILTIN_GUIDE.md](TOOL_BUILTIN_GUIDE.md)

#### RemoteProgram / RemoteWebpage (Closed Source, Commercial)

- Apply by contacting `tabulexflow@outlook.com`
- Submit complete source code to TabulexFlow official for review
- After review approval, the platform distributes the tool
- Developers retain intellectual property rights; cooperation is governed by the Third-Party Cooperation Agreement provided during onboarding
- Detailed frontend development guides are provided to approved third-party developers
  (not included in this open-source repository):
  - RemoteProgram: *RemoteProgram Frontend Development Guide*
  - RemoteWebpage: *RemoteWebpage Frontend Development Guide*

#### Third-Party Tool Naming Convention

Third-party tools must use the `tool3p_` prefix for their `tool_ident` to avoid conflicts with official tools:

```
# Official tools (no prefix)
TabulexFileOperator, TabulexDocCreator, ...

# Third-party tools (tool3p_ prefix required)
tool3p_MyTool, tool3p_DataAnalyzer, tool3p_ReportGenerator, ...
```

#### tool_manifest.json Review Criteria

All third-party tool submissions are reviewed against the following criteria:

1. **tool_ident**: Must follow naming convention (PascalCase, `tool3p_` prefix for third-party)
2. **tool_type**: Must be one of `BuiltinProgram`, `RemoteProgram`, `RemoteWebpage`
3. **tool_title**: Must include at least `en` and `zh` translations
4. **tool_is_free / tool_is_open_source**: Must match the actual tool type
   - BuiltinProgram: `tool_is_free=true`, `tool_is_open_source=true`
   - RemoteProgram/RemoteWebpage: `tool_is_free=false`, `tool_is_open_source=false`
5. **tool_is_local**: Must match the tool type
   - BuiltinProgram: `true`
   - RemoteProgram/RemoteWebpage: `false`
6. **Security**: No hardcoded credentials, no data exfiltration, no malicious code
7. **Dependencies**: All dependencies must be listed in `tool_dependencies` and compatible with the project license

---

### Getting Help

- [Documentation](./) (this `docs/` directory)
- [GitHub Discussions](https://github.com/TabulexFlow/tabulexflow-desktop/discussions)
- [Issues](https://github.com/TabulexFlow/tabulexflow-desktop/issues)
- **Commercial Edition**: For product information and early-access applications, contact `tabulexflow@outlook.com`

> **For contributors**: the official website `https://tabulexflow.com` (including the `/download` and `/feedback`
> links referenced in the app and docs) is **not live yet** — these are intentional placeholders until the site
> launches, and will start working once the website goes public. Do not replace them with other URLs in code.

---

### License

By contributing code, you agree to the [CLA](CLA.md): your contributions are published in this project under the AGPL v3 license, and you also grant the project maintainers the right to use, distribute, and sublicense them under other licenses, including the closed-source commercial license. See [CLA.md](CLA.md) and the [LICENSE](../LICENSE.txt) file for details.

---

*Thank you for your contribution!*

---

---

## 中文版

感谢您有兴趣为 TabulexFlow 项目做出贡献！本文档将帮助您了解如何参与项目开发。

---

### 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发环境设置](#开发环境设置)
- [代码规范](#代码规范)
- [提交流程](#提交流程)
- [Pull Request 指南](#pull-request-指南)
- [贡献第三方工具](#贡献第三方工具)
- [问题报告](#问题报告)
- [功能建议](#功能建议)

---

### 行为准则

#### 我们的承诺

为了营造一个开放和友好的环境，我们作为贡献者和维护者承诺：无论年龄、体型、残疾、种族、性别认同和表达、经验水平、教育程度、社会经济地位、国籍、外貌、种族、宗教或性取向如何，参与我们的项目和社区都将为每个人提供无骚扰的体验。

#### 我们的标准

**积极行为示例：**

- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

**不可接受的行为示例：**

- 捣乱、侮辱/贬损评论以及人身或政治攻击
- 公开或私下骚扰
- 未经明确许可，发布他人的私人信息
- 在专业环境中可能被合理认为不适当的其他行为

#### 责任

项目维护者负责阐明可接受行为的标准，并期望对任何不可接受行为采取适当和公平的纠正措施。

---

### 如何贡献

#### 贡献类型

我们欢迎以下类型的贡献：

- **Bug 修复**：修复已知问题
- **新功能**：添加新功能
- **文档改进**：改进或翻译文档
- **代码优化**：提高代码质量
- **翻译**：添加新的语言支持
- **测试**：添加或改进测试用例

#### 开始之前

1. **签署 CLA**：首次贡献前，请阅读并同意 [CLA.md](CLA.md)
2. **查看 Issues**：查看现有 Issues 了解当前任务
3. **讨论想法**：对于重大更改，请先讨论

---

### 开发环境设置

#### 系统要求

- Python 3.12.3 或更高版本
- Git 版本控制
- pip 包管理器

#### 克隆仓库

```bash
git clone https://github.com/TabulexFlow/tabulexflow-desktop.git
cd tabulexflow-desktop
```

#### 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python -m venv venv
source venv/bin/activate
```

> Linux 打包脚本（`scripts/tfpdesktop_build.sh` 等）通过环境变量 `TFP_VENV` 定位 Python 3.12
> venv（默认为原作者本机路径，请在 shell 中 `export TFP_VENV=/path/to/your/py312-venv` 覆盖）。
> Linux 上 wxPython 由系统 apt 包提供（python3-wxgtk4.0），勿用 pip 安装。

#### 安装依赖

```bash
pip install -r requirements.txt
```

#### 运行测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试文件
python -m pytest tests/test_base_tool.py

# 运行带覆盖率的测试
python -m pytest tests/ --cov=TabulexFlowDesktop --cov-report=html
```

#### 代码检查

```bash
# 运行代码格式检查
python -m flake8 .

# 运行类型检查
python -m mypy .

# 自动格式化代码
python -m black .
python -m isort .
```

---

### 代码规范

#### Python 代码规范

我们遵循 PEP 8 编码规范，并有以下额外要求：

**命名约定**：

```python
# 模块名：小写，下划线分隔，tfp_ 前缀
tfp_my_module.py

# 类名：大驼峰命名，TFP_ 前缀
class TFP_MyClass:
    pass

# 函数/方法名：小写，下划线分隔
def my_function():
    pass

# 常量：全大写，下划线分隔
MAX_CONNECTIONS = 100

# 私有属性：单下划线前缀
_private_var = "private"
```

**类型注解**：

```python
from typing import Dict, List, Optional, Any

def process_data(
    data: List[Dict[str, Any]],
    options: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    处理数据

    Args:
        data: 输入数据列表
        options: 可选配置项

    Returns:
        处理后的数据字典
    """
    pass
```

**导入顺序**：

```python
# 标准库
import os
import sys
from typing import Dict, List

# 第三方库
import pytest
import wx

# 本地模块
from tfp_toolkit.tfp_base_tool import TFP_BaseTool
from tfp_auth.tfp_auth_manager import TFP_AuthManager
```

#### 代码质量要求

- 所有函数必须有文档字符串
- 使用类型注解
- 单个函数不超过 50 行
- 单个文件不超过 500 行
- 代码复杂度不超过 10

---

### 提交流程

#### 分支命名

```bash
# 功能分支
feature/add-new-tool

# 修复分支
fix/authorization-error

# 文档分支
docs/update-readme

# 重构分支
refactor/ipc-module
```

#### 提交信息格式

```
<类型>: <简短描述>

[可选的正文]
```

描述文字中英文均可，无语言强制要求。

**类型**：

| 类型 | 说明 |
|-----|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `perf` | 性能改进 |
| `refactor` | 代码重构（不改变功能） |
| `docs` | 仅修改文档 |
| `style` | 代码格式调整（不影响功能） |
| `test` | 添加或修改测试代码 |
| `build` | 构建系统或外部依赖的变更 |
| `chore` | 配置、杂项或其他工具链变更 |
| `revert` | 回退之前的提交 |
| `merge` | 合并分支 |

**示例**：

```bash
# 好的提交信息
feat: 添加Token自动刷新功能
fix: 修复Socket连接超时问题
perf: 提升工具列表加载速度
docs: 更新安装说明

# 不好的提交信息
update code
fix bug
add feature
修改了一些东西
```

#### 提交步骤

```bash
# 1. 创建并切换到新分支
git checkout -b feature/my-new-feature

# 2. 进行修改并暂存
git add .

# 3. 提交更改
git commit -m "feat: 添加新功能描述"

# 4. 推送到远程仓库
git push origin feature/my-new-feature

# 5. 创建 Pull Request
```

---

### Pull Request 指南

#### PR 检查清单

在提交 PR 之前，请确保：

- [ ] 代码通过所有测试
- [ ] 代码通过 lint 检查
- [ ] 添加了必要的文档
- [ ] 遵循代码规范
- [ ] 提交信息符合规范
- [ ] 已签署 CLA

#### PR 标题格式

```
[类型] 简短描述
```

示例：
- `[feat] 添加工具自动更新功能`
- `[fix] 修复授权验证失败问题`
- `[docs] 更新贡献指南`

#### PR 描述模板

```markdown
## 变更类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 代码重构
- [ ] 其他

## 变更说明
简要描述此 PR 的变更内容

## 相关 Issue
关闭 #issue_number

## 测试说明
描述如何测试这些变更

## 截图
如有必要，添加截图说明

## CLA 确认
- [ ] 我已阅读并同意 CLA.md
```

#### 代码审查

所有 PR 都需要至少一位维护者的审查。审查者会检查：

- 代码质量和风格
- 测试覆盖率
- 文档完整性
- 与项目目标的一致性

---

### 问题报告

#### 报告 Bug

如果您发现了 Bug，请创建一个 Issue 并包含以下信息：

```markdown
## Bug 描述
清晰简洁地描述这个 Bug

## 复现步骤
1. 进入 '...'
2. 点击 '...'
3. 滚动到 '...'
4. 看到错误

## 预期行为
描述您期望发生的情况

## 实际行为
描述实际发生的情况

## 截图
如有必要，添加截图

## 环境信息
- 操作系统：[例如 Windows 11]
- Python 版本：[例如 3.12]
- TabulexFlow 版本：[例如 1.0.0]

## 其他信息
其他有助于解决问题的信息
```

#### 安全漏洞

如果您发现安全漏洞，请**不要**公开创建 Issue。请使用 GitHub 私密漏洞报告：进入仓库的 **Security** 标签页 → **Report a vulnerability**（https://github.com/TabulexFlow/tabulexflow-desktop/security）。

---

### 功能建议

如果您有功能建议，请创建一个 Issue 并包含：

```markdown
## 功能描述
清晰简洁地描述您希望添加的功能

## 问题背景
这个功能要解决什么问题？

## 建议方案
描述您建议的解决方案

## 替代方案
描述您考虑过的其他方案

## 附加信息
其他相关信息或截图
```

---

### 开发技巧

#### 调试模式

```python
# 启用调试日志
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### 运行单个工具

```bash
# 运行内置工具
python -m tools_fe.tools_builtin_program.TabulexDocCreator.tool_main
```

#### 测试 IPC 通信

```bash
# 启动 IPC 能力测试
python -m pytest tests/test_ipc_capabilities.py -v
```

---

### 贡献第三方工具

TabulexFlow 欢迎第三方开发者贡献子工具。根据工具类型，有两种贡献路径：

#### BuiltinProgram（开源，AGPL v3）

- 通过 GitHub Pull Request 提交
- 必须签署 [CLA](CLA.md)（贡献者许可协议）
- 工具代码采用 AGPL v3 许可证
- 工具随前端打包一起分发
- 开发指南：[TOOL_BUILTIN_GUIDE.md](TOOL_BUILTIN_GUIDE.md)

#### RemoteProgram / RemoteWebpage（闭源，商业）

- 通过 `tabulexflow@outlook.com` 申请合作
- 将完整源码提交给 TabulexFlow 官方审核
- 审核通过后，由平台统一分发
- 开发者保留工具的知识产权；合作条款以上架时提供的《第三方合作（上架）协议》为准
- 详细前端开发指南提供给已通过审核的第三方开发者（不随本开源仓库发布）：
  - RemoteProgram：《RemoteProgram 前端开发指南》
  - RemoteWebpage：《RemoteWebpage 前端开发指南》

#### 第三方工具命名规范

第三方工具的 `tool_ident` 必须使用 `tool3p_` 前缀，以避免与官方工具冲突：

```
# 官方工具（无前缀）
TabulexFileOperator, TabulexDocCreator, ...

# 第三方工具（必须使用 tool3p_ 前缀）
tool3p_MyTool, tool3p_DataAnalyzer, tool3p_ReportGenerator, ...
```

#### tool_manifest.json 审核标准

所有第三方工具提交均按以下标准审核：

1. **tool_ident**：必须遵循命名规范（PascalCase，第三方工具使用 `tool3p_` 前缀）
2. **tool_type**：必须为 `BuiltinProgram`、`RemoteProgram`、`RemoteWebpage` 之一
3. **tool_title**：必须至少包含 `en` 和 `zh` 翻译
4. **tool_is_free / tool_is_open_source**：必须与实际工具类型匹配
   - BuiltinProgram：`tool_is_free=true`，`tool_is_open_source=true`
   - RemoteProgram/RemoteWebpage：`tool_is_free=false`，`tool_is_open_source=false`
5. **tool_is_local**：必须与工具类型匹配
   - BuiltinProgram：`true`
   - RemoteProgram/RemoteWebpage：`false`
6. **安全性**：无硬编码凭据、无数据外泄、无恶意代码
7. **依赖**：所有依赖必须列在 `tool_dependencies` 中，且与项目许可证兼容

---

### 获取帮助

- [文档](./)（即本 `docs/` 目录）
- [GitHub Discussions](https://github.com/TabulexFlow/tabulexflow-desktop/discussions)
- [Issues](https://github.com/TabulexFlow/tabulexflow-desktop/issues)
- **商业版**：如需产品信息或申请内测，请联系 `tabulexflow@outlook.com`

> **贡献者须知**：官方网站 `https://tabulexflow.com`（包括程序与文档中引用的 `/download`、`/feedback`
> 链接）**尚未上线**——这是有意保留的占位链接，待官网上线后即可访问。请在代码中勿将其替换为其他地址。

---

### 许可证

通过贡献代码，您同意签署 [CLA](CLA.md)：您的贡献在本项目中以 AGPL v3 许可证发布，同时您授予项目维护者以其他许可证（包括闭源商业许可证）使用、分发和再许可您贡献的权利。详见 [CLA.md](CLA.md) 与 [LICENSE](../LICENSE.txt) 文件。

---

*感谢您的贡献！*
