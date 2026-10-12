# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

# 数据层 user_type 三值（用于权限比较/身份判断）
USER_TYPE_HIERARCHY = {
    "individual": 0,
    "enterprise": 1,
    "platform": 2,
}

USER_TYPE_VALUES = ("individual", "enterprise", "platform")

USER_TYPE_LABELS = {
    "individual": "Individual",
    "enterprise": "Enterprise",
    "platform": "Platform",
}

USER_TYPE_LABELS_ZH = {
    "individual": "个人",
    "enterprise": "企业",
    "platform": "平台管理员",
}

# UI 派生显示等级（5 级，含企业二级）
DISPLAY_TIER_VALUES = ("free", "premium", "enterprise", "enterprise_admin", "platform")

DISPLAY_TIER_LABELS = {
    "free": "Free",
    "premium": "Premium",
    "enterprise": "Enterprise",
    "enterprise_admin": "Enterprise-Admin",
    "platform": "Platform",
}

DISPLAY_TIER_LABELS_ZH = {
    "free": "免费",
    "premium": "高级",
    "enterprise": "企业",
    "enterprise_admin": "企业管理员",
    "platform": "平台管理员",
}

DISPLAY_TIER_COLORS = {
    "free": "gray",
    "premium": "gold",
    "enterprise": "blue",
    "enterprise_admin": "blue",
    "platform": "red",
}

# ============================================================================
# 新增：工具集 / 工具订购相关常量
# ============================================================================

# 平台默认工具集 ID
TOOLKIT_TFP_CORE = "TFP_CORE"

# subscription_type 取值
SUBSCRIPTION_TYPE_SINGLE_TOOL = "single_tool"
SUBSCRIPTION_TYPE_TOOLKIT = "toolkit"
SUBSCRIPTION_TYPE_ENTERPRISE = "enterprise"
SUBSCRIPTION_TYPE_THIRD_PARTY = "third_party"

# subscriber_type 取值
SUBSCRIBER_TYPE_USER = "user"
SUBSCRIBER_TYPE_COMPANY = "company"
SUBSCRIBER_TYPE_SYSTEM = "system"

# source 取值
SUBSCRIPTION_SOURCE_PURCHASE = "purchase"
SUBSCRIPTION_SOURCE_BONUS_FROM_ENTERPRISE = "bonus_from_enterprise"
SUBSCRIPTION_SOURCE_MANUAL_GRANT = "manual_grant"

# 旧字段值兼容映射（反序列化时归一化历史值）
_LEGACY_USER_TYPE_MAP = {
    "free": "individual",
    "premium": "individual",
    "admin": "platform",
}


def normalize_user_type(user_type: str) -> str:
    """将旧版 user_type 字段值规范化为新版三值

    新版三值：individual/enterprise/platform
    旧版值会被映射：
        free/premium → individual
        admin → platform
    """
    if not user_type:
        return "individual"
    if user_type in USER_TYPE_HIERARCHY:
        return user_type
    return _LEGACY_USER_TYPE_MAP.get(user_type, "individual")
