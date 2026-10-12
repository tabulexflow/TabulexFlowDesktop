# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import os
import json
import base64
import secrets
import logging
from typing import Optional, Any, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import keyring
    from keyring.errors import PasswordDeleteError, KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger.warning("keyring library not installed, using fallback scheme (not recommended for production)")

try:
    from cryptography.fernet import Fernet
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.warning("cryptography library not installed, Fernet encryption fallback unavailable")

# Windows DPAPI 可用性检测
_DPAPI_AVAILABLE = False
if sys.platform == 'win32':
    try:
        import ctypes
        import ctypes.wintypes
        _DPAPI_AVAILABLE = True
    except ImportError:
        pass

# v6.x 安全加固（H-1，2026-08-31）：
# Fernet 回退密钥不再由可预测的机器信息（hostname/machine/username）派生，
# 改为**首次生成 32 字节随机密钥**存于 0600 密钥文件（.tfp_fernet_key，与数据文件同目录）。
_FERNET_KEY_FILE = ".tfp_fernet_key"

# DPAPI 数据标记前缀，用于区分 DPAPI 加密数据和 Fernet 加密数据
_DPAPI_PREFIX = "DPAPI:"


def _dpapi_encrypt(data: str) -> Optional[str]:
    """使用 Windows DPAPI (CryptProtectData) 加密数据

    返回 DPAPI: + base64 编码的加密数据，失败返回 None。
    DPAPI 使用当前 Windows 用户 profile 的主密钥加密，无需应用提供口令/盐。
    安全边界：同一 Windows 用户 profile。
    """
    if not _DPAPI_AVAILABLE:
        return None
    try:
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ('cbData', ctypes.wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_ubyte)),
            ]

        plaintext_bytes = data.encode('utf-8')
        input_blob = DATA_BLOB()
        input_blob.cbData = len(plaintext_bytes)
        input_blob.pbData = (ctypes.c_ubyte * len(plaintext_bytes))(*plaintext_bytes)

        output_blob = DATA_BLOB()

        # CryptProtectData(hwnd=0, pPromptStruct=None, pData=&input, pOptionalEntropy=None,
        #                   pvReserved=None, pPromptStruct=None, pDataOut=&output)
        if ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            None,  # pwszDataTitle
            None,  # pOptionalEntropy
            None,  # pvReserved
            None,  # pPromptStruct
            0,     # dwFlags (0 = 仅当前用户可解密（默认）; CRYPTPROTECT_LOCAL_MACHINE=0x04 才为机器级; CRYPTPROTECT_UI_FORBIDDEN=0x01 禁止 UI 提示)
            ctypes.byref(output_blob),
        ):
            encrypted_bytes = (ctypes.c_ubyte * output_blob.cbData)()
            ctypes.memmove(encrypted_bytes, output_blob.pbData, output_blob.cbData)
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)
            return _DPAPI_PREFIX + base64.b64encode(bytes(encrypted_bytes)).decode('ascii')
        else:
            logger.debug("DPAPI CryptProtectData failed; falling back to Fernet")
            return None
    except Exception as e:
        logger.debug(f"DPAPI encryption error, falling back to Fernet: {e}")
        return None


def _dpapi_decrypt(encrypted: str) -> Optional[str]:
    """使用 Windows DPAPI (CryptUnprotectData) 解密数据

    输入须为 DPAPI: + base64 编码的加密数据，解密失败返回 None。
    """
    if not _DPAPI_AVAILABLE:
        return None
    if not encrypted.startswith(_DPAPI_PREFIX):
        return None
    try:
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ('cbData', ctypes.wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_ubyte)),
            ]

        encrypted_bytes = base64.b64decode(encrypted[len(_DPAPI_PREFIX):])
        input_blob = DATA_BLOB()
        input_blob.cbData = len(encrypted_bytes)
        input_blob.pbData = (ctypes.c_ubyte * len(encrypted_bytes))(*encrypted_bytes)

        output_blob = DATA_BLOB()

        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,  # ppszDataDescr
            None,  # pOptionalEntropy
            None,  # pvReserved
            None,  # pPromptStruct
            0,     # dwFlags
            ctypes.byref(output_blob),
        ):
            decrypted_bytes = (ctypes.c_ubyte * output_blob.cbData)()
            ctypes.memmove(decrypted_bytes, output_blob.pbData, output_blob.cbData)
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)
            return bytes(decrypted_bytes).decode('utf-8')
        else:
            logger.debug("DPAPI CryptUnprotectData failed")
            return None
    except Exception as e:
        logger.debug(f"DPAPI decryption error: {e}")
        return None


