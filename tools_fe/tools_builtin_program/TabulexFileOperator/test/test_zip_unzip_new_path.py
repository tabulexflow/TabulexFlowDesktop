# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试压缩/解压标签页 Apply/Preview/Execute 对"新路径"列的处理

规则（2026-09-29 修订，替换原规则）：
- Apply：唯一可写 New Path 的按钮；按分组计算并写入"新路径"列，New Path 变化的行清空 Result。
- Preview/Execute：不修改任何行的 Old/New Path；只使用用户已填写的非空"新路径"，
  为空则视为未设置，往 Result 写提示并跳过该行。
"""
import os
import sys
import zipfile

import pytest
import wx

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tfo_ZipWorker import tfo_ZipWorker  # noqa: E402
from tfo_UnZipWorker import tfo_UnZipWorker  # noqa: E402
from tfo_utils.tfo_worker_mode import WorkerMode  # noqa: E402
from tfo_utils.tfo_i18n_manager import translate  # noqa: E402


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


@pytest.fixture(autouse=True)
def _patch_call_after(monkeypatch):
    """工作线程通过 wx.CallAfter 回写 Grid，测试环境直接同步执行"""
    monkeypatch.setattr(wx, "CallAfter", lambda fn, *a, **k: fn(*a, **k))


def _make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries:
            if name.endswith("/"):
                zf.writestr(zipfile.ZipInfo(name), b"")
            else:
                zf.writestr(name, data.encode())


class TestUnzipNewPath:
    """解压 EXECUTE：尊重用户填写的"新路径"；空"新路径"行自动填入并解压"""

    def _run(self, rows, save_dir=None):
        worker = tfo_UnZipWorker(
            _FakeTool(rows),
            use_match_name=False,
            save_dir=save_dir,
            file_conflict_method="overwrite",
            dir_conflict_method="merge",
            worker_mode=WorkerMode.EXECUTE,
        )
        worker.run()

    def test_empty_new_path_skipped(self, tmp_path):
        """Old Path 存在但 New Path 为空：不自动 Apply；写"新路径未设置"并跳过"""
        archive = tmp_path / "a.zip"
        _make_zip(str(archive), [("a.txt", "A")])
        out = tmp_path / "out"
        rows = [{
            _FakeGrid.COL_OLD_PATH: str(archive),
            _FakeGrid.COL_NEW_PATH: "",
            _FakeGrid.COL_RESULT: "",
        }]
        self._run(rows, save_dir=str(out))
        # 空新路径不回填，提示未设置且不解压
        assert rows[0][_FakeGrid.COL_NEW_PATH] == ""
        assert rows[0][_FakeGrid.COL_RESULT] == translate("warning_new_path_not_set")
        assert not (out / "a").exists()

    def test_uses_user_new_path(self, tmp_path):
        """New Path 已填写：按用户填写的路径解压，不再自动覆盖"""
        archive = tmp_path / "a.zip"
        _make_zip(str(archive), [("a.txt", "A"), ("sub/b.txt", "B")])
        dest = tmp_path / "custom" / "mydest"
        rows = [{
            _FakeGrid.COL_OLD_PATH: str(archive),
            _FakeGrid.COL_NEW_PATH: str(dest),
            _FakeGrid.COL_RESULT: "",
        }]
        self._run(rows)
        assert os.path.exists(str(dest / "sub" / "b.txt"))
        # 新路径列保持用户填写的值，不被重写
        assert rows[0][_FakeGrid.COL_NEW_PATH] == str(dest)

    def test_mixed_rows_missing_and_filled(self, tmp_path):
        """部分行 New Path 为空：空行提示未设置并跳过，已填行正常解压"""
        a1 = tmp_path / "one.zip"
        a2 = tmp_path / "two.zip"
        _make_zip(str(a1), [("x.txt", "X")])
        _make_zip(str(a2), [("y.txt", "Y")])
        dest2 = tmp_path / "out2"
        rows = [
            {_FakeGrid.COL_OLD_PATH: str(a1), _FakeGrid.COL_NEW_PATH: "", _FakeGrid.COL_RESULT: ""},
            {_FakeGrid.COL_OLD_PATH: str(a2), _FakeGrid.COL_NEW_PATH: str(dest2), _FakeGrid.COL_RESULT: ""},
        ]
        self._run(rows)
        # 空新路径行不自动回填、不解压；已填行正常解压
        assert rows[0][_FakeGrid.COL_NEW_PATH] == ""
        assert rows[0][_FakeGrid.COL_RESULT] == translate("warning_new_path_not_set")
        assert not (tmp_path / "one").exists()
        assert os.path.exists(str(dest2 / "y.txt"))
        assert rows[1][_FakeGrid.COL_NEW_PATH] == str(dest2)


class TestZipNewPath:
    """压缩 EXECUTE：尊重用户填写的"新路径"；空"新路径"行自动计算填入并执行"""

    def _run(self, rows, save_dir=None):
        worker = tfo_ZipWorker(
            _FakeTool(rows),
            use_old_path=True,
            use_match_name=False,
            save_dir=save_dir,
            file_conflict_method="overwrite",
            dir_conflict_method="replace",
            worker_mode=WorkerMode.EXECUTE,
        )
        worker.run()

    def test_empty_new_path_skipped(self, tmp_path):
        """Old Path 存在但 New Path 为空：不自动 Apply；写"新路径未设置"并跳过"""
        src = tmp_path / "src"
        src.mkdir()
        f = src / "file.txt"
        f.write_text("data", encoding="utf-8")
        rows = [{
            _FakeGrid.COL_OLD_PATH: str(f),
            _FakeGrid.COL_NEW_PATH: "",
            _FakeGrid.COL_RESULT: "",
        }]
        self._run(rows)
        expected_zip = src / "src.zip"
        # 空新路径不回填、不创建 ZIP，提示未设置
        assert rows[0][_FakeGrid.COL_NEW_PATH] == ""
        assert rows[0][_FakeGrid.COL_RESULT] == translate("warning_new_path_not_set")
        assert not expected_zip.exists()

    def test_uses_user_new_path(self, tmp_path):
        """New Path 已填写：ZIP 创建在用户填写的路径，内部结构仍按分组规则"""
        src = tmp_path / "src"
        src.mkdir()
        f = src / "file.txt"
        f.write_text("data", encoding="utf-8")
        dest_zip = tmp_path / "out" / "custom.zip"
        rows = [{
            _FakeGrid.COL_OLD_PATH: str(f),
            _FakeGrid.COL_NEW_PATH: str(dest_zip),
            _FakeGrid.COL_RESULT: "",
        }]
        self._run(rows)
        assert os.path.exists(str(dest_zip))
        with zipfile.ZipFile(str(dest_zip)) as zf:
            # 分组名为父目录名 "src"，ZIP 内部结构按分组规则
            assert zf.namelist() == ["src/file.txt"]
        # 新路径列保持用户填写的值
        assert rows[0][_FakeGrid.COL_NEW_PATH] == str(dest_zip)