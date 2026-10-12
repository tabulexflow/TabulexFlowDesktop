#!/usr/bin/env python3
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""合并式产物 SHA-256 校验清单生成器（tfpdesktop_build.bat / tfpdesktop_package_linux.sh 共用）。

背景：Windows 与 Linux 构建会先后写入同一份校验清单；若各自清空整份文件，会删掉
另一平台已编译产物的记录。本脚本改为"仅移除同平台旧记录，再追加本次新产物记录"，
从而两平台可共存、互不覆盖。

清单文件：dist/SHA256SUMS.txt（格式 "<hash>  <相对路径>"，LF 行尾，兼容
`sha256sum -c SHA256SUMS.txt`）。

平台判定（--platform）：
  windows : 移除路径以 .exe 结尾的旧记录
  linux   : 移除路径以 .deb / .rpm / .AppImage 结尾的旧记录
另：无论平台，均移除与本次新产物相对路径完全相同的旧记录（用于覆盖 Linux
onefile 无扩展名的二进制行，以及同版本重建的场景）。

用法：
  tfpdesktop_checksum_manifest.py --platform {windows,linux} --manifest <路径> REL=ABS [REL=ABS ...]
  其中 REL 为写入清单的相对路径（相对 dist），ABS 为产物在磁盘上的实际路径。
成功时按顺序为每个产物输出一行其 SHA-256；任一产物读取失败则以非零退出且不改写清单。
"""
import argparse
import hashlib
import os
import sys

# 各平台旧记录所用的产物扩展名（小写，含点）
PLATFORM_SUFFIXES = {
    "windows": (".exe",),
    "linux": (".deb", ".rpm", ".appimage"),
}


def _read_manifest_lines(path):
    """读取现有清单并归一化行尾；文件不存在时返回空列表。"""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="ascii", errors="replace") as f:
        text = f.read()
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _line_path(line):
    """从清单行 "<hash>  <相对路径>" 中取出相对路径（无有效路径时返回空串）。"""
    line = line.strip()
    if not line:
        return ""
    parts = line.split(None, 1)
    if len(parts) < 2:
        return ""
    path = parts[1].strip()
    # 兼容 sha256sum 的二进制标记 "hash *path"
    if path.startswith("*"):
        path = path[1:]
    return path


def main():
    parser = argparse.ArgumentParser(description="Merge per-platform SHA-256 manifest entries.")
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORM_SUFFIXES))
    parser.add_argument("--manifest", required=True, help="清单文件路径（dist/SHA256SUMS.txt）")
    parser.add_argument("pairs", nargs="+", metavar="REL=ABS",
                        help="本次新产物：相对 dist 的路径=产物磁盘路径")
    args = parser.parse_args()

    entries = []  # [(rel, digest)]
    for pair in args.pairs:
        rel, sep, abs_path = pair.partition("=")
        if not sep or not rel or not abs_path:
            print(f"[FAIL] invalid artifact argument (expected REL=ABS): {pair}", file=sys.stderr)
            return 1
        if not os.path.isfile(abs_path):
            print(f"[FAIL] artifact not found: {abs_path}", file=sys.stderr)
            return 1
        with open(abs_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        entries.append((rel, digest))

    suffixes = PLATFORM_SUFFIXES[args.platform]
    new_rels = {rel for rel, _ in entries}

    # 保留所有非本平台旧记录（含另一平台记录），仅剔除本平台旧行与同路径旧行；
    # 空行不携带校验信息，直接丢弃，避免移除某行后残留孤立空行。
    kept = []
    for line in _read_manifest_lines(args.manifest):
        if not line.strip():
            continue
        path = _line_path(line)
        if path and (path.lower().endswith(suffixes) or path in new_rels):
            continue
        kept.append(line)
    for rel, digest in entries:
        kept.append(f"{digest}  {rel}")

    with open(args.manifest, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(kept) + "\n")

    for _, digest in entries:
        print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
