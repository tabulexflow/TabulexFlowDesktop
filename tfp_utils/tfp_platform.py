# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""跨平台构建/分发命名与判定的唯一权威来源（前端）。

背景：本项目三端（后端主程序 / RemoteProgram 子工具UI / 前端主程序）均可被
编译为 Windows 与 Linux 产物。Linux 侧按发行版家族细分为 Debian 系与 Red Hat 系，
因两者的 glibc/工具链不保证 ABI 兼容，产物与编译缓存必须按家族隔离，避免交叉复用。
为避免产物相互覆盖、并让后端能按客户端平台正确下发子工具，需要一个统一的平台
标签判定函数。本函数即前端侧的权威实现。

平台标签：
  - Windows            → 'windows'
  - Debian 系（Debian/Ubuntu/Mint 等）→ 'linux-deb'
  - Red Hat 系（RHEL/CentOS/Fedora/Rocky/Alma 等）→ 'linux-rpm'
  - 其余（含未识别的 Linux 发行版、macOS）→ 直接报错终止（fail-closed）

注意：后端为隔离部署，维护有等价的隔离实现，不跨工程 import，避免前端/后端解耦被破坏。
"""

import sys

# 平台标签常量（统一小写）
PLATFORM_WINDOWS = 'windows'
PLATFORM_LINUX_DEB = 'linux-deb'
PLATFORM_LINUX_RPM = 'linux-rpm'

# Debian 家族发行版 ID（/etc/os-release 的 ID）
_DEBIAN_FAMILY_IDS = frozenset({
    'debian', 'ubuntu', 'linuxmint', 'mint', 'pop', 'elementary', 'kali',
    'raspbian', 'devuan', 'deepin', 'zorin', 'mx', 'neon', 'parrot',
})
# Red Hat 家族发行版 ID（含 RHEL 衍生版）
_REDHAT_FAMILY_IDS = frozenset({
    'rhel', 'redhat', 'centos', 'fedora', 'rocky', 'almalinux', 'alma',
    'ol', 'oracle', 'scientific', 'amzn',
})
# ID_LIKE 归一化线索
_DEBIAN_LIKE = frozenset({'debian', 'ubuntu'})
_REDHAT_LIKE = frozenset({'rhel', 'fedora', 'centos'})


def _read_os_release(path='/etc/os-release'):
    """解析 /etc/os-release，返回 {KEY: value}；读取失败返回 None。"""
    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                data[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        return None
    return data


def detect_linux_distro_family():
    """返回 Linux 发行版家族：'deb' 或 'rpm'；未识别时抛 RuntimeError。"""
    info = _read_os_release()
    if info is None:
        raise RuntimeError(
            "无法读取 /etc/os-release，无法判定 Linux 发行版家族；"
            "仅支持 Debian 与 Red Hat 系（fail-closed）")
    distro_id = (info.get('ID') or '').strip().lower()
    id_like = {t.strip().lower() for t in (info.get('ID_LIKE') or '').split()}
    if distro_id in _DEBIAN_FAMILY_IDS or (id_like & _DEBIAN_LIKE):
        return 'deb'
    if distro_id in _REDHAT_FAMILY_IDS or (id_like & _REDHAT_LIKE):
        return 'rpm'
    raise RuntimeError(
        "不支持的 Linux 发行版: ID=%r ID_LIKE=%r；"
        "仅支持 Debian 系与 Red Hat 系（fail-closed）"
        % (info.get('ID'), info.get('ID_LIKE')))


def get_platform_tag() -> str:
    """返回当前平台的标签：'windows' / 'linux-deb' / 'linux-rpm'。

    - Windows 系（sys.platform 以 'win' 开头）→ 'windows'
    - Linux → 读 /etc/os-release 判定 Debian 系 / Red Hat 系
    - 未识别的平台或发行版 → 抛 RuntimeError（fail-closed，不静默回退）
    """
    if sys.platform.startswith('win'):
        return PLATFORM_WINDOWS
    if sys.platform.startswith('linux'):
        family = detect_linux_distro_family()
        return PLATFORM_LINUX_DEB if family == 'deb' else PLATFORM_LINUX_RPM
    raise RuntimeError(
        "不支持的运行平台: sys.platform=%r；仅支持 Windows 与 Linux(Debian/Red Hat)（fail-closed）"
        % sys.platform)
