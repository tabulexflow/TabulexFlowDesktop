# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""tfp_utils/tfp_tool_signer 子工具发布包签名验证模块测试（H-3 · 根/叶分层）

覆盖 verify_leaf_credential（正路径 / 缺失 / 篡改 / 过期 / 非本根 / 根未配置）、
verify_tool_signature（显式叶子公钥验签 / 错误公钥 / 缺省回退根公钥 / 畸形签名）、
is_public_key_configured。
"""
import base64
import hashlib
import json
from contextlib import contextmanager

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import tfp_utils.tfp_tool_signer as tt_signer


def _b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _pub_pem(pub):
    return pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode('utf-8')


def _fingerprint(pub):
    der = pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def _make_cred(root_priv, leaf_pub, not_after='2027-09-07T00:00:00Z'):
    """构造与后端签发脚本一致的叶子凭证传输串（sort_keys 定序 JSON）"""
    doc = {
        'schema': 'tf-tool-sign-leaf-v1',
        'root_key_id': _fingerprint(root_priv.public_key()),
        'leaf_key_id': _fingerprint(leaf_pub),
        'leaf_public_key_pem': _pub_pem(leaf_pub),
        'issued_at': '2026-09-07T00:00:00Z',
        'not_after': not_after,
    }
    payload = json.dumps(doc, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False).encode('utf-8')
    sig = root_priv.sign(payload)
    return _b64u(payload) + '.' + _b64u(sig)


# 测试密钥对（内存生成，避免依赖真实密钥文件）
ROOT = Ed25519PrivateKey.generate()
LEAF = Ed25519PrivateKey.generate()
OTHER_ROOT = Ed25519PrivateKey.generate()


@contextmanager
def _root(pub):
    """临时设置模块内置根公钥（不依赖 monkeypatch，便于无 pytest 环境直接驱动）"""
    old = tt_signer.TOOL_SIGN_ROOT_PUBLIC_KEY_PEM
    tt_signer.TOOL_SIGN_ROOT_PUBLIC_KEY_PEM = pub
    try:
        yield
    finally:
        tt_signer.TOOL_SIGN_ROOT_PUBLIC_KEY_PEM = old


class TestLeafCredential:

    def test_positive_roundtrip(self):
        with _root(_pub_pem(ROOT.public_key())):
            leaf_pem = tt_signer.verify_leaf_credential(
                _make_cred(ROOT, LEAF.public_key()))
            assert leaf_pem == _pub_pem(LEAF.public_key())

    def test_missing_or_malformed(self):
        with _root(_pub_pem(ROOT.public_key())):
            assert tt_signer.verify_leaf_credential('') is None
            assert tt_signer.verify_leaf_credential(None) is None
            assert tt_signer.verify_leaf_credential('a.b.c') is None
            assert tt_signer.verify_leaf_credential('not-a-cred') is None

    def test_tampered_leaf_rejected(self):
        with _root(_pub_pem(ROOT.public_key())):
            cred = _make_cred(ROOT, LEAF.public_key())
            payload_b64, sig_b64 = cred.split('.')
            payload = base64.urlsafe_b64decode(
                payload_b64 + '=' * (-len(payload_b64) % 4))
            doc = json.loads(payload.decode('utf-8'))
            doc['leaf_public_key_pem'] = _pub_pem(ROOT.public_key())
            tampered = _b64u(json.dumps(doc, sort_keys=True, separators=(',', ':'),
                                        ensure_ascii=False).encode('utf-8')) + '.' + sig_b64
            assert tt_signer.verify_leaf_credential(tampered) is None

    def test_tampered_sig_rejected(self):
        with _root(_pub_pem(ROOT.public_key())):
            cred = _make_cred(ROOT, LEAF.public_key())
            payload_b64, sig_b64 = cred.split('.')
            sig = base64.urlsafe_b64decode(
                sig_b64 + '=' * (-len(sig_b64) % 4))
            # 翻转最后一字节（异或 0x01，保证与原签名不同）
            bad_sig = _b64u(sig[:-1] + bytes([sig[-1] ^ 0x01]))
            assert tt_signer.verify_leaf_credential(payload_b64 + '.' + bad_sig) is None

    def test_expired_rejected(self):
        with _root(_pub_pem(ROOT.public_key())):
            cred = _make_cred(ROOT, LEAF.public_key(), not_after='2020-01-01T00:00:00Z')
            assert tt_signer.verify_leaf_credential(cred) is None

    def test_wrong_root_rejected(self):
        # 凭证由 OTHER_ROOT 签发，前端内置根为 ROOT → 拒绝
        with _root(_pub_pem(ROOT.public_key())):
            cred = _make_cred(OTHER_ROOT, LEAF.public_key())
            assert tt_signer.verify_leaf_credential(cred) is None

    def test_root_not_configured(self):
        with _root(''):
            assert tt_signer.is_public_key_configured() is False
            cred = _make_cred(ROOT, LEAF.public_key())
            assert tt_signer.verify_leaf_credential(cred) is None


class TestVerifyToolSignature:

    def test_verify_with_leaf_ok(self):
        sig = base64.b64encode(LEAF.sign(b'abc:1.0')).decode('ascii')
        assert tt_signer.verify_tool_signature('abc', '1.0', sig, _pub_pem(LEAF.public_key())) is True

    def test_verify_with_wrong_key_rejected(self):
        sig = base64.b64encode(LEAF.sign(b'abc:1.0')).decode('ascii')
        assert tt_signer.verify_tool_signature('abc', '1.0', sig, _pub_pem(OTHER_ROOT.public_key())) is False

    def test_verify_malformed_rejected(self):
        assert tt_signer.verify_tool_signature('abc', '1.0', 'not-base64!!', _pub_pem(LEAF.public_key())) is False

    def test_verify_default_fallback_root(self):
        # 缺省 public_key_pem 回退内置根公钥（过渡兼容）：根公钥签名可通过
        with _root(_pub_pem(ROOT.public_key())):
            sig = base64.b64encode(ROOT.sign(b'abc:1.0')).decode('ascii')
            assert tt_signer.verify_tool_signature('abc', '1.0', sig) is True

    def test_verify_no_key_configured_rejected(self):
        # 根未配置且未显式传验签公钥 → 无法验签（fail-closed）
        with _root(''):
            sig = base64.b64encode(ROOT.sign(b'abc:1.0')).decode('ascii')
            assert tt_signer.verify_tool_signature('abc', '1.0', sig) is False

    def test_signature_payload_format(self):
        assert tt_signer.get_signature_payload('abc', '1.0') == 'abc:1.0'