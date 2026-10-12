# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试解压标签页 - 压缩包第一层仅含一个目录时自动剥离逻辑

场景：压缩包第一层有且只有一个目录（无论该目录名是否与压缩包名相同），解压时
剥离该首层目录，使其内容落在单层目标子目录内；第一层有多个目录、或存在文件时
不剥离；压缩包内的深层目录不受影响。
"""
import os
import sys
import zipfile

import pytest
import wx

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tfo_UnZipWorker import (  # noqa: E402
    detect_single_top_dir,
    unwrap_member_parts,
    tfo_UnZipWorker,
)
from tfo_utils.tfo_worker_mode import WorkerMode  # noqa: E402


class _FakeGrid:
    COL_OLD_PATH = 0
    COL_MATCH_NAME = 1
    COL_NEW_PATH = 2
    COL_RESULT = 3

    def __init__(self, rows):
        self.rows = rows

    def GetNumberRows(self):
        return len(self.rows)

    def GetNumberCols(self):
        return 8

    def GetCellValue(self, row, col):
        return self.rows[row].get(col, "")

    def SetCellValue(self, row, col, val):
        self.rows[row][col] = val

    def queue_cell_value(self, row, col, val):
        # 测试中 Worker 同步运行，直接落盘以保持断言即时可见
        self.SetCellValue(row, col, val)


class _FakeSearchInput:
    def GetValue(self):
        return ""


class _FakeTool:
    def __init__(self, rows):
        self.file_grid = _FakeGrid(rows)
        self.input_search_path01 = _FakeSearchInput()

    def is_valid_path(self, path):
        return True


def _make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries:
            if name.endswith("/"):
                zf.writestr(zipfile.ZipInfo(name), b"")
            else:
                zf.writestr(name, data.encode())


def _extract(tmp_path, archive_name, entries, match_name="", use_match_name=False):
    """执行解压并返回 (保存目录内相对路径列表, 目标子目录绝对路径)"""
    archive = tmp_path / archive_name
    _make_zip(str(archive), entries)
    save_dir = tmp_path / ("out_" + archive_name)
    dest_top = str(save_dir / strip_archive_extension(archive_name)) \
        if not match_name else str(save_dir / match_name)
    rows = [{
        _FakeGrid.COL_OLD_PATH: str(archive),
        _FakeGrid.COL_MATCH_NAME: match_name,
        _FakeGrid.COL_NEW_PATH: dest_top,
        _FakeGrid.COL_RESULT: "",
    }]
    worker = tfo_UnZipWorker(
        _FakeTool(rows),
        use_match_name=use_match_name,
        save_dir=str(save_dir),
        file_conflict_method="overwrite",
        dir_conflict_method="merge",
        worker_mode=WorkerMode.EXECUTE,
    )
    worker.run()
    rel_paths = []
    for root, dirs, files in os.walk(dest_top):
        rel = os.path.relpath(root, dest_top)
        for d in dirs:
            rel_paths.append(os.path.join(rel, d) if rel != "." else d)
        for f in files:
            rel_paths.append(os.path.join(rel, f) if rel != "." else f)
    return sorted(rel_paths), dest_top


def strip_archive_extension(path):
    return os.path.splitext(os.path.basename(path))[0]


class TestSingleTopDirDetect:
    """detect_single_top_dir 单元测试"""

    def test_single_top_dir_explicit_entry(self):
        members = [("SubFolder01", True), ("SubFolder01/a.txt", False)]
        assert detect_single_top_dir(members) == "SubFolder01"

    def test_single_top_dir_any_name(self):
        """首层目录名与压缩包名无关：任何单一首层目录都会被检测到"""
        members = [("OtherFolder02", True), ("OtherFolder02/x.txt", False)]
        assert detect_single_top_dir(members) == "OtherFolder02"

    def test_single_top_dir_implicit_no_dir_entry(self):
        """无显式目录条目，仅有以首层段为前缀的文件条目时仍能检测到"""
        members = [("SubFolder01/Sub_TestText03.txt", False)]
        assert detect_single_top_dir(members) == "SubFolder01"

    def test_multiple_top_dirs_not_detected(self):
        members = [("A", True), ("A/x.txt", False), ("B", True), ("B/y.txt", False)]
        assert detect_single_top_dir(members) is None

    def test_top_dir_with_top_file_not_detected(self):
        members = [("A", True), ("A/x.txt", False), ("readme.txt", False)]
        assert detect_single_top_dir(members) is None

    def test_only_top_files_not_detected(self):
        members = [("a.txt", False), ("b.txt", False)]
        assert detect_single_top_dir(members) is None

    def test_single_top_file_not_detected(self):
        members = [("a.txt", False)]
        assert detect_single_top_dir(members) is None

    def test_empty_members_not_detected(self):
        assert detect_single_top_dir([]) is None


class TestUnwrapMemberParts:
    """unwrap_member_parts 单元测试"""

    def test_unwrap_dir_member_itself(self):
        assert unwrap_member_parts("SubFolder01", "SubFolder01") == []

    def test_unwrap_file_under_top_dir(self):
        assert unwrap_member_parts("SubFolder01/a.txt", "SubFolder01") == ["a.txt"]

    def test_unwrap_nested_path(self):
        assert unwrap_member_parts("SubFolder01/sub/deep.txt", "SubFolder01") == ["sub", "deep.txt"]

    def test_other_top_level_untouched(self):
        assert unwrap_member_parts("Other/c.txt", "SubFolder01") == ["Other", "c.txt"]

    def test_deep_same_name_dir_preserved(self):
        assert unwrap_member_parts("SubFolder01/SubFolder01/x.txt", "SubFolder01") == ["SubFolder01", "x.txt"]

    def test_no_unwrap_when_no_match(self):
        assert unwrap_member_parts("a.txt", None) == ["a.txt"]

    def test_case_insensitive_unwrap(self):
        assert unwrap_member_parts("SubFolder01/a.txt", "subfolder01") == ["a.txt"]


@pytest.fixture(autouse=True)
def _patch_call_after(monkeypatch):
    """解压线程通过 wx.CallAfter 回写 Grid，测试环境直接同步执行"""
    monkeypatch.setattr(wx, "CallAfter", lambda fn, *a, **k: fn(*a, **k))


class TestUnzipExecution:
    """解压执行端到端测试"""

    def test_single_top_dir_flattened(self, tmp_path):
        """第一层仅含一个目录：其内容落到单层目录，首层目录不创建"""
        rel, dest = _extract(tmp_path, "SubFolder01.zip", [
            ("SubFolder01/", ""),
            ("SubFolder01/a.txt", "A"),
            ("SubFolder01/sub/b.txt", "B"),
        ])
        assert rel == ["a.txt", "sub", "sub/b.txt"]
        assert not os.path.exists(os.path.join(dest, "SubFolder01"))

    def test_single_top_dir_other_name_flattened(self, tmp_path):
        """第一层仅含一个目录且名字与压缩包不同（OtherFolder02）：同样剥离"""
        rel, dest = _extract(tmp_path, "SubFolder01.zip", [
            ("OtherFolder02/", ""),
            ("OtherFolder02/Sub_TestText03.txt", "T"),
        ])
        assert rel == ["Sub_TestText03.txt"]
        assert not os.path.exists(os.path.join(dest, "OtherFolder02"))

    def test_no_explicit_dir_entry_flattened(self, tmp_path):
        """压缩包不含显式目录条目（仅文件条目 SubFolder01/Sub_TestText03.txt）：
        首层目录同样被剥离，不产生双层目录"""
        rel, dest = _extract(tmp_path, "SubFolder01.zip", [
            ("SubFolder01/Sub_TestText03.txt", "T"),
        ])
        assert rel == ["Sub_TestText03.txt"]
        assert not os.path.exists(os.path.join(dest, "SubFolder01"))
        assert os.path.exists(os.path.join(dest, "Sub_TestText03.txt"))

    def test_deep_same_name_dir_preserved(self, tmp_path):
        """深层同名目录不受影响"""
        rel, dest = _extract(tmp_path, "SubFolder01.zip", [
            ("SubFolder01/", ""),
            ("SubFolder01/SubFolder01/deep.txt", "D"),
        ])
        assert rel == ["SubFolder01", "SubFolder01/deep.txt"]
        assert os.path.exists(os.path.join(dest, "SubFolder01", "deep.txt"))

    def test_multiple_top_dirs_structure_preserved(self, tmp_path):
        """第一层有多个目录：不剥离，内部结构原样保留"""
        rel, dest = _extract(tmp_path, "SubFolder01.zip", [
            ("A/", ""),
            ("A/x.txt", "X"),
            ("B/", ""),
            ("B/y.txt", "Y"),
        ])
        assert rel == ["A", "A/x.txt", "B", "B/y.txt"]

    def test_top_dir_with_top_file_structure_preserved(self, tmp_path):
        """第一层目录与文件并存：不剥离，内部结构原样保留"""
        rel, _ = _extract(tmp_path, "SubFolder01.zip", [
            ("A/", ""),
            ("A/x.txt", "X"),
            ("readme.txt", "R"),
        ])
        assert rel == ["A", "A/x.txt", "readme.txt"]

    def test_only_top_files_structure_preserved(self, tmp_path):
        """第一层只有文件：不剥离，内部结构原样保留"""
        rel, _ = _extract(tmp_path, "SubFolder01.zip", [
            ("a.txt", "A"),
            ("b.txt", "B"),
        ])
        assert rel == ["a.txt", "b.txt"]

    def test_match_name_group_dir_flattened(self, tmp_path):
        """按匹配名分组时 New Path 不变，首层单一目录同样被剥离"""
        rel, dest = _extract(tmp_path, "SubFolder01.zip", [
            ("SubFolder01/", ""),
            ("SubFolder01/a.txt", "A"),
        ], match_name="MyGroup", use_match_name=True)
        assert rel == ["a.txt"]
        assert dest.endswith("MyGroup")
        assert not os.path.exists(os.path.join(dest, "SubFolder01"))