def _fernet_key_path(base_dir: Path) -> Path:
    """Fernet 密钥文件路径（与回退数据文件同目录）"""
    return base_dir / _FERNET_KEY_FILE


def _read_fernet_key(base_dir: Path) -> Optional[bytes]:
    """读取随机 Fernet 密钥（返回 urlsafe base64 的 32 字节密钥）。缺失或损坏返回 None。"""
    key_path = _fernet_key_path(base_dir)
    if not key_path.exists():
        return None
    try:
        key_b64 = key_path.read_text(encoding='utf-8').strip()
        key = base64.urlsafe_b64decode(key_b64)
        if len(key) != 32:
            logger.error(f"Fernet key file has invalid length: {key_path}")
            return None
        # 返回规范化后的 urlsafe base64 字节（Fernet 期望格式）
        return base64.urlsafe_b64encode(key)
    except Exception as e:
        logger.error(f"Fernet key file corrupted: {key_path} ({e})")
        return None


def _create_fernet_key(base_dir: Path) -> Optional[bytes]:
    """首次生成 32 字节随机密钥并写入 0600 密钥文件。

    os.open 带 0o600 模式创建（创建即收紧，消除"先写后 chmod"竞态）+
    fsync 落盘 + chmod 强化既有文件权限。任何一步失败返回 None（fail-closed）。
    """
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        key_b64 = base64.urlsafe_b64encode(key).decode('ascii')
        key_path = _fernet_key_path(base_dir)
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(key_b64)
            f.flush()
            os.fsync(f.fileno())
        # 强化既有文件权限（新文件创建即 0600，无权限放宽窗口）
        os.chmod(str(key_path), 0o600)
        return base64.urlsafe_b64encode(key)
    except Exception as e:
        logger.error(f"Failed to create Fernet key file: {base_dir} ({e})")
        return None


def _load_or_create_fernet_key(base_dir: Path) -> Optional[bytes]:
    """读取密钥；不存在则首次创建。读取/创建均失败时返回 None。"""
    key = _read_fernet_key(base_dir)
    if key is not None:
        return key
    return _create_fernet_key(base_dir)


def _encrypt_with_fernet(data: str, base_dir: Path) -> Optional[str]:
    """Fernet 加密（密钥来自随机密钥文件）。密钥不可用（无法读取/创建）返回 None。"""
    key = _load_or_create_fernet_key(base_dir)
    if key is None:
        return None
    f = Fernet(key)
    encrypted = f.encrypt(data.encode('utf-8'))
    return encrypted.decode('ascii')


def _decrypt_with_fernet(encrypted: str, base_dir: Path) -> str:
    """Fernet 解密（密钥来自随机密钥文件）。密钥文件缺失/损坏抛 ValueError；数据损坏抛 Fernet 异常。"""
    key = _read_fernet_key(base_dir)
    if key is None:
        raise ValueError("Fernet key file is missing or corrupted")
    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode('ascii'))
    return decrypted.decode('utf-8')


