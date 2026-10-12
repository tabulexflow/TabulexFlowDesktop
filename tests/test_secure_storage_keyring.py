# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""L-2 加固：keyring 可用性检测（set/get/delete 真实写测试 + 失败状态落地）测试。

使用字典后端模拟真实 keyring（set 后 get 返回值一致），不依赖系统密钥环，验证：
1. 正常可写（set/get/delete 全通过） → _keyring_backend_ok == True
2. set 抛异常（后端初始化失败/不可写） → _keyring_backend_ok == False
3. set 成功但 get 值不一致（后端未真正持久化） → _keyring_backend_ok == False
4. get 抛异常 → _keyring_backend_ok == False
5. keyring 库不可用 → _keyring_backend_ok == False
6. 失败状态落地后 _keyring_usable() 立即返回 False（降级 Fernet）
"""
import pytest

from tfp_utils import tfp_secure_storage as ss


class _FakeKeyring:
    """字典后端：模拟真实 keyring 的 set/get/delete 语义。"""

    def __init__(self, set_raises=None, get_raises=None, broken_get=None):
        self._store = {}
        self.set_raises = set_raises
        self.get_raises = get_raises
        # broken_get=True -> 写入后 get 返回其他值（后端未真正持久化）
        self.broken_get = broken_get
        self.set_password_calls = 0
        self.delete_password_calls = 0

    def get_keyring(self):
        return self

    def set_password(self, service, user, value):
        self.set_password_calls += 1
        if self.set_raises is not None:
            raise self.set_raises
        self._store[(service, user)] = "stale-old-value" if self.broken_get else value

    def get_password(self, service, user):
        if self.get_raises is not None:
            raise self.get_raises
        return self._store.get((service, user))

    def delete_password(self, service, user):
        self.delete_password_calls += 1
        self._store.pop((service, user), None)


def test_keyring_writable_sets_ok_true(monkeypatch):
    fk = _FakeKeyring()
    monkeypatch.setattr(ss, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(ss, "keyring", fk)
    storage = ss.TFP_SecureStorage("TestSvc")
    assert storage._keyring_backend_ok is True
    # 应执行真实写测试 set → get → delete 三步
    assert fk.set_password_calls == 1
    assert fk.delete_password_calls == 1


def test_keyring_set_exception_sets_ok_false(monkeypatch):
    fk = _FakeKeyring(set_raises=RuntimeError("no default collection"))
    monkeypatch.setattr(ss, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(ss, "keyring", fk)
    storage = ss.TFP_SecureStorage("TestSvc")
    assert storage._keyring_backend_ok is False


def test_keyring_value_mismatch_sets_ok_false(monkeypatch):
    # set 成功但 get 返回旧值/其他值 → 后端未真正持久化 → fail-closed
    fk = _FakeKeyring(broken_get=True)
    monkeypatch.setattr(ss, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(ss, "keyring", fk)
    storage = ss.TFP_SecureStorage("TestSvc")
    assert storage._keyring_backend_ok is False


def test_keyring_get_exception_sets_ok_false(monkeypatch):
    fk = _FakeKeyring(get_raises=RuntimeError("dbus error"))
    monkeypatch.setattr(ss, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(ss, "keyring", fk)
    storage = ss.TFP_SecureStorage("TestSvc")
    assert storage._keyring_backend_ok is False


def test_keyring_lib_unavailable_sets_ok_false(monkeypatch):
    monkeypatch.setattr(ss, "KEYRING_AVAILABLE", False)
    storage = ss.TFP_SecureStorage("TestSvc")
    assert storage._keyring_backend_ok is False


def test_keyring_usable_returns_false_after_failure(monkeypatch):
    fk = _FakeKeyring(set_raises=RuntimeError("init failed"))
    monkeypatch.setattr(ss, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(ss, "keyring", fk)
    storage = ss.TFP_SecureStorage("TestSvc")
    # 失败状态落地后 _keyring_usable() 应立即返回 False（降级 Fernet），而非等首次 save()
    assert storage._keyring_usable() is False