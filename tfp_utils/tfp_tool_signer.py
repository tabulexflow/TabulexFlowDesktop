# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
子工具发布包 Ed25519 签名验证模块（H-3 加固 · 根/叶分层，2026-09-07）

后端对下载包（ZIP）的 "{checksum}:{version}" 载荷用「叶子私钥」签名，
签名值经响应头 X-Tool-Checksum-Sig 下发；「叶子公钥」由「根私钥」离线签发为
叶子凭证（经 X-Tool-Sign-Cred 响应头随下载下发）。本模块：
1. 用内置「根公钥」验证叶子凭证（verify_leaf_credential），得到叶子公钥；
2. 再用叶子公钥验证工具包签名（verify_tool_signature）；
3. 验签通过后才比对 ZIP 实际 SHA-256 并解压运行。

根公钥作为独立信任锚内置于打包产物中——攻击者可篡改 ZIP 与响应头，但无私钥
无法伪造签名；且攻击者无法伪造"根签发的叶子凭证"（根私钥离线保管，服务器无根私钥）。

根公钥配置：
- TOOL_SIGN_ROOT_PUBLIC_KEY_PEM 为空时视为未配置：
  - 源码开发模式（is_dev_mode()==True）：放行（本地开发，日志警告）
  - 其余场景（生产 / 本地测试构建）：fail-closed 拒绝执行未验证的工具包
- 部署步骤：运行后端 scripts/init_tool_signing_root.sh 一次性生成根密钥并
  自动替换本常量（根公钥），再运行 scripts/issue_tool_signing_leaf.sh 签发叶子
  凭证到后端；根公钥与凭证配对后前端方可下载子工具。
"""
import base64
import datetime
import json
import logging

logger = logging.getLogger(__name__)

# 后端工具发布签名「根公钥」（PEM 格式；由 init_tool_signing_root 脚本填写，空 = 未配置）
# ⚠️ 生产上线前：运行后端
#    scripts/init_tool_signing_root.sh / .bat 一次性生成根密钥并自动替换本常量，然后重新打包前端，
#    再运行 scripts/issue_tool_signing_leaf.sh 为后端签发叶子凭证，
#    否则生产环境工具包验签失败、无法下载。
TOOL_SIGN_ROOT_PUBLIC_KEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MCowBQYDK2VwAyEAMwZvsNiuiT7DowJS8YRXzKiQd/sQFFQnZ+OMVg0na4E=\n"
    "-----END PUBLIC KEY-----\n"
)


def is_public_key_configured() -> bool:
    """是否已内置根公钥（用于验证叶子凭证链）"""
    return bool(TOOL_SIGN_ROOT_PUBLIC_KEY_PEM and TOOL_SIGN_ROOT_PUBLIC_KEY_PEM.strip())


def get_signature_payload(checksum: str, version: str) -> str:
    """构造与后端一致的待验签载荷"""
    return f"{checksum}:{version}"


def _b64url_decode(s: str) -> bytes:
    """Base64URL 解码（自动补 '=' 填充）"""
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def _root_key_fingerprint_hex(root_pub) -> str:
    """根公钥指纹：SubjectPublicKeyInfo DER 的 SHA-256，hex"""
    import hashlib
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    der = root_pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def verify_leaf_credential(cred: str):
    """用内置根公钥验证叶子凭证，成功返回叶子公钥 PEM；任何失败返回 None（fail-closed）。

    校验顺序（与后端 be_utils.be_tool_signer.validate_leaf_credential 一致）：
    传输格式 → 根验签（对收到的 payload 原字节）→ schema → root_key_id 与内置根
    指纹一致 → not_after 未过期（±5 分钟容差）。
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        if not is_public_key_configured():
            return None
        parts = (cred or '').strip().split('.')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None
        payload = _b64url_decode(parts[0])
        signature = _b64url_decode(parts[1])
        if not payload or not signature:
            return None

        root_pub = load_pem_public_key(TOOL_SIGN_ROOT_PUBLIC_KEY_PEM.encode('utf-8'))
        if not isinstance(root_pub, Ed25519PublicKey):
            return None
        # 对收到的 payload 原字节验签（不重新序列化，避免两端 JSON 规范化不一致）
        root_pub.verify(signature, payload)

        doc = json.loads(payload.decode('utf-8'))
        if doc.get('schema') != 'tf-tool-sign-leaf-v1':
            return None
        if doc.get('root_key_id') and doc['root_key_id'] != _root_key_fingerprint_hex(root_pub):
            return None

        leaf_pem = doc.get('leaf_public_key_pem', '')
        if not leaf_pem:
            return None

        not_after = doc.get('not_after')
        if not_after:
            not_after_dt = datetime.datetime.fromisoformat(
                not_after.replace('Z', '+00:00'))
            now = datetime.datetime.now(datetime.timezone.utc)
            if now > not_after_dt + datetime.timedelta(minutes=5):
                return None

        return leaf_pem
    except Exception:
        return None


def verify_tool_signature(checksum: str, version: str, signature_b64: str,
                          public_key_pem: str = None) -> bool:
    """用给定公钥验证载荷签名。

    public_key_pem 为叶子公钥（由 verify_leaf_credential 返回）。缺省时回退到内置
    根公钥——仅用于过渡兼容；真实工具签名由叶子签发，用根公钥验签必然失败 → fail-closed。

    验签失败、格式异常或公钥未配置均返回 False（fail-closed）。
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        pem = (public_key_pem or '').strip() or TOOL_SIGN_ROOT_PUBLIC_KEY_PEM
        if not pem or not pem.strip():
            return False
        public_key = load_pem_public_key(pem.encode('utf-8'))
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(
            signature,
            get_signature_payload(checksum, version).encode('utf-8'),
        )
        return True
    except Exception:
        return False