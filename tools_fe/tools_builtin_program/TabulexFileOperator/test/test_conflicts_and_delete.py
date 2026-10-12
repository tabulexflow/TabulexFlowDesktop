# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TabulexFileOperator 回归测试：冲突处理、去重执行、删除标记

覆盖以下回归场景（BFM-01 ~ BFM-06）：
- BFM-01：移动/复制在目标已存在于磁盘时，必须按文件/目录冲突策略处理
          （跳过 / 覆盖 / 合并 / 替换）。
- BFM-02：去重执行不得依赖异步写入 Grid 的 [WILL DELETE] 文本，须以本地记录为准。
- BFM-03：删除标记不得写入"新路径"列（会破坏"删除目标=新路径"流程），
          应写入"执行结果"列。
- BFM-04：目录合并时同名文件按文件冲突下拉框处理（跳过/覆盖）。
- BFM-05：同一 Grid 多源→同一目标目录且选择合并时，所有行统一走合并（不得嵌套）。
- BFM-06：压缩默认保存路径按各路径的父目录求公共父路径（单文件不得把文件当目录）。
"""
import os
import sys
import shutil
import types
import logging

import pytest
import wx

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import tool_main  # noqa: E402
from tfo_RenameMoveWorker import tfo_RenameMoveWorker  # noqa: E402
from tfo_CopyWorker import tfo_CopyWorker  # noqa: E402
from tfo_ZipWorker import tfo_ZipWorker  # noqa: E402
from tfo_UnZipWorker import tfo_UnZipWorker  # noqa: E402
import tfo_DeleteWorker as _delete_worker_module  # noqa: E402
import tfo_DuplicateWorker as _duplicate_worker_module  # noqa: E402
from tfo_DeleteWorker import tfo_DeleteWorker  # noqa: E402
from tfo_DuplicateWorker import tfo_DuplicateWorker  # noqa: E402
from tfo_utils.tfo_worker_mode import WorkerMode  # noqa: E402
from tfo_utils.tfo_i18n_manager import translate  # noqa: E402


class _FakeGrid:
    COL_OLD_PATH = 0
    COL_NEW_PATH = 1
    COL_MATCH_NAME = 2
    COL_RESULT = 3

    def __init__(self, rows):
        self.rows = rows

    def GetNumberRows(self):
        return len(self.rows)

    def GetNumberCols(self):
        return 13

    def GetCellValue(self, row, col):
        return self.rows[row].get(col, "")

    def SetCellValue(self, row, col, val):
        self.rows[row][col] = val

    def queue_cell_value(self, row, col, val):
        # 测试中 Worker 同步运行，直接落盘以保持断言即时可见
        self.SetCellValue(row, col, val)

    def ForceRefresh(self):
        pass

    def Update(self):
        pass


class _FakeCombo:
    def __init__(self, selection):
        self.selection = selection

    def GetSelection(self):
        return self.selection


class _FakeStatusBar:
    def SetStatusText(self, *args, **kwargs):
        pass


class _FakeInput:
    def __init__(self, value=""):
        self.value = value

    def GetValue(self):
        return self.value


class _FakeTool:
    def __init__(self, rows, file_conflict=0, dir_conflict=0):
        self.file_grid = _FakeGrid(rows)
        self.combo_file_conflict0202 = _FakeCombo(file_conflict)
        self.combo_dir_conflict0202 = _FakeCombo(dir_conflict)
        self.combo_file_conflict0302 = _FakeCombo(file_conflict)
        self.combo_dir_conflict0302 = _FakeCombo(dir_conflict)
        self.combo_file_conflict0402 = _FakeCombo(file_conflict)
        self.combo_dir_conflict0402 = _FakeCombo(dir_conflict)
        self.status_bar = _FakeStatusBar()
        self.input_search_path01 = _FakeInput()
        self.input_source_path03 = _FakeInput()
        self.input_source_path04 = _FakeInput()
        self.input_dest_path03 = _FakeInput()
        self.input_dest_path04 = _FakeInput()
        self.combo_create_folder03 = _FakeCombo(0)
        self.combo_create_folder04 = _FakeCombo(0)
        self.create_folder_mapping = {0: "no_subdirectories"}
        self.combo_naming_method02 = _FakeCombo(0)
        self.naming_method_mapping = {0: "original_name"}
        self.input_naming_text02 = _FakeInput()
        self.input_naming_oldtext = _FakeInput()
        self.input_naming_position02 = _FakeInput()
        self.input_length02 = _FakeInput()
        self.check_number_pos_start02 = _FakeInput(False)
        self.radio_number_scope_none02 = _FakeInput(True)
        self.radio_number_scope_dir02 = _FakeInput(False)
        self.radio_number_scope_match02 = _FakeInput(False)
        self.radio_replace_mode_text02 = _FakeInput(True)
        self.radio_replace_mode_position02 = _FakeInput(False)
        self.radio_affix_mode_suffix02 = _FakeInput(True)
        self.radio_affix_mode_prefix02 = _FakeInput(False)
        self.radio_case_mode_upper02 = _FakeInput(True)
        self.radio_case_mode_lower02 = _FakeInput(False)
        self.radio_case_mode_camel02 = _FakeInput(False)
        self.radio_case_mode_capitalize02 = _FakeInput(False)
        self.radio_mp3_artist_first02 = _FakeInput(True)
        self.radio_mp3_title_first02 = _FakeInput(False)
        self.radio_mp3_title_only02 = _FakeInput(False)
        self._current_op_entry = None
        self._op_history_manager = None

    def is_valid_path(self, path):
        return bool(path) and os.path.isabs(path)

    def get_combo_box_method(self, combo_box, mapping_dict):
        return mapping_dict.get(combo_box.GetSelection())

    def merge_directories(self, src_dir, dst_dir, is_move=False, file_conflict="skip"):
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir, exist_ok=True)
        for item in os.listdir(src_dir):
            src_item = os.path.join(src_dir, item)
            dst_item = os.path.join(dst_dir, item)
            if os.path.isdir(src_item) and os.path.isdir(dst_item):
                self.merge_directories(src_item, dst_item, is_move, file_conflict)
                continue
            if os.path.exists(dst_item):
                if file_conflict != "overwrite":
                    continue
                if os.path.isdir(dst_item):
                    shutil.rmtree(dst_item)
                else:
                    os.remove(dst_item)
            if os.path.isdir(src_item):
                if is_move:
                    shutil.move(src_item, dst_item)
                else:
                    shutil.copytree(src_item, dst_item, symlinks=True)
            elif is_move:
                shutil.move(src_item, dst_item)
            else:
                shutil.copy2(src_item, dst_item)
        if is_move and os.path.exists(src_dir):
            try:
                os.rmdir(src_dir)
            except OSError:
                pass


@pytest.fixture(autouse=True)
def _sync_call_after(monkeypatch):
    """默认把 wx.CallAfter 置为同步执行，聚焦文件系统结果"""
    monkeypatch.setattr(wx, "CallAfter", lambda fn, *a, **k: fn(*a, **k))


class TestMoveCopyDiskConflict:
    """BFM-01：目标已存在时按冲突策略处理"""

    def test_move_dir_to_existing_dir_merge(self, tmp_path):
        src_a = tmp_path / "src" / "A"
        dst_a = tmp_path / "dst" / "A"
        src_a.mkdir(parents=True)
        dst_a.mkdir(parents=True)
        (src_a / "s.txt").write_text("SRC", encoding="utf-8")
        (dst_a / "d.txt").write_text("DST", encoding="utf-8")

        rows = [{0: str(src_a), 1: str(dst_a), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, dir_conflict=1),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        assert (dst_a / "s.txt").read_text(encoding="utf-8") == "SRC"
        assert (dst_a / "d.txt").read_text(encoding="utf-8") == "DST"
        # 不应产生 dst/A/A 嵌套
        assert not (dst_a / "A").exists()
        assert not src_a.exists()

    def test_move_file_to_existing_file_skip(self, tmp_path):
        src_f = tmp_path / "src" / "f.txt"
        dst_f = tmp_path / "dst" / "f.txt"
        src_f.parent.mkdir(parents=True)
        dst_f.parent.mkdir(parents=True)
        src_f.write_text("NEW", encoding="utf-8")
        dst_f.write_text("OLD", encoding="utf-8")

        rows = [{0: str(src_f), 1: str(dst_f), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, file_conflict=0),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        # 跳过：目标不变，源保留
        assert dst_f.read_text(encoding="utf-8") == "OLD"
        assert src_f.read_text(encoding="utf-8") == "NEW"

    def test_move_file_to_existing_file_overwrite(self, tmp_path):
        src_f = tmp_path / "src" / "f.txt"
        dst_f = tmp_path / "dst" / "f.txt"
        src_f.parent.mkdir(parents=True)
        dst_f.parent.mkdir(parents=True)
        src_f.write_text("NEW", encoding="utf-8")
        dst_f.write_text("OLD", encoding="utf-8")

        rows = [{0: str(src_f), 1: str(dst_f), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, file_conflict=1),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        assert dst_f.read_text(encoding="utf-8") == "NEW"
        assert not src_f.exists()

    def test_copy_dir_to_existing_dir_replace(self, tmp_path):
        src_a = tmp_path / "src" / "A"
        dst_a = tmp_path / "dst" / "A"
        src_a.mkdir(parents=True)
        dst_a.mkdir(parents=True)
        (src_a / "s.txt").write_text("SRC", encoding="utf-8")
        (dst_a / "d.txt").write_text("DST", encoding="utf-8")

        rows = [{0: str(src_a), 1: str(dst_a), 2: "", 3: ""}]
        tfo_CopyWorker(_FakeTool(rows, dir_conflict=2),
                       worker_mode=WorkerMode.EXECUTE).run()

        # 替换：旧内容被删除，仅保留新内容
        assert (dst_a / "s.txt").read_text(encoding="utf-8") == "SRC"
        assert not (dst_a / "d.txt").exists()
        # 源目录不被删除
        assert src_a.exists()

    def test_move_reads_move_tab_conflict_combo(self, tmp_path):
        """BFM-13：移动 Worker 读取 Tab03(0302) 的冲突下拉框，而非重命名 Tab(0202)"""
        src_f = tmp_path / "src" / "f.txt"
        dst_f = tmp_path / "dst" / "f.txt"
        src_f.parent.mkdir(parents=True)
        dst_f.parent.mkdir(parents=True)
        src_f.write_text("NEW", encoding="utf-8")
        dst_f.write_text("OLD", encoding="utf-8")

        rows = [{0: str(src_f), 1: str(dst_f), 2: "", 3: ""}]
        tool = _FakeTool(rows)
        # 重命名 Tab：覆盖；移动 Tab：跳过
        tool.combo_file_conflict0202 = _FakeCombo(1)
        tool.combo_file_conflict0302 = _FakeCombo(0)

        tfo_RenameMoveWorker(tool, is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        # 应使用移动 Tab 的"跳过"：目标不变、源保留
        assert dst_f.read_text(encoding="utf-8") == "OLD"
        assert src_f.read_text(encoding="utf-8") == "NEW"


def _patch_recycle(monkeypatch, module):
    """把模块内 delete_to_recycle 替换为直接删除并返回 0"""
    def _fake_delete(path):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
        return 0
    monkeypatch.setattr(module, "delete_to_recycle", _fake_delete)


class TestDuplicateExecuteNotDependentOnGrid:
    """BFM-02：去重执行不依赖异步写入 Grid 的 [WILL DELETE]"""

    def test_execute_deletes_without_grid_writeback(self, tmp_path, monkeypatch):
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        f1 = d1 / "x.txt"
        f2 = d2 / "x.txt"
        f1.write_text("SAMEDATA", encoding="utf-8")
        f2.write_text("SAMEDATA", encoding="utf-8")

        # 模拟主线程未处理 CallAfter：Grid 不会被异步更新
        monkeypatch.setattr(wx, "CallAfter", lambda fn, *a, **k: None)
        _patch_recycle(monkeypatch, _duplicate_worker_module)

        rows = [{0: str(f1), 1: "", 2: "", 3: ""},
                {0: str(f2), 1: "", 2: "", 3: ""}]
        tfo_DuplicateWorker(_FakeTool(rows), "filename", "keep_create_time_latest",
                            worker_mode=WorkerMode.EXECUTE).run()

        # 即使 Grid 未回写，仍应删掉其中一个重复文件
        assert sum(os.path.exists(p) for p in (f1, f2)) == 1


class TestDeleteNewPathTarget:
    """BFM-03：删除标记不得写入新路径列"""

    def test_apply_keeps_new_path_and_marks_result(self, tmp_path, monkeypatch):
        f = tmp_path / "f.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: "", 1: str(f), 2: "", 3: ""}]
        tool = _FakeTool(rows)
        _patch_recycle(monkeypatch, _delete_worker_module)

        tfo_DeleteWorker(tool, delete_original=False, paths_info=[(0, str(f), "new")],
                         worker_mode=WorkerMode.APPLY, delete_filter="delete_all").run()

        # 新路径列保留原值，标记写入执行结果列
        assert rows[0][1] == str(f)
        assert rows[0][3] == "[WILL DELETE]"

        # 执行：按新路径列（未被破坏）删除
        paths_info = [(0, rows[0][1].strip(), "new")]
        tfo_DeleteWorker(tool, delete_original=False, paths_info=paths_info,
                         worker_mode=WorkerMode.EXECUTE, delete_filter="delete_all").run()
        assert not f.exists()
        assert rows[0][3] != ""


def _merge_host():
    """把真实的 tool_main.merge_directories 绑定到最小宿主对象上"""
    host = types.SimpleNamespace()
    host.merge_directories = types.MethodType(
        tool_main.tfo_TabulexFileOperatorTool.merge_directories, host)
    return host


class TestMergeDirectoriesFileConflict:
    """BFM-04：目录合并同名文件按文件冲突下拉框处理"""

    def test_skip_keeps_existing_file(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "same.txt").write_text("SRC", encoding="utf-8")
        (dst / "same.txt").write_text("DST", encoding="utf-8")

        _merge_host().merge_directories(str(src), str(dst), is_move=True, file_conflict="skip")

        assert (dst / "same.txt").read_text(encoding="utf-8") == "DST"
        assert (src / "same.txt").read_text(encoding="utf-8") == "SRC"
        # 被跳过的源文件保留，源目录因非空而不删除
        assert src.exists()

    def test_overwrite_replaces_existing_file(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "same.txt").write_text("SRC", encoding="utf-8")
        (dst / "same.txt").write_text("DST", encoding="utf-8")

        _merge_host().merge_directories(str(src), str(dst), is_move=True, file_conflict="overwrite")

        assert (dst / "same.txt").read_text(encoding="utf-8") == "SRC"
        assert not src.exists()


class TestMultiSourceDirMergeNoNesting:
    """BFM-05：多源→同一目标目录且合并时，所有行统一合并，不产生嵌套"""

    def test_all_duplicate_rows_merge(self, tmp_path):
        s1 = tmp_path / "s1"
        s2 = tmp_path / "s2"
        td = tmp_path / "td"
        s1.mkdir()
        s2.mkdir()
        (s1 / "a.txt").write_text("A", encoding="utf-8")
        (s2 / "b.txt").write_text("B", encoding="utf-8")

        rows = [{0: str(s1), 1: str(td), 2: "", 3: ""},
                {0: str(s2), 1: str(td), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, dir_conflict=1),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        assert (td / "a.txt").read_text(encoding="utf-8") == "A"
        assert (td / "b.txt").read_text(encoding="utf-8") == "B"
        # 不得把 s2 整个目录嵌套进 td
        assert not (td / "s2").exists()
        assert not s1.exists()
        assert not s2.exists()


class TestMultiSourceOverwriteReplace:
    """BFM-10/11：多源→同一目标，覆盖/替换时靠前的源也必须被处理（不残留）"""

    def test_file_overwrite_consumes_all_sources(self, tmp_path):
        s1 = tmp_path / "s1.txt"
        s2 = tmp_path / "s2.txt"
        s1.write_text("ONE", encoding="utf-8")
        s2.write_text("TWO", encoding="utf-8")
        tgt = tmp_path / "target.txt"

        rows = [{0: str(s1), 1: str(tgt), 2: "", 3: ""},
                {0: str(s2), 1: str(tgt), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, file_conflict=1),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        # 靠前源文件被移动/覆盖，不再残留；目标保留最后一个源的内容
        assert not s1.exists()
        assert not s2.exists()
        assert tgt.read_text(encoding="utf-8") == "TWO"

    def test_dir_replace_consumes_all_sources(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        (a / "x.txt").write_text("A", encoding="utf-8")
        (b / "y.txt").write_text("B", encoding="utf-8")
        td = tmp_path / "td"

        rows = [{0: str(a), 1: str(td), 2: "", 3: ""},
                {0: str(b), 1: str(td), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, dir_conflict=2),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        # 靠前源目录被替换，不再残留；目标保留最后一个源目录的内容
        assert not a.exists()
        assert not b.exists()
        assert sorted(os.listdir(td)) == ["y.txt"]

    def test_file_skip_keeps_first_and_later_source(self, tmp_path):
        s1 = tmp_path / "s1.txt"
        s2 = tmp_path / "s2.txt"
        s1.write_text("ONE", encoding="utf-8")
        s2.write_text("TWO", encoding="utf-8")
        tgt = tmp_path / "target.txt"

        rows = [{0: str(s1), 1: str(tgt), 2: "", 3: ""},
                {0: str(s2), 1: str(tgt), 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows, file_conflict=0),
                             is_rename=False, worker_mode=WorkerMode.EXECUTE).run()

        # 跳过：第一个源保留为目标，后续同名源跳过并保留原地
        assert not s1.exists()
        assert s2.exists()
        assert tgt.read_text(encoding="utf-8") == "ONE"


class TestZipDefaultSavePath:
    """BFM-06：压缩默认保存路径按父目录求公共父路径"""

    def test_single_file_default_path_uses_parent_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("data", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tfo_ZipWorker(_FakeTool(rows), use_old_path=True, use_match_name=False,
                      save_dir=None, worker_mode=WorkerMode.APPLY).run()

        new_path = rows[0][1]
        # 目标 ZIP 应位于文件的父目录下，而不是 "<文件>/xxx.zip"
        assert os.path.dirname(new_path) == str(tmp_path)
        assert new_path.endswith(".zip")
        assert os.path.isfile(str(f))  # 原文件仍是文件，未被当作目录


class TestDuplicateMarkersInResultColumn:
    """BFM-07：去重应用/预览的状态标记写入结果列，不写入新路径列"""

    def test_markers_not_in_new_path_column(self, tmp_path):
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        f1 = d1 / "x.txt"
        f2 = d2 / "x.txt"
        f1.write_text("SAME", encoding="utf-8")
        f2.write_text("SAME", encoding="utf-8")
        unique = tmp_path / "u.txt"
        unique.write_text("UNIQUE", encoding="utf-8")

        template = [{0: str(f1), 1: "", 2: "", 3: ""},
                    {0: str(f2), 1: "", 2: "", 3: ""},
                    {0: str(unique), 1: "", 2: "", 3: ""}]

        for mode in (WorkerMode.APPLY, WorkerMode.PREVIEW):
            rows = [dict(r) for r in template]
            tfo_DuplicateWorker(_FakeTool(rows), "filename", "keep_create_time_latest",
                                worker_mode=mode).run()
            results = [r[3] for r in rows]
            new_paths = [r[1] for r in rows]

            # 状态标记必须写入结果列
            assert "[WILL RETAIN]" in results
            if mode == WorkerMode.APPLY:
                assert "[WILL DELETE]" in results
                assert "[NO DUPLICATE]" in results
            # 新路径列不得被状态标记污染
            assert all(not v.startswith("[") for v in new_paths)


class TestZipExecuteFlag:
    """BFM-08：ZipWorker.execute_zip 必须与 worker_mode 一致"""

    def test_flag_matches_worker_mode(self):
        rows = [{0: "", 1: "", 2: "", 3: ""}]
        for mode, expected in ((WorkerMode.APPLY, False),
                               (WorkerMode.PREVIEW, False),
                               (WorkerMode.EXECUTE, True)):
            worker = tfo_ZipWorker(_FakeTool(rows), True, False, None, worker_mode=mode)
            assert worker.execute_zip is expected


class TestOpHistoryTabIndex:
    """BFM-09：删除/去重操作级历史的 tab_index 必须正确

    tab_index 由 tool_main 的处理器传入，此处用源码断言防止回归
    （_TAB_LABEL_KEY: 6=删除, 7=去重）。
    """

    def test_delete_and_duplicate_tab_indices(self):
        import inspect
        tool_cls = tool_main.tfo_TabulexFileOperatorTool
        assert "OP_TYPE_DELETE_EXECUTE if execute else OP_TYPE_DELETE_APPLY, 6" in \
            inspect.getsource(tool_cls.execute_delete_in_thread)
        assert "OP_TYPE_DELETE_PREVIEW, 6" in inspect.getsource(tool_cls.on_preview_delete)
        assert "OP_TYPE_DUPLICATE_PREVIEW, 7" in inspect.getsource(tool_cls.on_preview_duplicate)


class TestPreviewRespectsNewPath:
    """Preview 必须尊重用户新路径，且只有 Apply 会写入新路径列（用户确认的语义）"""

    def test_zip_preview_keeps_user_new_path(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        f = src_dir / "file.txt"
        f.write_text("data", encoding="utf-8")
        dest_zip = tmp_path / "custom" / "my.zip"
        rows = [{0: str(f), 1: str(dest_zip), 2: "", 3: ""}]

        tfo_ZipWorker(_FakeTool(rows), True, False, None,
                      worker_mode=WorkerMode.PREVIEW).run()

        # 新路径列保持用户值，结果写结果列
        assert rows[0][1] == str(dest_zip)
        assert rows[0][3] == translate("correct_will_add_to_zip")
        assert not dest_zip.exists()  # Preview 不落盘

    def test_zip_preview_existing_zip_reflects_conflict(self, tmp_path):
        import zipfile
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        f = src_dir / "file.txt"
        f.write_text("data", encoding="utf-8")
        dest_zip = tmp_path / "my.zip"
        with zipfile.ZipFile(str(dest_zip), "w") as zf:
            zf.writestr("src/other.txt", "x")
        rows = [{0: str(f), 1: str(dest_zip), 2: "", 3: ""}]

        tfo_ZipWorker(_FakeTool(rows), True, False, None,
                      dir_conflict_method="skip",
                      worker_mode=WorkerMode.PREVIEW).run()

        assert rows[0][1] == str(dest_zip)
        assert rows[0][3] == translate("warning_will_be_skipped")

    def test_zip_preview_empty_new_path_not_auto_filled(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        f = src_dir / "file.txt"
        f.write_text("data", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]

        tfo_ZipWorker(_FakeTool(rows), True, False, None,
                      worker_mode=WorkerMode.PREVIEW).run()

        # 新路径为空：Preview 不再自动填入/回写 New Path，只提示未设置并跳过
        assert rows[0][1] == ""
        assert rows[0][3] == translate("warning_new_path_not_set")
        assert not (src_dir / "src.zip").exists()

    def test_zip_apply_writes_new_path(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        f = src_dir / "file.txt"
        f.write_text("data", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]

        tfo_ZipWorker(_FakeTool(rows), True, False, None,
                      worker_mode=WorkerMode.APPLY).run()

        # 只有 Apply 写新路径列
        assert rows[0][1].endswith(".zip")

    def test_unzip_preview_keeps_user_new_path(self, tmp_path):
        import zipfile
        archive = tmp_path / "a.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            zf.writestr("a.txt", "A")
        dest = tmp_path / "custom_dest"
        rows = [{0: str(archive), 1: str(dest), 2: "", 3: ""}]

        tfo_UnZipWorker(_FakeTool(rows), False, "",
                        worker_mode=WorkerMode.PREVIEW).run()

        assert rows[0][1] == str(dest)
        assert rows[0][3] == translate("correct_will_be_extracted")
        assert not dest.exists()  # Preview 不解压

    def test_unzip_preview_empty_new_path_not_auto_filled(self, tmp_path):
        import zipfile
        archive = tmp_path / "a.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            zf.writestr("a.txt", "A")
        rows = [{0: str(archive), 1: "", 2: "", 3: ""}]

        tfo_UnZipWorker(_FakeTool(rows), False, "",
                        worker_mode=WorkerMode.PREVIEW).run()

        # 新路径为空：Preview 不再自动填入/回写 New Path，只提示未设置
        assert rows[0][1] == ""
        assert rows[0][3] == translate("warning_new_path_not_set")
        assert not (tmp_path / "a").exists()

    def test_unzip_apply_writes_new_path(self, tmp_path):
        import zipfile
        archive = tmp_path / "a.zip"
        with zipfile.ZipFile(str(archive), "w") as zf:
            zf.writestr("a.txt", "A")
        rows = [{0: str(archive), 1: "", 2: "", 3: ""}]

        tfo_UnZipWorker(_FakeTool(rows), False, "",
                        worker_mode=WorkerMode.APPLY).run()

        # 未指定目标路径：默认解压到压缩包旁边（新路径列为自动计算路径）
        assert rows[0][1] == str(tmp_path / "a")

    def test_rename_preview_keeps_nonempty_new_path(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        target = tmp_path / "b.txt"
        rows = [{0: str(f), 1: str(target), 2: "", 3: ""}]

        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=True,
                             worker_mode=WorkerMode.PREVIEW).run()

        # Preview 不改动已有非空新路径，仅把预测结果写入结果列
        assert rows[0][1] == str(target)
        assert rows[0][3] == translate("correct_will_be_renamed")


class TestApplyOnlyNewPath:
    """Apply（6.1）：只修改 New Path；New Path 变化的行清空 Result，未变化的行 Result 保持不变"""

    def test_move_apply_only_new_path_and_result_rule(self, tmp_path):
        source = tmp_path / "src"
        dest = tmp_path / "dst"
        source.mkdir()
        dest.mkdir()
        f1 = source / "a.txt"
        f2 = source / "b.txt"
        f1.write_text("A", encoding="utf-8")
        f2.write_text("B", encoding="utf-8")
        expected1 = str(dest / "a.txt")
        expected2 = str(dest / "b.txt")
        rows = [{0: str(f1), 1: "", 2: "", 3: "OLD-RESULT"},
                {0: str(f2), 1: expected2, 2: "", 3: "KEEP-RESULT"}]
        tool = _FakeTool(rows)
        tool.input_source_path03 = _FakeInput(str(source))
        tool.input_dest_path03 = _FakeInput(str(dest))

        tfo_RenameMoveWorker(tool, is_rename=False).apply_path()

        assert rows[0][1] == expected1
        assert rows[0][3] == ""              # New Path 变化 → 清空 Result
        assert rows[1][1] == expected2
        assert rows[1][3] == "KEEP-RESULT"   # New Path 未变化 → Result 保持

    def test_rename_apply_only_new_path_and_result_rule(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("A", encoding="utf-8")
        f2.write_text("B", encoding="utf-8")
        rows = [{0: str(f1), 1: "", 2: "", 3: "OLD-RESULT"},
                {0: str(f2), 1: str(f2), 2: "", 3: "KEEP-RESULT"}]

        # 默认 naming_method_mapping(0)=original_name：新文件名=旧文件名
        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=True).apply_naming()

        assert rows[0][1] == str(f1)
        assert rows[0][3] == ""              # New Path 从空变为 f1 → 清空 Result
        assert rows[1][1] == str(f2)
        assert rows[1][3] == "KEEP-RESULT"   # 未变化 → 保持


class _ListLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class TestExecuteLogging:
    """Execute 必须为每个非空旧路径/新路径的行记录 旧路径/新路径/匹配名（成功与失败都记录）"""

    @pytest.fixture
    def captured(self, monkeypatch):
        import tfo_utils.tfo_logger as tfo_logger
        handler = _ListLogHandler()
        logger = logging.getLogger("TFO_TEST_CAPTURE")
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        monkeypatch.setattr(tfo_logger, "_logger", logger)
        return handler.messages

    def test_success_is_logged(self, tmp_path, captured):
        src_f = tmp_path / "a.txt"
        src_f.write_text("A", encoding="utf-8")
        dst_f = tmp_path / "dst" / "a.txt"
        rows = [{0: str(src_f), 1: str(dst_f), 2: "MYMATCH", 3: ""}]

        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=False,
                             worker_mode=WorkerMode.EXECUTE).run()

        joined = "\n".join(captured)
        assert str(src_f) in joined
        assert str(dst_f) in joined
        assert "MYMATCH" in joined
        assert "成功" in joined

    def test_failure_is_logged_with_paths(self, tmp_path, captured):
        src_f = tmp_path / "a.txt"
        src_f.write_text("A", encoding="utf-8")
        blocker = tmp_path / "blocker"
        blocker.write_text("B", encoding="utf-8")   # 用文件当作目录，使移动失败
        dst_f = blocker / "x.txt"
        rows = [{0: str(src_f), 1: str(dst_f), 2: "FAILMATCH", 3: ""}]

        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=False,
                             worker_mode=WorkerMode.EXECUTE).run()

        joined = "\n".join(captured)
        assert str(src_f) in joined
        assert str(dst_f) in joined
        assert "FAILMATCH" in joined
        assert "失败" in joined


class TestResultColumnCleared:
    """Preview/Execute 前必须清空整个"执行结果"列"""

    def test_stale_results_cleared(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("A", encoding="utf-8")
        target = tmp_path / "b.txt"
        rows = [
            {0: str(f), 1: str(target), 2: "", 3: "上一次的结果"},
            {0: "", 1: "", 2: "", 3: "上一次的结果2"},
        ]

        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=False,
                             worker_mode=WorkerMode.PREVIEW).run()

        # 被处理的行写入新结果；未被处理的空行也必须被清空
        assert rows[0][3] != "上一次的结果"
        assert rows[1][3] == ""

    def test_zip_apply_only_clears_changed_rows(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("A", encoding="utf-8")
        rows = [
            {0: str(f), 1: "", 2: "", 3: "上一次的结果"},
            {0: "", 1: "", 2: "", 3: "上一次的结果2"},
        ]

        tfo_ZipWorker(_FakeTool(rows), True, False, None,
                      worker_mode=WorkerMode.APPLY).run()

        # Apply（6.1）：New Path 变化的行清空 Result；两列都空的行不变，Result 保持
        assert rows[0][3] == ""
        assert rows[1][3] == "上一次的结果2"


class TestAddNumber:
    """合并后的"添加编号"：位置（勾选 Before=文件名前，否则末尾）+ 分组（不分组/按父目录/按匹配名，单选）"""

    def _run(self, rows, start=False, scope="none"):
        tool = _FakeTool(rows)
        tool.combo_naming_method02 = _FakeCombo(11)
        tool.naming_method_mapping = {11: "add_number"}
        tool.check_number_pos_start02 = _FakeInput(start)
        tool.radio_number_scope_none02 = _FakeInput(scope == "none")
        tool.radio_number_scope_dir02 = _FakeInput(scope == "dir")
        tool.radio_number_scope_match02 = _FakeInput(scope == "match")
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()

    def test_position_end_default(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        self._run(rows)
        assert os.path.basename(rows[0][1]) == "a_01.txt"

    def test_position_start(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        self._run(rows, start=True)
        assert os.path.basename(rows[0][1]) == "01_a.txt"

    def test_scope_by_directory(self, tmp_path):
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        f1, f2, f3 = d1 / "a.txt", d1 / "b.txt", d2 / "c.txt"
        for p in (f1, f2, f3):
            p.write_text("x", encoding="utf-8")
        rows = [{0: str(p), 1: "", 2: "", 3: ""} for p in (f1, f2, f3)]
        self._run(rows, scope="dir")
        assert [os.path.basename(r[1]) for r in rows] == ["a_01.txt", "b_02.txt", "c_01.txt"]

    def test_idempotent_reapply(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        self._run(rows)
        self._run(rows)
        assert os.path.basename(rows[0][1]) == "a_01.txt"

    def test_suffix_mode_preserves_prefix_number(self, tmp_path):
        d = tmp_path / "00__Old"
        d.mkdir()
        rows = [{0: str(d), 1: "", 2: "", 3: ""}]
        self._run(rows, start=False, scope="dir")
        assert os.path.basename(rows[0][1]) == "00__Old_01"

    def test_suffix_mode_clears_suffix_keeps_prefix(self, tmp_path):
        d = tmp_path / "00__Old_55"
        d.mkdir()
        rows = [{0: str(d), 1: "", 2: "", 3: ""}]
        self._run(rows, start=False, scope="dir")
        assert os.path.basename(rows[0][1]) == "00__Old_01"

    def test_prefix_mode_clears_prefix_keeps_suffix(self, tmp_path):
        d = tmp_path / "00_Old_55"
        d.mkdir()
        rows = [{0: str(d), 1: "", 2: "", 3: ""}]
        self._run(rows, start=True, scope="dir")
        assert os.path.basename(rows[0][1]) == "01_Old_55"


class TestMergedNamingMethods:
    """合并后的重命名方式：替换(文本/位置)、前后缀(后缀/前缀)、大小写(四种)、正则替换"""

    def _tool(self, rows, idx, key, **overrides):
        tool = _FakeTool(rows)
        tool.combo_naming_method02 = _FakeCombo(idx)
        tool.naming_method_mapping = {idx: key}
        for k, v in overrides.items():
            setattr(tool, k, _FakeInput(v))
        return tool

    def test_replace_by_text(self, tmp_path):
        f = tmp_path / "hello_world.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 1, "replace", input_naming_oldtext="world", input_naming_text02="earth")
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "hello_earth.txt"

    def test_replace_by_position(self, tmp_path):
        f = tmp_path / "hello_world.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 1, "replace", radio_replace_mode_text02=False,
                          radio_replace_mode_position02=True, input_naming_position02="0",
                          input_length02="5", input_naming_text02="HI")
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "HI_world.txt"

    def test_add_affix_default_suffix(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 4, "add_affix", input_naming_text02="_SUF")
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "a_SUF.txt"

    def test_add_affix_prefix(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 4, "add_affix", radio_affix_mode_suffix02=False,
                          radio_affix_mode_prefix02=True, input_naming_text02="PRE_")
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "PRE_a.txt"

    def test_change_case_lower(self, tmp_path):
        f = tmp_path / "HelloWorld.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 5, "change_case", radio_case_mode_upper02=False,
                          radio_case_mode_lower02=True)
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "helloworld.txt"

    def test_change_case_capitalize(self, tmp_path):
        f = tmp_path / "hello_world.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 5, "change_case", radio_case_mode_upper02=False,
                          radio_case_mode_capitalize02=True)
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "Hello_world.txt"

    def test_regex_replace(self, tmp_path):
        f = tmp_path / "file_2024_01.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 6, "regex_replace",
                          input_naming_oldtext=r"(\d{4})_(\d{2})", input_naming_text02=r"\2-\1")
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        assert os.path.basename(rows[0][1]) == "file_01-2024.txt"

    def test_regex_invalid_shows_error(self, tmp_path, monkeypatch):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, 6, "regex_replace", input_naming_oldtext="(", input_naming_text02="x")
        monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: wx.OK)
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        # 无效正则不产生新路径
        assert rows[0][1] == ""


class TestMp3NamingFormat:
    """对MP3重命名：歌手-歌名（默认）/ 歌名-歌手 / 仅歌名"""

    def _tool(self, rows, title_first=False, title_only=False):
        tool = _FakeTool(rows)
        tool.combo_naming_method02 = _FakeCombo(9)
        tool.naming_method_mapping = {9: "rename_mp3"}
        tool.radio_mp3_artist_first02 = _FakeInput(not title_first and not title_only)
        tool.radio_mp3_title_first02 = _FakeInput(title_first)
        tool.radio_mp3_title_only02 = _FakeInput(title_only)
        return tool

    def _run(self, tmp_path, monkeypatch, title_first=False, title_only=False):
        import tfo_RenameMoveWorker as rmw_module
        monkeypatch.setattr(rmw_module, "HAS_MUTAGEN", True)
        monkeypatch.setattr(rmw_module.tfo_RenameMoveWorker, "_get_mp3_metadata",
                            lambda self, p: ("Artist", "Title"))
        f = tmp_path / "song.mp3"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = self._tool(rows, title_first=title_first, title_only=title_only)
        tfo_RenameMoveWorker(tool, is_rename=True).apply_naming()
        return os.path.basename(rows[0][1])

    def test_artist_first_default(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch) == "Artist - Title.mp3"

    def test_title_first(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch, title_first=True) == "Title - Artist.mp3"

    def test_title_only(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch, title_only=True) == "Title.mp3"


class TestPreviewExecuteFinalResultConsistency:
    """(5.1)(5.2)(5.3)：Preview/Execute 的最终结果列必须与实际动作一致，
    不得残留预览态的预测文案（如"将被跳过""新路径未设置"）。"""

    def test_preview_resnapshot_reads_latest_new_path(self, tmp_path):
        """Preview 启动时重新快照 Grid：用户在构造 worker 后 / start 前填写的新路径必须生效。"""
        src = tmp_path / "src"
        src.mkdir()
        f = src / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tool = _FakeTool(rows)
        worker = tfo_RenameMoveWorker(tool, is_rename=False, worker_mode=WorkerMode.PREVIEW)
        # 模拟构造 worker 之后、start 之前 Grid 被填写/编辑（本用例即"手动填写 New Path"）
        rows[0][1] = str(tmp_path / "dst" / "a.txt")
        worker.start()
        worker.join()
        assert rows[0][3] != translate("warning_new_path_not_set")
        assert rows[0][3] == translate("correct_will_be_moved")

    def test_execute_skip_writes_final_not_preview(self, tmp_path):
        """(5.2) Execute 下被冲突策略跳过的行，最终结果应为"已跳过"而非"将被跳过"。"""
        src = tmp_path / "src"
        src.mkdir()
        a = src / "a.txt"
        a.write_text("A", encoding="utf-8")
        b = src / "b.txt"
        b.write_text("B", encoding="utf-8")
        dst = tmp_path / "dst"
        dst.mkdir()
        target = dst / "x.txt"
        rows = [
            {0: str(a), 1: str(target), 2: "", 3: ""},
            {0: str(b), 1: str(target), 2: "", 3: ""},
        ]
        tool = _FakeTool(rows, file_conflict=0, dir_conflict=0)
        worker = tfo_RenameMoveWorker(tool, is_rename=False, worker_mode=WorkerMode.EXECUTE)
        worker.start()
        worker.join()
        assert target.exists()
        assert rows[1][3] == translate("warning_skipped")

    def test_zip_execute_skip_writes_final_not_preview(self, tmp_path):
        """(5.2) 压缩执行时目标 ZIP 已存在且策略为跳过，结果写"已跳过"而非"将被跳过"。"""
        import zipfile
        src = tmp_path / "src"
        src.mkdir()
        f = src / "file.txt"
        f.write_text("data", encoding="utf-8")
        dest_zip = tmp_path / "my.zip"
        with zipfile.ZipFile(str(dest_zip), "w") as zf:
            zf.writestr("src/other.txt", "x")
        rows = [{0: str(f), 1: str(dest_zip), 2: "", 3: ""}]

        tfo_ZipWorker(_FakeTool(rows), True, False, None,
                      dir_conflict_method="skip",
                      worker_mode=WorkerMode.EXECUTE).run()

        assert rows[0][3] == translate("warning_skipped")

    def test_copy_execute_skip_writes_final_not_preview(self, tmp_path):
        """(5.2) 复制执行时被冲突策略跳过的行，最终结果应为"已跳过"。"""
        src = tmp_path / "src"
        src.mkdir()
        a = src / "a.txt"
        a.write_text("A", encoding="utf-8")
        b = src / "b.txt"
        b.write_text("B", encoding="utf-8")
        dst = tmp_path / "dst"
        dst.mkdir()
        target = dst / "x.txt"
        rows = [
            {0: str(a), 1: str(target), 2: "", 3: ""},
            {0: str(b), 1: str(target), 2: "", 3: ""},
        ]
        tool = _FakeTool(rows, file_conflict=0, dir_conflict=0)
        worker = tfo_CopyWorker(tool, worker_mode=WorkerMode.EXECUTE)
        worker.start()
        worker.join()
        assert target.exists()
        assert rows[1][3] == translate("warning_skipped")

    def test_duplicate_execute_retain_writes_final_not_preview(self, tmp_path, monkeypatch):
        """(5.3) 去重执行模式下被保留的行，结果写"已保留"而非"[将保留]"。"""
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        f1 = d1 / "x.txt"
        f2 = d2 / "x.txt"
        f1.write_text("SAMEDATA", encoding="utf-8")
        f2.write_text("SAMEDATA", encoding="utf-8")
        _patch_recycle(monkeypatch, _duplicate_worker_module)

        rows = [{0: str(f1), 1: "", 2: "", 3: ""},
                {0: str(f2), 1: "", 2: "", 3: ""}]
        tfo_DuplicateWorker(_FakeTool(rows), "filename", "keep_create_time_latest",
                            worker_mode=WorkerMode.EXECUTE).run()

        results = [rows[0][3], rows[1][3]]
        assert translate("result_retained") in results
        assert translate("result_will_retain") not in results
        assert translate("result_will_delete") not in results

    def test_preview_new_path_empty_not_filled(self, tmp_path):
        """(6.2) Preview 不改 New Path；Old 非空/New 空的行写"新路径未设置"。"""
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: "OLD"}]
        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=False,
                             worker_mode=WorkerMode.PREVIEW).run()
        assert rows[0][1] == ""
        assert rows[0][3] == translate("warning_new_path_not_set")

    def test_execute_new_path_empty_skipped_not_filled(self, tmp_path):
        """(6.3) Execute 不自动 Apply；Old 非空/New 空的行写"新路径未设置"并跳过（不移动文件）。"""
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        rows = [{0: str(f), 1: "", 2: "", 3: ""}]
        tfo_RenameMoveWorker(_FakeTool(rows), is_rename=False,
                             worker_mode=WorkerMode.EXECUTE).run()
        assert rows[0][1] == ""
        assert rows[0][3] == translate("warning_new_path_not_set")
        assert f.exists()
