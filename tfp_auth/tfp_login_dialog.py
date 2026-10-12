# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import wx.adv
from typing import Optional, Callable
from .tfp_auth_manager import auth_manager, TFP_UserInfo
from tfp_utils.tfp_i18n_manager import translate, i18n


def _spx_calc(value, scale_factor):
    """Scale pixels by TFP_DPI_SCALE_FACTOR. 对固定像素值进行DPI缩放。"""
    if value == -1:
        return -1
    return int(value * scale_factor)


class TFP_LoginRegisterDialog(wx.Dialog):
    
    @staticmethod
    def _validate_password_strength(password: str) -> bool:
        has_digit = any(c.isdigit() for c in password)
        has_alpha = any(c.isalpha() for c in password)
        has_special = any(not c.isalnum() for c in password)
        return sum([has_digit, has_alpha, has_special]) >= 2
    
    @staticmethod
    def _validate_username_format(username: str) -> str:
        """校验用户名格式：字母开头，仅允许字母+数字+下划线，最少4个字符
        返回错误信息，校验通过返回空字符串
        """
        if not username or len(username) < 4:
            return translate("error_username_min_length")
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', username):
            return "用户名只能包含字母、数字和下划线，且必须以字母开头"
        return ''
    
    @staticmethod
    def _validate_email_format(email: str) -> str:
        """校验邮箱格式
        返回错误信息，校验通过返回空字符串
        """
        if not email:
            return translate("error_invalid_email")
        import re
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            return translate("error_invalid_email")
        return ''
    
    def __init__(self, parent, on_login_success: Optional[Callable] = None):
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(
            parent,
            title=translate("dialog_title_user_login"),
            size=(_spx_calc(520, self.TFP_DPI_SCALE_FACTOR), _spx_calc(480, self.TFP_DPI_SCALE_FACTOR)),
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP
        )
        
        self._on_login_success = on_login_success
        self._init_ui()
        self.Centre()
        
        # 设置键盘快捷键：Enter等同于点击确定/登录按钮，Esc等同于取消/关闭
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_event)
        
        # 弹窗显示后自动设置焦点到用户名输入框
        wx.CallAfter(self._set_initial_focus)
    
    def _init_ui(self):
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.notebook = wx.Notebook(panel, style=wx.NB_TOP)
        self.notebook.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        login_panel = self._create_login_panel(self.notebook)
        register_panel = self._create_register_panel(self.notebook)
        
        self.notebook.AddPage(login_panel, translate("tab_login"))
        self.notebook.AddPage(register_panel, translate("tab_register"))
        
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
    
    def _create_login_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        
        logo_sizer = wx.BoxSizer(wx.HORIZONTAL)
        logo_text = wx.StaticText(panel, label="TabulexFlow")
        logo_text.SetFont(wx.Font(18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        logo_text.SetForegroundColour(wx.Colour(70, 90, 110))
        logo_sizer.Add(logo_text, 0, wx.ALIGN_CENTER)
        main_sizer.Add(logo_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(8, self.TFP_DPI_SCALE_FACTOR))

        subtitle = wx.StaticText(panel, label=translate("label_platform"))
        subtitle.SetForegroundColour(wx.Colour(120, 140, 160))
        main_sizer.Add(subtitle, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        form_sizer = wx.BoxSizer(wx.VERTICAL)
        label_color = wx.Colour(70, 90, 110)
        sp5 = _spx_calc(5, self.TFP_DPI_SCALE_FACTOR)
        input_h = _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)

        username_label = wx.StaticText(panel, label=translate("label_username"))
        username_label.SetForegroundColour(label_color)
        form_sizer.Add(username_label, 0, wx.BOTTOM, sp5)

        self.login_username = wx.TextCtrl(panel, size=(-1, input_h), style=wx.TE_PROCESS_ENTER)
        self.login_username.SetHint(translate("hint_enter_username"))
        self.login_username.Bind(wx.EVT_TEXT_ENTER, self._on_login)
        form_sizer.Add(self.login_username, 0, wx.EXPAND | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        password_label = wx.StaticText(panel, label=translate("label_password"))
        password_label.SetForegroundColour(label_color)
        form_sizer.Add(password_label, 0, wx.BOTTOM, sp5)

        self.login_password = wx.TextCtrl(panel, size=(-1, input_h), style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        self.login_password.SetHint(translate("hint_enter_password"))
        self.login_password.Bind(wx.EVT_TEXT_ENTER, self._on_login)
        form_sizer.Add(self.login_password, 0, wx.EXPAND | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.Add(form_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _spx_calc(40, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.login_btn = wx.Button(panel, label=translate("btn_login_action"), size=(_spx_calc(160, self.TFP_DPI_SCALE_FACTOR), _spx_calc(42, self.TFP_DPI_SCALE_FACTOR)))
        self.login_btn.SetBackgroundColour(wx.Colour(26, 188, 156))
        self.login_btn.SetForegroundColour(wx.WHITE)
        self.login_btn.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.login_btn.Bind(wx.EVT_BUTTON, self._on_login)
        btn_sizer.Add(self.login_btn, 0, wx.ALIGN_CENTER)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, _spx_calc(8, self.TFP_DPI_SCALE_FACTOR))

        self.login_message = wx.StaticText(panel, label="")
        self.login_message.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.login_message, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, _spx_calc(40, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddStretchSpacer()

        demo_sizer = wx.BoxSizer(wx.HORIZONTAL)
        demo_text = wx.StaticText(panel, label=translate("label_test_account"))
        demo_text.SetForegroundColour(wx.Colour(149, 165, 166))
        demo_text.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
        demo_sizer.Add(demo_text, 0, wx.ALIGN_CENTER)
        main_sizer.Add(demo_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
        return panel
    
    def _create_register_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        
        # 标题
        title = wx.StaticText(panel, label=translate("label_create_new_account"))
        title.SetFont(wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        sf = self.TFP_DPI_SCALE_FACTOR
        sp2 = _spx_calc(2, sf)
        gap8 = _spx_calc(8, sf)
        input_h = _spx_calc(28, sf)
        label_color = wx.Colour(70, 90, 110)
        form_pad = _spx_calc(20, sf)

        # --- 第1行：用户名 + 显示名（各占1/2，8px间隙） ---
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        s1 = wx.BoxSizer(wx.VERTICAL)
        ul = wx.StaticText(panel, label=translate("label_username_required"))
        ul.SetForegroundColour(label_color)
        s1.Add(ul, 0, wx.BOTTOM, sp2)
        self.reg_username = wx.TextCtrl(panel, size=(-1, input_h))
        self.reg_username.SetHint(translate("hint_username_min_chars"))
        s1.Add(self.reg_username, 1, wx.EXPAND)
        row1.Add(s1, 1, wx.RIGHT, gap8)
        s2 = wx.BoxSizer(wx.VERTICAL)
        dl = wx.StaticText(panel, label=translate("label_display_name"))
        dl.SetForegroundColour(label_color)
        s2.Add(dl, 0, wx.BOTTOM, sp2)
        self.reg_display_name = wx.TextCtrl(panel, size=(-1, input_h))
        self.reg_display_name.SetHint(translate("hint_optional"))
        s2.Add(self.reg_display_name, 1, wx.EXPAND)
        row1.Add(s2, 1)
        main_sizer.Add(row1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, form_pad)

        # --- 第2行：邮箱(1/2) + 验证码输入框+发送按钮(1/2) ---
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 邮箱（左半）
        s3 = wx.BoxSizer(wx.VERTICAL)
        el = wx.StaticText(panel, label=translate("label_email_required"))
        el.SetForegroundColour(label_color)
        s3.Add(el, 0, wx.BOTTOM, sp2)
        self.reg_email = wx.TextCtrl(panel, size=(-1, input_h))
        self.reg_email.SetHint(translate("hint_email_format"))
        s3.Add(self.reg_email, 1, wx.EXPAND)
        row2.Add(s3, 1, wx.RIGHT, gap8)
        # 验证码+发送按钮（右半）
        s3b = wx.BoxSizer(wx.VERTICAL)
        vcl = wx.StaticText(panel, label=translate("label_email_verify_code"))
        vcl.SetForegroundColour(label_color)
        s3b.Add(vcl, 0, wx.BOTTOM, sp2)
        code_row = wx.BoxSizer(wx.HORIZONTAL)
        self.reg_email_code = wx.TextCtrl(panel, size=(-1, input_h))
        self.reg_email_code.SetHint(translate("hint_email_verify_code"))
        code_row.Add(self.reg_email_code, 1, wx.RIGHT, _spx_calc(4, sf))
        self.send_code_btn = wx.Button(panel, label=translate("btn_send_verify_code"),
                                        size=(_spx_calc(90, sf), input_h))
        self.send_code_btn.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.send_code_btn.Bind(wx.EVT_BUTTON, self._on_send_verify_code)
        code_row.Add(self.send_code_btn, 0)
        s3b.Add(code_row, 1, wx.EXPAND)
        # 验证状态标签
        self.email_verified_label = wx.StaticText(panel, label="")
        self.email_verified_label.SetForegroundColour(wx.Colour(46, 204, 113))
        self.email_verified_label.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        s3b.Add(self.email_verified_label, 0, wx.TOP, sp2)
        row2.Add(s3b, 1)
        main_sizer.Add(row2, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, form_pad)

        # --- 第3行：密码 + 确认密码（各占1/2，8px间隙） ---
        row3 = wx.BoxSizer(wx.HORIZONTAL)
        s4 = wx.BoxSizer(wx.VERTICAL)
        pl = wx.StaticText(panel, label=translate("label_password_required"))
        pl.SetForegroundColour(label_color)
        s4.Add(pl, 0, wx.BOTTOM, sp2)
        self.reg_password = wx.TextCtrl(panel, size=(-1, input_h), style=wx.TE_PASSWORD)
        self.reg_password.SetHint(translate("hint_password_min_chars"))
        s4.Add(self.reg_password, 1, wx.EXPAND)
        row3.Add(s4, 1, wx.RIGHT, gap8)
        s5 = wx.BoxSizer(wx.VERTICAL)
        cl = wx.StaticText(panel, label=translate("label_confirm_password"))
        cl.SetForegroundColour(label_color)
        s5.Add(cl, 0, wx.BOTTOM, sp2)
        self.reg_confirm_password = wx.TextCtrl(panel, size=(-1, input_h), style=wx.TE_PASSWORD)
        self.reg_confirm_password.SetHint(translate("hint_reenter_password"))
        s5.Add(self.reg_confirm_password, 1, wx.EXPAND)
        row3.Add(s5, 1)
        main_sizer.Add(row3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, form_pad)

        # --- 第4行：邀请码（整行宽度） ---
        s6 = wx.BoxSizer(wx.VERTICAL)
        il = wx.StaticText(panel, label=translate("label_invitation_code"))
        il.SetForegroundColour(label_color)
        s6.Add(il, 0, wx.BOTTOM, sp2)
        self.reg_invitation_code = wx.TextCtrl(panel, size=(-1, input_h))
        self.reg_invitation_code.SetHint(translate("hint_invitation_code"))
        s6.Add(self.reg_invitation_code, 1, wx.EXPAND)
        main_sizer.Add(s6, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, form_pad)

        main_sizer.AddSpacer(_spx_calc(6, sf))

        # 注册按钮
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.register_btn = wx.Button(panel, label=translate("btn_register_action"),
                                       size=(_spx_calc(160, sf), _spx_calc(36, sf)))
        self.register_btn.SetBackgroundColour(wx.Colour(52, 152, 219))
        self.register_btn.SetForegroundColour(wx.WHITE)
        self.register_btn.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.register_btn.Bind(wx.EVT_BUTTON, self._on_register)
        btn_sizer.Add(self.register_btn, 0, wx.ALIGN_CENTER)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, _spx_calc(6, sf))

        # 错误消息
        self.register_message = wx.StaticText(panel, label="")
        self.register_message.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.register_message, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, form_pad)

        main_sizer.AddStretchSpacer()
        
        # 邮箱验证状态
        self._email_verified = False
        self._code_countdown_timer = None
        
        panel.SetSizer(main_sizer)
        return panel
    
    def _on_send_verify_code(self, event):
        """发送邮箱验证码"""
        email = self.reg_email.GetValue().strip()
        username = self.reg_username.GetValue().strip()
        
        # 先校验邮箱格式
        email_error = self._validate_email_format(email)
        if email_error:
            self.register_message.SetLabel(email_error)
            return
        
        self.send_code_btn.Disable()
        self.register_message.SetLabel(translate("status_sending_code"))
        
        wx.CallLater(100, self._do_send_verify_code, email, username)
    
    def _do_send_verify_code(self, email: str, username: str):
        result = auth_manager.send_email_verify_code(email, username)
        
        if result.get("success"):
            self.register_message.SetLabel("")
            self._start_code_countdown(60)
        else:
            self.register_message.SetLabel(result.get("message", translate("error_send_code_failed")))
            self.send_code_btn.Enable()
    
    def _start_code_countdown(self, seconds: int):
        """启动验证码倒计时"""
        self._countdown_seconds = seconds
        self._update_countdown_button()
        if self._code_countdown_timer:
            self._code_countdown_timer.Stop()
        self._code_countdown_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_countdown_tick, self._code_countdown_timer)
        self._code_countdown_timer.Start(1000)
    
    def _on_countdown_tick(self, event):
        """倒计时每秒触发"""
        self._countdown_seconds -= 1
        if self._countdown_seconds <= 0:
            self._code_countdown_timer.Stop()
            self.send_code_btn.SetLabel(translate("btn_send_verify_code"))
            self.send_code_btn.Enable()
        else:
            self._update_countdown_button()
    
    def _update_countdown_button(self):
        self.send_code_btn.SetLabel(
            translate("btn_send_verify_code_retry", seconds=self._countdown_seconds)
        )
    
    def _on_login(self, event):
        username = self.login_username.GetValue().strip()
        password = self.login_password.GetValue()
        
        if not username:
            self.login_message.SetLabel(translate("error_enter_username"))
            return
        
        if not password:
            self.login_message.SetLabel(translate("error_enter_password"))
            return
        
        self.login_btn.Disable()
        self.login_message.SetLabel(translate("status_logging_in"))
        
        wx.CallLater(100, self._do_login, username, password)
    
    def _do_login(self, username: str, password: str):
        result = auth_manager.login_user(username, password)
        
        if result.get("success"):
            self.login_message.SetLabel("")
            self._close_with_success()
        else:
            message = result.get("message", translate("error_login_failed"))

            self.login_message.SetLabel(message)
            self.login_btn.Enable()

    def _terminate_other_sessions_and_login(self, username: str, password: str):
        temp_result = auth_manager.login_user(username, password)
        
        if temp_result.get("success"):
            term_result = auth_manager.terminate_other_sessions()
            
            if term_result.get("success"):
                self.login_message.SetLabel("")
                self._close_with_success()
            else:
                auth_manager.logout_user()
                self.login_message.SetLabel(translate("error_terminate_session_failed"))
                self.login_btn.Enable()
        else:
            self.login_message.SetLabel(temp_result.get("message", translate("error_login_failed")))
            self.login_btn.Enable()
    
    def _on_register(self, event):
        username = self.reg_username.GetValue().strip()
        email = self.reg_email.GetValue().strip()
        display_name = self.reg_display_name.GetValue().strip()
        password = self.reg_password.GetValue()
        confirm_password = self.reg_confirm_password.GetValue()
        invitation_code = self.reg_invitation_code.GetValue().strip().upper()
        email_code = self.reg_email_code.GetValue().strip() if hasattr(self, 'reg_email_code') else ''
        
        if not username or len(username) < 4:
            self.register_message.SetLabel(translate("error_username_min_length"))
            return
        
        # 用户名格式校验：字母开头，仅允许字母+数字+下划线
        username_format_error = self._validate_username_format(username)
        if username_format_error:
            self.register_message.SetLabel(username_format_error)
            return
        
        # 邮箱格式校验
        email_format_error = self._validate_email_format(email)
        if email_format_error:
            self.register_message.SetLabel(email_format_error)
            return
        
        # 邮箱验证码校验
        if not self._email_verified:
            if not email_code:
                self.register_message.SetLabel(translate("error_email_verify_code_required"))
                return
            if len(email_code) != 6 or not email_code.isdigit():
                self.register_message.SetLabel(translate("error_email_verify_code_format"))
                return
            # 先验证邮箱验证码，成功后再注册
            self.register_btn.Disable()
            self.register_message.SetLabel("")
            wx.CallLater(100, self._do_verify_email_then_register, email, email_code,
                         username, password, display_name, invitation_code)
            return
        
        if not password or len(password) < 8:
            self.register_message.SetLabel(translate("error_password_min_length"))
            return
        
        if not self._validate_password_strength(password):
            self.register_message.SetLabel(translate("error_password_strength"))
            return
        
        if password != confirm_password:
            self.register_message.SetLabel(translate("error_password_mismatch"))
            return
        
        self.register_btn.Disable()
        self.register_message.SetLabel(translate("status_registering"))
        
        wx.CallLater(100, self._do_register, username, email, password, display_name, invitation_code)
    
    def _do_verify_email_then_register(self, email: str, code: str,
                                        username: str, password: str,
                                        display_name: str, invitation_code: str):
        """先验证邮箱验证码，成功后再执行注册"""
        result = auth_manager.verify_email_code(email, code)
        if result.get("success"):
            self._email_verified = True
            self.email_verified_label.SetLabel(translate("status_email_verified"))
            self.reg_email_code.Disable()
            self.reg_email.Disable()
            self.send_code_btn.Disable()
            # 继续校验密码等
            confirm_password = self.reg_confirm_password.GetValue()
            if not password or len(password) < 8:
                self.register_message.SetLabel(translate("error_password_min_length"))
                self.register_btn.Enable()
                return
            if not self._validate_password_strength(password):
                self.register_message.SetLabel(translate("error_password_strength"))
                self.register_btn.Enable()
                return
            if password != confirm_password:
                self.register_message.SetLabel(translate("error_password_mismatch"))
                self.register_btn.Enable()
                return
            self.register_message.SetLabel(translate("status_registering"))
            wx.CallLater(100, self._do_register, username, email, password, display_name, invitation_code)
        else:
            self.register_message.SetLabel(result.get("message", translate("error_email_verify_code_invalid")))
            self.register_btn.Enable()
    
    def _do_register(self, username: str, email: str, password: str, display_name: str, invitation_code: str = None):
        result = auth_manager.register_user_with_invitation(username, email, password, display_name or None, invitation_code or None)
        
        if result.get("success"):
            self.register_message.SetForegroundColour(wx.Colour(46, 204, 113))
            self.register_message.SetLabel(translate("status_register_success"))
            
            wx.CallLater(500, self._auto_login_after_register, username, password)
        else:
            self.register_message.SetForegroundColour(wx.Colour(231, 76, 60))
            self.register_message.SetLabel(result.get("message", translate("error_register_failed")))
            self.register_btn.Enable()
    
    def _auto_login_after_register(self, username: str, password: str):
        result = auth_manager.login_user(username, password)
        
        if result.get("success"):
            self._close_with_success()
        else:
            self.register_message.SetLabel(translate("error_auto_login_failed"))
            self.register_btn.Enable()
    
    def _close_with_success(self):
        self._stop_countdown_timer()
        if self._on_login_success:
            self._on_login_success()
        self.EndModal(wx.ID_OK)
        self.Close()
    
    def _stop_countdown_timer(self):
        """停止验证码倒计时定时器"""
        if self._code_countdown_timer:
            self._code_countdown_timer.Stop()
            self._code_countdown_timer = None
    
    def _set_initial_focus(self):
        """设置初始焦点到用户名输入框"""
        if hasattr(self, 'login_username') and self.login_username:
            self.login_username.SetFocus()
            self.login_username.SelectAll()
    
    def _on_key_event(self, event):
        """处理键盘事件：Enter执行登录/注册，Esc关闭弹窗"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_ESCAPE:
            # Esc键关闭弹窗
            self._stop_countdown_timer()
            self.EndModal(wx.ID_CANCEL)
            self.Close()
            return
        
        if key_code == wx.WXK_RETURN:
            # Enter键执行当前标签页的操作
            current_page = self.notebook.GetSelection() if hasattr(self, 'notebook') else 0
            if current_page == 0:
                # 登录标签页：触发登录
                self._on_login(event)
            else:
                # 注册标签页：触发注册
                self._on_register(event)
            return
        
        event.Skip()
    
    def ShowLoginDialog(self):
        return self.ShowModal()


class TFP_PermissionRequiredDialog(wx.Dialog):

    def __init__(self, parent, title: str = None, message: str = "",
                 required_type: str = "premium", current_type: str = "free"):
        actual_title = title if title else translate("dialog_title_permission_required")
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(
            parent,
            title=actual_title,
            size=(_spx_calc(400, self.TFP_DPI_SCALE_FACTOR), -1),
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP
        )
        
        self._init_ui(message, required_type, current_type)
        self.Centre()
        
        # 根据内容自动调整窗口大小，确保按钮等控件完整显示
        self.Fit()
        
        # 设置键盘快捷键：Esc关闭弹窗
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_event)
    
    def _init_ui(self, message: str, required_type: str, current_type: str):
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        
        icon_text = wx.StaticText(panel, label="🔒")
        icon_text.SetFont(wx.Font(36, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        main_sizer.Add(icon_text, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        title_text = wx.StaticText(panel, label=translate("label_higher_permission_needed"))
        title_text.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title_text.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title_text, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        if message:
            msg_text = wx.StaticText(panel, label=message)
            msg_text.SetForegroundColour(wx.Colour(100, 100, 100))
            msg_text.Wrap(_spx_calc(350, self.TFP_DPI_SCALE_FACTOR))
            main_sizer.Add(msg_text, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        type_text = wx.StaticText(
            panel,
            label=f"{translate('label_current_account_type', type=current_type.upper())}\n{translate('label_required_account_type', type=required_type.upper())}"
        )
        type_text.SetForegroundColour(wx.Colour(120, 140, 160))
        main_sizer.Add(type_text, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        close_btn = wx.Button(panel, label=translate("button_close"), size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        btn_sizer.Add(close_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        upgrade_btn = wx.Button(panel, label=translate("btn_upgrade_account"), size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        upgrade_btn.SetBackgroundColour(wx.Colour(52, 152, 219))
        upgrade_btn.SetForegroundColour(wx.WHITE)
        upgrade_btn.Bind(wx.EVT_BUTTON, self._on_upgrade)
        btn_sizer.Add(upgrade_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
    
    def _on_upgrade(self, event):
        wx.MessageBox(
            translate("message_contact_admin_upgrade"),
            translate("dialog_title_upgrade_account"),
            wx.OK | wx.ICON_INFORMATION
        )
    
    def _on_close(self, event):
        self.EndModal(wx.ID_CANCEL)
        self.Close()
    
    def _on_key_event(self, event):
        """处理键盘事件：Esc关闭弹窗"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            self.Close()
            return
        
        event.Skip()


class TFP_LoginRequiredDialog(wx.Dialog):

    def __init__(self, parent, message: str = None,
                 on_login_success: Optional[Callable] = None):
        actual_message = message if message else translate("message_login_required")
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(
            parent,
            title=translate("dialog_title_login_required"),
            size=(_spx_calc(400, self.TFP_DPI_SCALE_FACTOR), _spx_calc(220, self.TFP_DPI_SCALE_FACTOR)),
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP
        )
        
        self._on_login_success = on_login_success
        self._init_ui(actual_message)
        self.Centre()
        
        # 设置键盘快捷键：Enter点击登录，Esc取消
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_event)
    
    def _init_ui(self, message: str):
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        
        icon_text = wx.StaticText(panel, label="🔐")
        icon_text.SetFont(wx.Font(36, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        main_sizer.Add(icon_text, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        msg_text = wx.StaticText(panel, label=message)
        msg_text.SetForegroundColour(wx.Colour(70, 90, 110))
        msg_text.Wrap(_spx_calc(350, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.Add(msg_text, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        cancel_btn = wx.Button(panel, label=translate("btn_cancel"), size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_sizer.Add(cancel_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        login_btn = wx.Button(panel, label=translate("btn_login_now"), size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(38, self.TFP_DPI_SCALE_FACTOR)))
        login_btn.SetBackgroundColour(wx.Colour(26, 188, 156))
        login_btn.SetForegroundColour(wx.WHITE)
        login_btn.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        login_btn.Bind(wx.EVT_BUTTON, self._on_login)
        btn_sizer.Add(login_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
    
    def _on_login(self, event):
        self.EndModal(wx.ID_OK)
        self.Close()
        
        wx.CallAfter(self._show_login_dialog)
    
    def _show_login_dialog(self):
        parent = self.GetParent()
        # 若 parent 为 None（如通过 request_login_via_ipc 创建），回退到主窗口
        if parent is None:
            try:
                for tlw in wx.GetTopLevelWindows():
                    if type(tlw).__name__ == 'TFP_MainFrame':
                        parent = tlw
                        break
                if parent is None:
                    for tlw in wx.GetTopLevelWindows():
                        if tlw.IsShown():
                            parent = tlw
                            break
            except Exception:
                pass
        dlg = TFP_LoginRegisterDialog(parent, self._on_login_success)
        result = dlg.ShowLoginDialog()
        dlg.Destroy()
        
        if result == wx.ID_OK and self._on_login_success:
            self._on_login_success()
    
    def _on_cancel(self, event):
        self.EndModal(wx.ID_CANCEL)
        self.Close()
    
    def _on_key_event(self, event):
        """处理键盘事件：Enter点击登录，Esc取消"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            self.Close()
            return
        
        if key_code == wx.WXK_RETURN:
            self._on_login(event)
            return
        
        event.Skip()


class TFP_UserProfileDialog(wx.Dialog):

    def __init__(self, parent, on_update_success: Optional[Callable] = None):
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(
            parent,
            title="用户信息",
            size=(_spx_calc(450, self.TFP_DPI_SCALE_FACTOR), _spx_calc(520, self.TFP_DPI_SCALE_FACTOR)),
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP
        )
        
        self._on_update_success = on_update_success
        self._init_ui()
        self._load_user_info()
        self.Centre()
    
    def _init_ui(self):
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))
        
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        avatar_text = wx.StaticText(panel, label="👤")
        avatar_text.SetFont(wx.Font(36, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        header_sizer.Add(avatar_text, 0, wx.ALIGN_CENTER | wx.RIGHT, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        info_sizer = wx.BoxSizer(wx.VERTICAL)

        self.display_name_label = wx.StaticText(panel, label="用户名")
        self.display_name_label.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.display_name_label.SetForegroundColour(wx.Colour(70, 90, 110))
        info_sizer.Add(self.display_name_label, 0, wx.BOTTOM, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        self.user_type_label = wx.StaticText(panel, label="FREE")
        self.user_type_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.user_type_label.SetForegroundColour(wx.Colour(120, 140, 160))
        info_sizer.Add(self.user_type_label, 0)

        header_sizer.Add(info_sizer, 1, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        notebook = wx.Notebook(panel, style=wx.NB_TOP)
        notebook.SetBackgroundColour(wx.Colour(250, 250, 250))

        profile_panel = self._create_profile_panel(notebook)
        security_panel = self._create_security_panel(notebook)
        upgrade_panel = self._create_upgrade_panel(notebook)

        notebook.AddPage(profile_panel, "个人资料")
        notebook.AddPage(security_panel, "安全设置")
        notebook.AddPage(upgrade_panel, "账户升级")

        main_sizer.Add(notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        close_btn = wx.Button(panel, label="关闭", size=(_spx_calc(100, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        main_sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))
        
        panel.SetSizer(main_sizer)
    
    def _create_profile_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))
        
        form_sizer = wx.FlexGridSizer(4, 2, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR), _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        form_sizer.AddGrowableCol(1, 1)

        username_label = wx.StaticText(panel, label="用户名:")
        username_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(username_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self.username_value = wx.StaticText(panel, label="")
        self.username_value.SetForegroundColour(wx.Colour(100, 100, 100))
        form_sizer.Add(self.username_value, 0, wx.ALIGN_CENTER_VERTICAL)

        email_label = wx.StaticText(panel, label="邮箱:")
        email_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(email_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self.email_input = wx.TextCtrl(panel, size=(-1, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR)))
        form_sizer.Add(self.email_input, 0, wx.EXPAND)

        display_label = wx.StaticText(panel, label="显示名称:")
        display_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(display_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self.display_name_input = wx.TextCtrl(panel, size=(-1, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR)))
        form_sizer.Add(self.display_name_input, 0, wx.EXPAND)

        created_label = wx.StaticText(panel, label="注册时间:")
        created_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(created_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self.created_value = wx.StaticText(panel, label="")
        self.created_value.SetForegroundColour(wx.Colour(100, 100, 100))
        form_sizer.Add(self.created_value, 0, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(form_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        self.profile_message = wx.StaticText(panel, label="")
        self.profile_message.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.profile_message, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        save_btn = wx.Button(panel, label="保存修改", size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        save_btn.SetBackgroundColour(wx.Colour(26, 188, 156))
        save_btn.SetForegroundColour(wx.WHITE)
        save_btn.Bind(wx.EVT_BUTTON, self._on_save_profile)
        main_sizer.Add(save_btn, 0, wx.ALIGN_CENTER | wx.TOP, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        
        main_sizer.AddStretchSpacer()
        panel.SetSizer(main_sizer)
        return panel
    
    def _create_security_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))
        
        title = wx.StaticText(panel, label="修改密码")
        title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        form_sizer = wx.BoxSizer(wx.VERTICAL)

        current_label = wx.StaticText(panel, label="当前密码")
        current_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(current_label, 0, wx.LEFT | wx.BOTTOM, _spx_calc(3, self.TFP_DPI_SCALE_FACTOR))

        self.current_password = wx.TextCtrl(panel, size=(-1, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR)), style=wx.TE_PASSWORD)
        form_sizer.Add(self.current_password, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        new_label = wx.StaticText(panel, label="新密码")
        new_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(new_label, 0, wx.LEFT | wx.TOP | wx.BOTTOM, _spx_calc(3, self.TFP_DPI_SCALE_FACTOR))

        self.new_password = wx.TextCtrl(panel, size=(-1, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR)), style=wx.TE_PASSWORD)
        form_sizer.Add(self.new_password, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        confirm_label = wx.StaticText(panel, label="确认新密码")
        confirm_label.SetForegroundColour(wx.Colour(70, 90, 110))
        form_sizer.Add(confirm_label, 0, wx.LEFT | wx.TOP | wx.BOTTOM, _spx_calc(3, self.TFP_DPI_SCALE_FACTOR))

        self.confirm_password = wx.TextCtrl(panel, size=(-1, _spx_calc(30, self.TFP_DPI_SCALE_FACTOR)), style=wx.TE_PASSWORD)
        form_sizer.Add(self.confirm_password, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(5, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.Add(form_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        self.password_message = wx.StaticText(panel, label="")
        self.password_message.SetForegroundColour(wx.Colour(231, 76, 60))
        main_sizer.Add(self.password_message, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        change_btn = wx.Button(panel, label="修改密码", size=(_spx_calc(120, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        change_btn.SetBackgroundColour(wx.Colour(52, 152, 219))
        change_btn.SetForegroundColour(wx.WHITE)
        change_btn.Bind(wx.EVT_BUTTON, self._on_change_password)
        main_sizer.Add(change_btn, 0, wx.ALIGN_CENTER | wx.TOP, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))
        
        main_sizer.AddStretchSpacer()
        panel.SetSizer(main_sizer)
        return panel
    
    def _create_upgrade_panel(self, parent) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(wx.Colour(250, 250, 250))

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        title = wx.StaticText(panel, label="账户类型说明")
        title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        title.SetForegroundColour(wx.Colour(70, 90, 110))
        main_sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, _spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        # 账户类型说明（user_type 三值 + UI 派生显示等级）
        types_info = [
            ("Free（免费）", "免费用户：可使用基础工具 + 收费工具的免费次数（15次/月）", wx.Colour(149, 165, 166)),
            ("Premium（高级）", "已订购任意工具的个人用户：已订购工具无限使用，未订购工具走免费次数", wx.Colour(46, 204, 113)),
            ("Enterprise（企业）", "企业年费用户：企业级功能（批量比对/API/团队管理）+ 推广期赠送 TFP_CORE 工具集", wx.Colour(52, 152, 219)),
            ("Platform（平台）", "平台管理员：拥有全部权限", wx.Colour(231, 76, 60)),
        ]

        for type_name, desc, color in types_info:
            type_sizer = wx.BoxSizer(wx.HORIZONTAL)
            type_sizer.AddSpacer(_spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

            type_label = wx.StaticText(panel, label=type_name)
            type_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            type_label.SetForegroundColour(color)
            type_sizer.Add(type_label, 0, wx.ALIGN_TOP | wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

            desc_label = wx.StaticText(panel, label=desc)
            desc_label.SetForegroundColour(wx.Colour(100, 100, 100))
            desc_label.Wrap(_spx_calc(280, self.TFP_DPI_SCALE_FACTOR))
            type_sizer.Add(desc_label, 1, wx.ALIGN_TOP)

            main_sizer.Add(type_sizer, 0, wx.EXPAND | wx.BOTTOM, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddSpacer(_spx_calc(15, self.TFP_DPI_SCALE_FACTOR))

        self.upgrade_message = wx.StaticText(panel, label="")
        self.upgrade_message.SetForegroundColour(wx.Colour(46, 204, 113))
        main_sizer.Add(self.upgrade_message, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, _spx_calc(20, self.TFP_DPI_SCALE_FACTOR))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 升级按钮：订购工具 / 开通 Enterprise 年费
        self.upgrade_premium_btn = wx.Button(panel, label="订购工具", size=(_spx_calc(150, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        self.upgrade_premium_btn.SetBackgroundColour(wx.Colour(46, 204, 113))
        self.upgrade_premium_btn.SetForegroundColour(wx.WHITE)
        self.upgrade_premium_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_request_upgrade("toolkit"))
        btn_sizer.Add(self.upgrade_premium_btn, 0, wx.RIGHT, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        self.upgrade_enterprise_btn = wx.Button(panel, label="开通 Enterprise 年费", size=(_spx_calc(160, self.TFP_DPI_SCALE_FACTOR), _spx_calc(35, self.TFP_DPI_SCALE_FACTOR)))
        self.upgrade_enterprise_btn.SetBackgroundColour(wx.Colour(52, 152, 219))
        self.upgrade_enterprise_btn.SetForegroundColour(wx.WHITE)
        self.upgrade_enterprise_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_request_upgrade("enterprise"))
        btn_sizer.Add(self.upgrade_enterprise_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.TOP, _spx_calc(10, self.TFP_DPI_SCALE_FACTOR))

        main_sizer.AddStretchSpacer()
        panel.SetSizer(main_sizer)
        return panel
    
    def _load_user_info(self):
        user = auth_manager.get_current_user()
        if user:
            self.display_name_label.SetLabel(user.display_name or user.username)
            self.user_type_label.SetLabel(f"{user.user_type.upper()} 用户")
            self.username_value.SetLabel(user.username)
            self.email_input.SetValue(user.email)
            self.display_name_input.SetValue(user.display_name or user.username)
            
            if user.created_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(user.created_at.replace("Z", "+00:00"))
                    self.created_value.SetLabel(dt.strftime("%Y-%m-%d %H:%M"))
                except (ValueError, AttributeError):
                    self.created_value.SetLabel(user.created_at)
            
            if user.user_type == "premium":
                self.upgrade_premium_btn.Disable()
            elif user.user_type == "enterprise":
                self.upgrade_premium_btn.Disable()
                self.upgrade_enterprise_btn.Disable()
    
    def _on_save_profile(self, event):
        display_name = self.display_name_input.GetValue().strip()
        email = self.email_input.GetValue().strip()
        
        if not display_name:
            self.profile_message.SetLabel("显示名称不能为空")
            return
        
        result = auth_manager.update_profile(display_name, email if email else None)
        
        if result.get("success"):
            self.profile_message.SetForegroundColour(wx.Colour(46, 204, 113))
            self.profile_message.SetLabel("资料更新成功")
            self.display_name_label.SetLabel(display_name)
            
            if self._on_update_success:
                self._on_update_success()
        else:
            self.profile_message.SetForegroundColour(wx.Colour(231, 76, 60))
            self.profile_message.SetLabel(result.get("message", "更新失败"))
    
    def _on_change_password(self, event):
        current = self.current_password.GetValue()
        new = self.new_password.GetValue()
        confirm = self.confirm_password.GetValue()
        
        if not current or not new or not confirm:
            self.password_message.SetLabel("请填写所有密码字段")
            return
        
        if new != confirm:
            self.password_message.SetLabel("两次输入的新密码不一致")
            return
        
        if len(new) < 8:
            self.password_message.SetLabel("新密码至少需要8个字符")
            return
        
        if not self._validate_password_strength(new):
            self.password_message.SetLabel("密码需包含数字、字母、特殊字符中的两种或以上")
            return
        
        result = auth_manager.change_password(current, new)
        
        if result.get("success"):
            self.password_message.SetForegroundColour(wx.Colour(46, 204, 113))
            self.password_message.SetLabel("密码修改成功，请重新登录")
            
            wx.CallLater(1500, self._close_and_logout)
        else:
            self.password_message.SetForegroundColour(wx.Colour(231, 76, 60))
            self.password_message.SetLabel(result.get("message", "修改失败"))
    
    @staticmethod
    def _validate_password_strength(password: str) -> bool:
        has_digit = any(c.isdigit() for c in password)
        has_alpha = any(c.isalpha() for c in password)
        has_special = any(not c.isalnum() for c in password)
        return sum([has_digit, has_alpha, has_special]) >= 2
    
    def _on_request_upgrade(self, target_type: str):
        result = auth_manager.request_upgrade(target_type)
        
        if result.get("success"):
            self.upgrade_message.SetLabel(result.get("message", "申请已提交"))
        else:
            self.upgrade_message.SetForegroundColour(wx.Colour(231, 76, 60))
            self.upgrade_message.SetLabel(result.get("message", "申请失败"))
    
    def _close_and_logout(self):
        auth_manager.logout_user()
        self.EndModal(wx.ID_OK)
        self.Close()
    
    def _on_close(self, event):
        self.EndModal(wx.ID_CANCEL)
        self.Close()
