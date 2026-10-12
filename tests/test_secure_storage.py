# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 tfp_utils.tfp_secure_storage 模块"""
import pytest
import sys
import os

# 确保路径
_fe_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _fe_root not in sys.path:
    sys.path.insert(0, _fe_root)

from tfp_utils.tfp_secure_storage import TFP_SecureStorage, TFP_AuthTokenStorage


class TestTFSecureStorageInit:
    """测试 TFP_SecureStorage 初始化"""

    def test_default_service_name(self):
        storage = TFP_SecureStorage()
        assert storage.service_name == "TabulexFlow"

    def test_custom_service_name(self):
        storage = TFP_SecureStorage(service_name="CustomApp")
        assert storage.service_name == "CustomApp"

    def test_get_storage_info(self):
        storage = TFP_SecureStorage()
        info = storage.get_storage_info()
        assert isinstance(info, dict)
        assert 'service_name' in info
        assert 'keyring_available' in info
        assert 'backend' in info


class TestTFSecureStorageOperations:
    """测试 TFP_SecureStorage 基本操作"""

    @pytest.fixture
    def storage(self):
        return TFP_SecureStorage("TestSecureStorage")

    def test_save_and_load(self, storage):
        test_key = "test_save_load"
        test_data = {"name": "test", "value": 42}
        storage.save(test_key, test_data)
        loaded = storage.load(test_key)
        assert loaded == test_data
        storage.delete(test_key)

    def test_save_and_load_string(self, storage):
        test_key = "test_save_string"
        storage.save(test_key, "hello_world")
        loaded = storage.load(test_key)
        assert loaded == "hello_world"
        storage.delete(test_key)

    def test_exists(self, storage):
        test_key = "test_exists"
        assert storage.exists(test_key) is False
        storage.save(test_key, "data")
        assert storage.exists(test_key) is True
        storage.delete(test_key)

    def test_delete(self, storage):
        test_key = "test_delete"
        storage.save(test_key, "data")
        assert storage.exists(test_key) is True
        storage.delete(test_key)
        assert storage.exists(test_key) is False

    def test_delete_nonexistent(self, storage):
        result = storage.delete("nonexistent_key")
        assert result is True

    def test_load_nonexistent(self, storage):
        result = storage.load("nonexistent_key_12345")
        assert result is None

    def test_save_list(self, storage):
        test_key = "test_list"
        test_data = [1, 2, 3, "a", "b"]
        storage.save(test_key, test_data)
        loaded = storage.load(test_key)
        assert loaded == test_data
        storage.delete(test_key)


class TestTFAuthTokenStorage:
    """测试 TFP_AuthTokenStorage 专用类"""

    @pytest.fixture
    def auth_storage(self):
        return TFP_AuthTokenStorage()

    def test_save_and_load_session(self, auth_storage):
        session_data = {
            "session_token": "test_token_abc123",
            "refresh_token": "refresh_token_xyz",
            "user": {"id": 1, "username": "test_user"}
        }
        auth_storage.save_auth_session(session_data)
        loaded = auth_storage.load_auth_session()
        assert loaded == session_data
        auth_storage.clear_auth_session()

    def test_has_session(self, auth_storage):
        assert auth_storage.has_auth_session() is False
        auth_storage.save_auth_session({"token": "test"})
        assert auth_storage.has_auth_session() is True
        auth_storage.clear_auth_session()

    def test_clear_session(self, auth_storage):
        auth_storage.save_auth_session({"token": "test"})
        auth_storage.clear_auth_session()
        assert auth_storage.has_auth_session() is False