def _write_file_0600(file_path: Path, content: str) -> bool:
    """以 0600 权限写入文件：os.open 带模式创建（无"先写后 chmod"竞态）+ fsync + 强化 chmod。"""
    try:
        fd = os.open(str(file_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # 强化既有文件权限（新文件创建即 0600，无权限放宽窗口）
        os.chmod(str(file_path), 0o600)
        return True
    except Exception as e:
        logger.error(f"Failed to write file: {file_path}: {e}")
        return False


def _set_file_permissions_readonly(file_path: Path):
    try:
        if sys.platform == 'win32':
            import subprocess
            username = os.environ.get('USERNAME', '')
            if username:
                subprocess.run(
                    ['icacls', str(file_path), '/inheritance:r', '/grant', f'{username}:R'],
                    capture_output=True, timeout=5
                )
        else:
            os.chmod(file_path, 0o600)
    except Exception:
        logger.warning("Failed to set key file permissions; the file may be too permissive")


class TFP_SecureStorage:
    
    def __init__(self, service_name: str = "TabulexFlow"):
        self.service_name = service_name
        # keyring 后端运行时是否可用：None=未知，True=可用，False=已失败(回退Fernet文件)
        self._keyring_backend_ok: Optional[bool] = None
        self._check_keyring_availability()
        
        if not KEYRING_AVAILABLE:
            logger.error(
                "⚠️  Warning: keyring library is unavailable!\n"
                "   Falling back to encrypted file storage (DPAPI / Fernet+0600 随机密钥文件).\n"
                "   Please run: pip install keyring  (推荐，使用系统密钥环)"
            )
    
    def _keyring_usable(self) -> bool:
        """判断 keyring 后端是否可用（含运行时失败后的降级状态）。"""
        if not KEYRING_AVAILABLE:
            return False
        if self._keyring_backend_ok is False:
            return False
        return True
    
    def _check_keyring_availability(self):
        """keyring 可用性检测：set/get/delete 三步真实写测试，并将结果落地到 _keyring_backend_ok。

        早期实现仅 get_password（只读探测）且异常路径未置 False，导致后端不可写时
        _keyring_usable() 仍返回 True。现改为真实写测试，任何一步失败都 fail-closed
        置 _keyring_backend_ok = False（L-2，2026-09-01）。
        """
        if not KEYRING_AVAILABLE:
            self._keyring_backend_ok = False
            return False

        test_user = "__tfp_keyring_test__"
        test_value = secrets.token_hex(8)
        try:
            backend = keyring.get_keyring()
            logger.debug(f"Key storage backend: {backend.__class__.__name__}")

            # 真实写测试：set → get 校验一致 → delete 清理（验证后端可写、可读、可删）
            keyring.set_password(self.service_name, test_user, test_value)
            stored = keyring.get_password(self.service_name, test_user)
            if stored != test_value:
                logger.error("keyring write test failed: stored value mismatch")
                self._keyring_backend_ok = False
                return False
            try:
                keyring.delete_password(self.service_name, test_user)
            except Exception:
                logger.warning("keyring cleanup failed (test key left behind)")

            self._keyring_backend_ok = True
            return True

        except Exception as e:
            self._keyring_backend_ok = False
            logger.error(f"❌ keyring initialization failed: {e}")
            try:
                keyring.delete_password(self.service_name, test_user)
            except Exception:
                pass
            return False
    
    def save(self, key: str, data: Any) -> bool:
        try:
            if isinstance(data, (dict, list)):
                data_str = json.dumps(data, ensure_ascii=False)
            else:
                data_str = str(data)
            
            if self._keyring_usable():
                try:
                    keyring.set_password(self.service_name, key, data_str)
                    logger.debug(f"✅ Data securely stored: {key}")
                    return True
                except Exception as e:
                    # keyring 后端运行时故障（如 Linux Secret Service 无默认collection、
                    # 创建被取消等），回退到 Fernet 文件存储
                    logger.warning(f"keyring backend error, falling back to Fernet file storage [{key}]: {e}")
                    self._keyring_backend_ok = False
            return self._save_fallback(key, data_str)
                
        except Exception as e:
            logger.error(f"❌ Failed to save data [{key}]: {e}", exc_info=True)
            return False
    
    def load(self, key: str) -> Optional[Any]:
        try:
            if self._keyring_usable():
                try:
                    data_str = keyring.get_password(self.service_name, key)
                except Exception as e:
                    logger.warning(f"keyring backend error, falling back to Fernet file storage [{key}]: {e}")
                    self._keyring_backend_ok = False
                    return self._load_fallback(key)
                
                if data_str is None:
                    logger.debug(f"Data not found: {key}")
                    return None
                
                try:
                    return json.loads(data_str)
                except json.JSONDecodeError:
                    return data_str
                    
            else:
                return self._load_fallback(key)
                
        except Exception as e:
            logger.error(f"❌ Failed to read data [{key}]: {e}", exc_info=True)
            return None
    
    def delete(self, key: str) -> bool:
        try:
            if self._keyring_usable():
                try:
                    keyring.delete_password(self.service_name, key)
                    logger.debug(f"✅ Data deleted: {key}")
                    return True
                except PasswordDeleteError:
                    logger.debug(f"Data does not exist, nothing to delete: {key}")
                    return True
                except Exception as e:
                    logger.warning(f"keyring backend error, falling back to Fernet file storage [{key}]: {e}")
                    self._keyring_backend_ok = False
            return self._delete_fallback(key)
                
        except Exception as e:
            logger.error(f"❌ Failed to delete data [{key}]: {e}", exc_info=True)
            return False
    
    def exists(self, key: str) -> bool:
        try:
            if self._keyring_usable():
                try:
                    data = keyring.get_password(self.service_name, key)
                    return data is not None
                except Exception as e:
                    logger.warning(f"keyring backend error, falling back to Fernet file storage [{key}]: {e}")
                    self._keyring_backend_ok = False
            return self._exists_fallback(key)
        except Exception as e:
            logger.error(f"❌ Failed to check data existence [{key}]: {e}")
            return False
    
    def _get_fallback_path(self) -> Path:
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent / "config"
        else:
            base_dir = Path(__file__).parent.parent / "config"
        
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir
    
    def _save_fallback(self, key: str, data_str: str) -> bool:
        try:
            config_dir = self._get_fallback_path()
            file_path = config_dir / f".{key}"

            # Windows 上优先使用 DPAPI 加密（安全性优于 Fernet 文件密钥）
            if _DPAPI_AVAILABLE:
                encrypted = _dpapi_encrypt(data_str)
                if encrypted is not None:
                    if not _write_file_0600(file_path, encrypted):
                        return False
                    _set_file_permissions_readonly(file_path)
                    logger.warning(f"[Fallback] DPAPI-encrypted stored to: {file_path}")
                    return True
                else:
                    logger.debug("DPAPI encryption failed; falling back to Fernet")

            # DPAPI 不可用或加密失败时，回退到 Fernet（Linux/macOS 或 DPAPI 异常）
            if not CRYPTOGRAPHY_AVAILABLE:
                logger.error("cryptography library unavailable, cannot use Fernet encryption fallback")
                return False

            encrypted = _encrypt_with_fernet(data_str, config_dir)
            if encrypted is None:
                # fail-closed：随机密钥文件无法读取/创建时不落盘任何明文
                logger.error("Fernet fallback encryption failed (key file unreadable/uncreatable); refusing to store plaintext")
                return False
            if not _write_file_0600(file_path, encrypted):
                return False

            logger.warning(f"[Fallback] Fernet-encrypted stored to: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Fallback save failed: {e}")
            return False

    def _load_fallback(self, key: str) -> Optional[Any]:
        try:
            config_dir = self._get_fallback_path()
            file_path = config_dir / f".{key}"

            if not file_path.exists():
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()

            # 优先尝试 DPAPI 解密（新数据）
            if raw.startswith(_DPAPI_PREFIX):
                data_str = _dpapi_decrypt(raw)
                if data_str is not None:
                    try:
                        return json.loads(data_str)
                    except json.JSONDecodeError:
                        return data_str
                # DPAPI 解密失败（如用户 profile 变更），尝试 Fernet 解密
                logger.warning("DPAPI decryption failed; data may be encrypted by old Fernet, but format does not match")
                return None

            # Fernet 解密（旧数据兼容；H-1 加固后旧"机器特征派生"密文无法用随机密钥解密 → 返回 None，用户重新登录）
            try:
                data_str = _decrypt_with_fernet(raw, config_dir)
            except Exception:
                logger.error(f"Fallback file decryption failed [{key}]")
                return None

            try:
                return json.loads(data_str)
            except json.JSONDecodeError:
                return data_str

        except Exception as e:
            logger.error(f"Fallback read failed: {e}")
            return None
    
    def _delete_fallback(self, key: str) -> bool:
        try:
            config_dir = self._get_fallback_path()
            file_path = config_dir / f".{key}"
            
            if file_path.exists():
                file_path.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"Fallback delete failed: {e}")
            return False
    
    def _exists_fallback(self, key: str) -> bool:
        try:
            config_dir = self._get_fallback_path()
            file_path = config_dir / f".{key}"
            return file_path.exists()
        except Exception as e:
            logger.error(f"Fallback check failed: {e}")
            return False
    
    def get_storage_info(self) -> Dict[str, Any]:
        info = {
            'service_name': self.service_name,
            'keyring_available': KEYRING_AVAILABLE,
        }
        
        if KEYRING_AVAILABLE:
            try:
                backend = keyring.get_keyring()
                info['backend'] = backend.__class__.__name__
                info['backend_description'] = getattr(backend, '__doc__', '').split('\n')[0] if backend.__doc__ else 'Unknown'
            except Exception:
                info['backend'] = 'Unknown'
                info['backend_description'] = 'Failed to detect'
        else:
            if _DPAPI_AVAILABLE:
                info['backend'] = 'Fallback (DPAPI加密优先，Fernet兜底)'
                info['backend_description'] = 'Windows DPAPI (CryptProtectData) with Fernet fallback'
            else:
                info['backend'] = 'Fallback (Fernet加密)'
                info['backend_description'] = 'Using Fernet encrypted file storage'
        
        return info


class TFP_AuthTokenStorage(TFP_SecureStorage):
    
    TOKEN_KEY = "auth_token"
    
    def __init__(self):
        super().__init__("TabulexFlow_Auth")
    
    def save_auth_session(self, session_data: Dict[str, Any]) -> bool:
        return self.save(self.TOKEN_KEY, session_data)
    
    def load_auth_session(self) -> Optional[Dict[str, Any]]:
        data = self.load(self.TOKEN_KEY)
        return data
    
    def clear_auth_session(self) -> bool:
        return self.delete(self.TOKEN_KEY)
    
    def has_auth_session(self) -> bool:
        return self.exists(self.TOKEN_KEY)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 70)
    print("🔐 SecureStorage Functional Test")
    print("=" * 70)
    
    storage = TFP_SecureStorage("TestApp")
    
    print("\n📋 Storage Info:")
    info = storage.get_storage_info()
    for k, v in info.items():
        print(f"  {k}: {v}")
    
    print("\n📝 Test 1: Storing Data...")
    test_data = {
        "session_token": "test_token_43210",
        "refresh_token": "refresh_test_98765",
        "user_id": 42,
        "username": "test_user",
        "timestamp": "2026-04-16T15:30:00"
    }
    
    success = storage.save("test_data", test_data)
    print(f"  Store Result: {'✅ Success' if success else '❌ Failed'}")
    
    print("\n📖 Test 2: Reading Data...")
    loaded_data = storage.load("test_data")
    if loaded_data:
        print(f"  ✅ Read success:")
        for k, v in loaded_data.items():
            if 'token' in k.lower():
                print(f"    {k}: ***{v[-8:]}")
            else:
                print(f"    {k}: {v}")
    else:
        print(f"  ❌ Read failed")
    
    print("\n🔍 Test 3: Checking Data Existence...")
    exists = storage.exists("test_data")
    print(f"  Data exists: {'✅ Yes' if exists else '❌ No'}")
    
    not_exists = storage.exists("nonexistent_key")
    print(f"  Nonexistent data: {'✅ Yes' if not_exists else '❌ Should be No'}")
    
    print("\n🗑️  Test 4: Deleting Data...")
    delete_success = storage.delete("test_data")
    print(f"  Delete Result: {'✅ Success' if delete_success else '❌ Failed'}")
    
    exists_after_delete = storage.exists("test_data")
    print(f"  Existence after delete: {'❌ Still exists' if exists_after_delete else '✅ Cleared'}")
    
    print("\n🎫 Test 5: AuthTokenStorage Dedicated Class...")
    auth_storage = TFP_AuthTokenStorage()
    
    auth_data = {
        "session_token": "auth_test_token_xyz",
        "refresh_token": "auth_refresh_abc",
        "user": {
            "id": 100,
            "username": "sample_user",
            "user_type": "premium"
        }
    }
    
    save_ok = auth_storage.save_auth_session(auth_data)
    print(f"  Save Session: {'✅ Success' if save_ok else '❌ Failed'}")
    
    loaded_auth = auth_storage.load_auth_session()
    if loaded_auth:
        print(f"  Load Session: ✅ Success")
        print(f"    User Type: {loaded_auth.get('user', {}).get('user_type')}")
    
    has_session = auth_storage.has_auth_session()
    print(f"  Session exists: {'✅ Yes' if has_session else '❌ No'}")
    
    clear_ok = auth_storage.clear_auth_session()
    print(f"  Clear Session: {'✅ Success' if clear_ok else '❌ Failed'}")
    
    has_session_after_clear = auth_storage.has_auth_session()
    print(f"  Existence after clear: {'❌ Still exists' if has_session_after_clear else '✅ Cleared'}")
    
    print("\n" + "=" * 70)
    print("✅ All tests completed!")
    print("=" * 70 + "\n")
