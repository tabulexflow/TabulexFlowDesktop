# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TFP_SecureStorage Fernet 加解密专项测试

覆盖：随机密钥文件（0600 + 复用 + 跨目录随机性）、Fernet 加解密往返、密文不泄露明文、
keyring 不可用时的 Fallback 文件存储/读取/删除/存在性（fail-closed）。
"""
import os
import pytest

from tfp_utils.tfp_secure_storage import (
    TFP_SecureStorage,
    _read_fernet_key,
    _encrypt_with_fernet,
    _decrypt_with_fernet,
    _FERNET_KEY_FILE,
)


# ========== Fernet 随机密钥文件（H-1 加固替代可预测派生态） ==========

def test_fernet_key_file_created_and_reused(tmp_path):
    """首次加密创建密钥文件；同一目录后续复用同一密钥"""
    encrypted = _encrypt_with_fernet("data", tmp_path)
    assert encrypted is not None
    key_path = tmp_path / _FERNET_KEY_FILE
    assert key_path.exists()
    key1 = _read_fernet_key(tmp_path)
    key2 = _read_fernet_key(tmp_path)
    assert key1 == key2
    assert len(key1) > 0
    # 依赖密钥文件的往返解密成功（证明后续复用同一密钥）
    assert _decrypt_with_fernet(encrypted, tmp_path) == "data"


def test_fernet_key_file_permissions_0600(tmp_path):
    """密钥文件权限必须为 0600（创建即收紧，无"先写后 chmod"竞态）"""
    if os.name == "nt":
        pytest.skip("POSIX 权限检查不适用于 Windows")
    _encrypt_with_fernet("data", tmp_path)
    mode = (tmp_path / _FERNET_KEY_FILE).stat().st_mode & 0o777
    assert mode == 0o600


def test_fernet_key_random_not_machine_derived(tmp_path):
    """不同目录生成的密钥互不相同（随机，而非可由机器信息重建）"""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    _encrypt_with_fernet("x", dir_a)
    _encrypt_with_fernet("x", dir_b)
    assert _read_fernet_key(dir_a) != _read_fernet_key(dir_b)


def test_decrypt_missing_key_file_raises(tmp_path):
    """密钥文件缺失时解密直接抛错（fail-closed，不降级为明文）"""
    with pytest.raises(Exception):
        _decrypt_with_fernet("gAAAAAB_not_a_real_token", tmp_path)


# ========== Fernet 加解密 ==========

def test_encrypt_decrypt_roundtrip(tmp_path):
    plaintext = "secret-token-abc123"
    encrypted = _encrypt_with_fernet(plaintext, tmp_path)
    assert encrypted is not None
    assert _decrypt_with_fernet(encrypted, tmp_path) == plaintext


def test_encrypted_content_not_plaintext(tmp_path):
    plaintext = "secret-token-abc123"
    encrypted = _encrypt_with_fernet(plaintext, tmp_path)
    assert plaintext not in encrypted


def test_encrypt_different_data_different_ciphertext(tmp_path):
    a = _encrypt_with_fernet("data-1", tmp_path)
    b = _encrypt_with_fernet("data-1", tmp_path)
    # Fernet 是带随机 IV 的对称加密，同一明文两次加密结果不同
    assert a != b
    assert _decrypt_with_fernet(a, tmp_path) == _decrypt_with_fernet(b, tmp_path) == "data-1"


def test_decrypt_corrupted_fails(tmp_path):
    encrypted = _encrypt_with_fernet("data", tmp_path)
    corrupted = encrypted[:-4] + "AAAA"  # 篡改尾部
    with pytest.raises(Exception):
        _decrypt_with_fernet(corrupted, tmp_path)


# ========== Fallback 文件存储 ==========

@pytest.fixture()
def fallback_storage(tmp_path, monkeypatch):
    monkeypatch.setattr("tfp_utils.tfp_secure_storage.KEYRING_AVAILABLE", False)
    storage = TFP_SecureStorage("TestApp")
    # 重定向 Fallback 目录到临时目录，避免污染真实 config/
    storage._get_fallback_path = lambda: tmp_path
    return storage


def test_fallback_save_load_dict(fallback_storage):
    assert fallback_storage.save("auth_token", {"session_token": "st", "user": {"id": 1}}) is True
    data = fallback_storage.load("auth_token")
    assert data == {"session_token": "st", "user": {"id": 1}}


def test_fallback_save_load_string(fallback_storage):
    assert fallback_storage.save("plain", "hello") is True
    assert fallback_storage.load("plain") == "hello"


def test_fallback_file_is_encrypted(fallback_storage):
    secret = "secret-token-abc123"
    fallback_storage.save("tok", secret)
    files = list(fallback_storage._get_fallback_path().glob(".tok"))
    assert len(files) == 1
    raw = files[0].read_text(encoding="utf-8")
    assert secret not in raw  # 明文绝不落盘


def test_fallback_data_file_permissions_0600(fallback_storage):
    if os.name == "nt":
        pytest.skip("POSIX 权限检查不适用于 Windows")
    fallback_storage.save("tok", "secret")
    mode = (fallback_storage._get_fallback_path() / ".tok").stat().st_mode & 0o777
    assert mode == 0o600


def test_fallback_exists_delete(fallback_storage):
    assert fallback_storage.exists("k") is False
    fallback_storage.save("k", "v")
    assert fallback_storage.exists("k") is True
    assert fallback_storage.delete("k") is True
    assert fallback_storage.exists("k") is False
    # 删除不存在项返回 True
    assert fallback_storage.delete("k") is True


def test_fallback_load_nonexistent_returns_none(fallback_storage):
    assert fallback_storage.load("not_exist") is None


def test_fallback_corrupted_file_returns_none(fallback_storage):
    path = fallback_storage._get_fallback_path() / ".corrupt"
    path.write_text("not valid fernet data", encoding="utf-8")
    assert fallback_storage.load("corrupt") is None


def test_storage_info_reports_fallback(fallback_storage):
    info = fallback_storage.get_storage_info()
    assert info["keyring_available"] is False
    assert info["backend"] == "Fallback (Fernet加密)"


def test_fallback_json_invalid_returns_raw(fallback_storage):
    # 非 JSON 数据按原始字符串返回
    fallback_storage.save("raw", "just-a-string-not-json")
    assert fallback_storage.load("raw") == "just-a-string-not-json"