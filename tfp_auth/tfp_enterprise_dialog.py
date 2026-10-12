# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import wx.lib.scrolledpanel as scrolled
import re
from typing import Optional, Callable
from .tfp_auth_manager import auth_manager, TFP_CompanyInfo


def _spx_calc(value, scale_factor):
    """Scale pixels by TFP_DPI_SCALE_FACTOR. 对固定像素值进行DPI缩放。"""
    if value == -1:
        return -1
    return int(value * scale_factor)


class TFP_EnterpriseDialog(wx.Dialog):
    
    def __init__(self, parent, mode: str = "manage", on_success: Optional[Callable] = None):
        title = {
            "register": "注册企业",
            "join": "加入企业",
            "manage": "企业管理"
        }.get(mode, "企业管理")

        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(
            parent,
            title=title,
            size=(_spx_calc(500, self.TFP_DPI_SCALE_FACTOR), _spx_calc(550, self.TFP_DPI_SCALE_FACTOR)),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        
        self._mode = mode
        self._on_success = on_success
        self._init_ui()
        self.Centre()
        
        if mode == "manage":
            self._load_company_info()
    
    def _init_ui(self):
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        if self._mode == "register":
            content_panel = self._create_register_panel(panel)
        elif self._mode == "join":
            content_panel = self._create_join_panel(panel)
        else:
            content_panel = self._create_manage_panel(panel)
        
        main_sizer.Add(content_panel, 1, wx.EXPAND | wx.ALL, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
    
    def _create_register_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(15)
        
        title = wx.StaticText(panel, label="注册新企业")
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        desc = wx.StaticText(panel, label="注册企业后，您将成为企业管理员，可以邀请成员加入")
        desc.SetForegroundColour(wx.Colour(120, 140, 160))
        main_sizer.Add(desc, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        form_sizer = wx.FlexGridSizer(rows=6, cols=2, vgap=_spx_calc(10, self.TFP_DPI_SCALE_FACTOR), hgap=_spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        form_sizer.AddGrowableCol(1, 1)

        name_label = wx.StaticText(panel, label="企业名称 *")
        name_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.company_name = wx.TextCtrl(panel, size=(-1, _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        self.company_name.SetHint("请输入企业名称")
        form_sizer.Add(self.company_name, 0, wx.EXPAND | wx.RIGHT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        code_label = wx.StaticText(panel, label="企业代码 *")
        code_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(code_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.company_code = wx.TextCtrl(panel, size=(-1, _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        self.company_code.SetHint("3-10位大写字母或数字")
        form_sizer.Add(self.company_code, 0, wx.EXPAND | wx.RIGHT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        email_label = wx.StaticText(panel, label="联系邮箱 *")
        email_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(email_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.contact_email = wx.TextCtrl(panel, size=(-1, _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        self.contact_email.SetHint("企业联系邮箱")
        form_sizer.Add(self.contact_email, 0, wx.EXPAND | wx.RIGHT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        phone_label = wx.StaticText(panel, label="联系电话")
        phone_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(phone_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.contact_phone = wx.TextCtrl(panel, size=(-1, _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        self.contact_phone.SetHint("可选")
        form_sizer.Add(self.contact_phone, 0, wx.EXPAND | wx.RIGHT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        license_label = wx.StaticText(panel, label="许可证数量")
        license_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(license_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.license_count = wx.SpinCtrl(panel, value="1", min=1, max=1000, size=(-1, _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        form_sizer.Add(self.license_count, 0, wx.EXPAND | wx.RIGHT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        address_label = wx.StaticText(panel, label="企业地址")
        address_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(address_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.address = wx.TextCtrl(panel, size=(-1, _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        self.address.SetHint("可选")
        form_sizer.Add(self.address, 0, wx.EXPAND | wx.RIGHT, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.Add(form_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        cancel_btn = wx.Button(panel, label="取消", size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.register_btn = wx.Button(panel, label="注册企业", size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        self.register_btn.SetBackgroundColour(wx.Colour(26, 188, 156))
        self.register_btn.SetForegroundColour(wx.WHITE)
        self.register_btn.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.register_btn.Bind(wx.EVT_BUTTON, self._on_register)
        btn_sizer.Add(self.register_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.message_label = wx.StaticText(panel, label="")
        self.message_label.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.message_label, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddStretchSpacer()
        
        panel.SetSizer(main_sizer)
        return panel
    
    def _create_join_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(30)
        
        title = wx.StaticText(panel, label="加入企业")
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        desc = wx.StaticText(panel, label="请输入企业管理员提供的邀请码")
        desc.SetForegroundColour(wx.Colour(120, 140, 160))
        main_sizer.Add(desc, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR))

        form_sizer = wx.BoxSizer(wx.VERTICAL)

        code_label = wx.StaticText(panel, label="邀请码")
        code_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(code_label, 0, wx.LEFT | wx.BOTTOM, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.invitation_code = wx.TextCtrl(panel, size=(_spx_calc(300, self.TFP_DPI_SCALE_FACTOR), _spx_calc(40, self.TFP_DPI_SCALE_FACTOR)), style=wx.TE_CENTER)
        self.invitation_code.SetHint("XXXX-XXXXXXXX")
        self.invitation_code.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.invitation_code.Bind(wx.EVT_TEXT, self._on_code_change)
        form_sizer.Add(self.invitation_code, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR))

        self.company_info_label = wx.StaticText(panel, label="")
        self.company_info_label.SetForegroundColour(wx.Colour(39, 174, 96))
        self.company_info_label.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        form_sizer.Add(self.company_info_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.Add(form_sizer, 0, wx.ALIGN_CENTER)
        main_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        cancel_btn = wx.Button(panel, label="取消", size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.join_btn = wx.Button(panel, label="加入企业", size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        self.join_btn.SetBackgroundColour(wx.Colour(52, 152, 219))
        self.join_btn.SetForegroundColour(wx.WHITE)
        self.join_btn.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.join_btn.Bind(wx.EVT_BUTTON, self._on_join)
        self.join_btn.Disable()
        btn_sizer.Add(self.join_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.message_label = wx.StaticText(panel, label="")
        self.message_label.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.message_label, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddStretchSpacer()
        
        panel.SetSizer(main_sizer)
        return panel
    
    def _create_manage_panel(self, parent) -> wx.Panel:
        panel = scrolled.ScrolledPanel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(10)
        
        self.company_title = wx.StaticText(panel, label="企业信息")
        self.company_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.company_title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(self.company_title, 0, wx.LEFT | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.company_info_text = wx.StaticText(panel, label="加载中...")
        self.company_info_text.SetForegroundColour(wx.Colour(100, 120, 140))
        main_sizer.Add(self.company_info_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddSpacer(_spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        license_title = wx.StaticText(panel, label="License使用情况")
        license_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        license_title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(license_title, 0, wx.LEFT | wx.TOP | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.license_usage_text = wx.StaticText(panel, label="加载中...")
        self.license_usage_text.SetForegroundColour(wx.Colour(100, 120, 140))
        main_sizer.Add(self.license_usage_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddSpacer(_spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        members_title = wx.StaticText(panel, label="企业成员")
        members_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        members_title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(members_title, 0, wx.LEFT | wx.TOP | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.members_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(-1, _spx_calc(150, self.TFP_DPI_SCALE_FACTOR)))
        self.members_list.InsertColumn(0, "用户名", width=_spx_calc(120, self.TFP_DPI_SCALE_FACTOR))
        self.members_list.InsertColumn(1, "显示名称", width=_spx_calc(120, self.TFP_DPI_SCALE_FACTOR))
        self.members_list.InsertColumn(2, "角色", width=_spx_calc(80, self.TFP_DPI_SCALE_FACTOR))
        self.members_list.InsertColumn(3, "加入时间", width=_spx_calc(150, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.Add(self.members_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddSpacer(_spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        codes_title = wx.StaticText(panel, label="邀请码")
        codes_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        codes_title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(codes_title, 0, wx.LEFT | wx.TOP | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        codes_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        create_single_btn = wx.Button(panel, label="创建单次邀请码", size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        create_single_btn.Bind(wx.EVT_BUTTON, lambda e: self._create_code("single"))
        codes_btn_sizer.Add(create_single_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        create_multi_btn = wx.Button(panel, label="创建多次邀请码", size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(32, self.TFP_DPI_SCALE_FACTOR)))
        create_multi_btn.Bind(wx.EVT_BUTTON, lambda e: self._create_code("multi"))
        codes_btn_sizer.Add(create_multi_btn, 0)

        main_sizer.Add(codes_btn_sizer, 0, wx.LEFT | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.codes_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(-1, _spx_calc(120, self.TFP_DPI_SCALE_FACTOR)))
        self.codes_list.InsertColumn(0, "邀请码", width=_spx_calc(150, self.TFP_DPI_SCALE_FACTOR))
        self.codes_list.InsertColumn(1, "类型", width=_spx_calc(80, self.TFP_DPI_SCALE_FACTOR))
        self.codes_list.InsertColumn(2, "剩余次数", width=_spx_calc(80, self.TFP_DPI_SCALE_FACTOR))
        self.codes_list.InsertColumn(3, "过期时间", width=_spx_calc(150, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.Add(self.codes_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddSpacer(_spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        close_btn = wx.Button(panel, label="关闭", size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        btn_sizer.Add(close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
        panel.SetupScrolling()
        return panel
    
    def _load_company_info(self):
        result = auth_manager.get_company_info()
        
        if result.get("success"):
            company: TFP_CompanyInfo = result.get("company")
            is_admin = result.get("is_admin", False)
            
            info_text = f"企业名称: {company.company_name}\n"
            info_text += f"企业代码: {company.company_code}\n"
            info_text += f"许可证: {company.used_license_count}/{company.license_count}\n"
            info_text += f"联系邮箱: {company.contact_email}"
            
            self.company_info_text.SetLabel(info_text)
            self.company_title.SetLabel(f"企业: {company.company_name}")
            
            self._load_license_usage()
            self._load_members()
            self._load_invitation_codes()
        else:
            self.company_info_text.SetLabel(result.get("message", "获取企业信息失败"))
    
    def _load_license_usage(self):
        result = auth_manager.get_license_usage()
        
        if result.get("success"):
            data = result.get("data", {})
            license_count = data.get("license_count", 0)
            active_sessions = data.get("active_sessions", 0)
            usage_percentage = data.get("usage_percentage", 0)
            online_users = data.get("online_users", [])
            
            usage_text = f"License使用情况: {active_sessions}/{license_count} ({usage_percentage}%)\n"
            usage_text += f"可用License: {data.get('available_licenses', 0)}\n"
            
            if online_users:
                usage_text += "当前在线用户:\n"
                for user in online_users[:5]:
                    usage_text += f"  - {user.get('display_name', user.get('username', '未知'))} ({user.get('company_role', 'member')})\n"
                if len(online_users) > 5:
                    usage_text += f"  ... 还有 {len(online_users) - 5} 人在线"
            else:
                usage_text += "当前无在线用户"
            
            if hasattr(self, 'license_usage_text'):
                self.license_usage_text.SetLabel(usage_text)
    
    def _load_members(self):
        result = auth_manager.get_company_members()
        
        self.members_list.DeleteAllItems()
        
        if result.get("success"):
            members = result.get("data", {}).get("members", [])
            for member in members:
                index = self.members_list.InsertItem(self.members_list.GetItemCount(), member.get("username", ""))
                self.members_list.SetItem(index, 1, member.get("display_name", ""))
                self.members_list.SetItem(index, 2, member.get("role_display", ""))
                self.members_list.SetItem(index, 3, member.get("joined_at", "")[:19].replace("T", " ") if member.get("joined_at") else "")
    
    def _load_invitation_codes(self):
        result = auth_manager.get_invitation_codes(active_only=True)
        
        self.codes_list.DeleteAllItems()
        
        if result.get("success"):
            codes = result.get("data", {}).get("codes", [])
            for code in codes:
                index = self.codes_list.InsertItem(self.codes_list.GetItemCount(), code.get("code", ""))
                self.codes_list.SetItem(index, 1, code.get("code_type_display", ""))
                self.codes_list.SetItem(index, 2, str(code.get("remaining_uses", 0)))
                expires = code.get("expires_at", "")
                if expires:
                    expires = expires[:19].replace("T", " ")
                else:
                    expires = "永不过期"
                self.codes_list.SetItem(index, 3, expires)
    
    def _on_code_change(self, event):
        code = self.invitation_code.GetValue().strip().upper()
        
        if len(code) >= 8:
            result = auth_manager.validate_invitation_code(code)
            
            if result.get("valid"):
                self.company_info_label.SetLabel(f"将加入: {result.get('company_name', '')}")
                self.join_btn.Enable()
            else:
                self.company_info_label.SetLabel(result.get("message", "邀请码无效"))
                self.join_btn.Disable()
        else:
            self.company_info_label.SetLabel("")
            self.join_btn.Disable()
    
    def _on_register(self, event):
        company_name = self.company_name.GetValue().strip()
        company_code = self.company_code.GetValue().strip().upper()
        contact_email = self.contact_email.GetValue().strip()
        contact_phone = self.contact_phone.GetValue().strip()
        address = self.address.GetValue().strip()
        license_count = self.license_count.GetValue()
        
        if not company_name:
            self.message_label.SetLabel("请输入企业名称")
            return
        
        # 企业代码格式校验：大写字母+数字，3-10位
        if not company_code or len(company_code) < 3:
            self.message_label.SetLabel("企业代码至少需要3个字符")
            return
        if not re.match(r'^[A-Z0-9]{3,10}$', company_code):
            self.message_label.SetLabel("企业代码只能包含大写字母和数字，长度3-10位")
            return
        
        # 邮箱格式校验
        if not contact_email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', contact_email):
            self.message_label.SetLabel("请输入有效的联系邮箱")
            return
        
        self.message_label.SetLabel("正在注册...")
        self.register_btn.Disable()
        
        result = auth_manager.register_company(
            company_name=company_name,
            company_code=company_code,
            contact_email=contact_email,
            contact_phone=contact_phone if contact_phone else None,
            address=address if address else None,
            license_count=license_count
        )
        
        if result.get("success"):
            wx.MessageBox("企业注册成功！您已成为企业管理员。", "成功", wx.OK | wx.ICON_INFORMATION)
            if self._on_success:
                self._on_success()
            self.Close()
        else:
            self.message_label.SetLabel(result.get("message", "注册失败"))
            self.register_btn.Enable()
    
    def _on_join(self, event):
        code = self.invitation_code.GetValue().strip().upper()
        
        if not code:
            self.message_label.SetLabel("请输入邀请码")
            return
        
        self.message_label.SetLabel("正在加入...")
        self.join_btn.Disable()
        
        result = auth_manager.join_company(code)
        
        if result.get("success"):
            wx.MessageBox(f"成功加入企业: {result.get('company_name', '')}", "成功", wx.OK | wx.ICON_INFORMATION)
            if self._on_success:
                self._on_success()
            self.Close()
        else:
            self.message_label.SetLabel(result.get("message", "加入失败"))
            self.join_btn.Enable()
    
    def _create_code(self, code_type: str):
        max_uses = 1
        if code_type == "multi":
            dlg = wx.NumberEntryDialog(
                self,
                "请输入最大使用次数",
                "创建多次邀请码",
                1, 1, 100
            )
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            max_uses = dlg.GetValue()
            dlg.Destroy()
        else:
            max_uses = 1
        
        result = auth_manager.create_invitation_code(
            code_type=code_type,
            max_uses=max_uses,
            expires_days=30
        )
        
        if result.get("success"):
            code = result.get("code", "")
            wx.MessageBox(f"邀请码创建成功！\n\n邀请码: {code}\n\n请将此邀请码发送给需要加入的成员。", "成功", wx.OK | wx.ICON_INFORMATION)
            self._load_invitation_codes()
        else:
            wx.MessageBox(result.get("message", "创建失败"), "错误", wx.OK | wx.ICON_ERROR)


class TFP_QuickJoinCompanyDialog(wx.Dialog):

    def __init__(self, parent, invitation_code: str = None, on_success: Optional[Callable] = None):
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(
            parent,
            title="加入企业",
            size=(_spx_calc(400, self.TFP_DPI_SCALE_FACTOR), _spx_calc(300, self.TFP_DPI_SCALE_FACTOR)),
            style=wx.DEFAULT_DIALOG_STYLE
        )
        
        self._on_success = on_success
        self._init_ui(invitation_code)
        self.Centre()
    
    def _init_ui(self, invitation_code: str = None):
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(30)
        
        title = wx.StaticText(panel, label="加入企业")
        title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        desc = wx.StaticText(panel, label="请输入邀请码以加入企业")
        desc.SetForegroundColour(wx.Colour(120, 140, 160))
        main_sizer.Add(desc, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        code_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.code_input = wx.TextCtrl(panel, size=(_spx_calc(250, self.TFP_DPI_SCALE_FACTOR), _spx_calc(40, self.TFP_DPI_SCALE_FACTOR)), style=wx.TE_CENTER)
        self.code_input.SetHint("邀请码")
        self.code_input.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        if invitation_code:
            self.code_input.SetValue(invitation_code)
        code_sizer.Add(self.code_input, 0, wx.ALIGN_CENTER)

        main_sizer.Add(code_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        self.message_label = wx.StaticText(panel, label="")
        self.message_label.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.message_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        cancel_btn = wx.Button(panel, label="取消", size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.join_btn = wx.Button(panel, label="加入", size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        self.join_btn.SetBackgroundColour(wx.Colour(52, 152, 219))
        self.join_btn.SetForegroundColour(wx.WHITE)
        self.join_btn.Bind(wx.EVT_BUTTON, self._on_join)
        btn_sizer.Add(self.join_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER)
        
        panel.SetSizer(main_sizer)
    
    def _on_join(self, event):
        code = self.code_input.GetValue().strip().upper()
        
        if not code:
            self.message_label.SetLabel("请输入邀请码")
            return
        
        self.message_label.SetLabel("正在加入...")
        self.join_btn.Disable()
        
        result = auth_manager.join_company(code)
        
        if result.get("success"):
            wx.MessageBox(f"成功加入企业: {result.get('company_name', '')}", "成功", wx.OK | wx.ICON_INFORMATION)
            if self._on_success:
                self._on_success()
            self.Close()
        else:
            self.message_label.SetLabel(result.get("message", "加入失败"))
            self.join_btn.Enable()
