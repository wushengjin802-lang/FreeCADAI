"""Dockable AI panel for the phase 4 FreeCADAI prototype."""

import json
import traceback

import FreeCAD as App
import FreeCADGui as Gui

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError:  # FreeCAD builds may expose PySide instead of PySide2.
    from PySide import QtCore, QtGui
    QtWidgets = QtGui

from freecad_ai.cloud.client import FreeCADAICloudClient, format_cloud_error
from freecad_ai.executor import execute_script
from freecad_ai.freecad_context import collect_context
from freecad_ai.llm.client import LLMClientError, OpenAICompatibleClient, format_llm_error
from freecad_ai.llm.prompts import (
    build_generation_messages,
    build_regeneration_with_parameters_messages,
    build_repair_messages,
)
from freecad_ai.llm.schemas import LLMResponseError, parse_generation_response
from freecad_ai.local_examples import build_local_example_payload
from freecad_ai.storage.config import load_config, save_config
from freecad_ai.storage.history import append_history, load_recent_history
from freecad_ai.templates import get_template_prompt, template_names
from freecad_ai.validator import ScriptValidationError, validate_script


PANEL_OBJECT_NAME = "FreeCADAIPhase4Panel"


class BackgroundTask(QtCore.QObject):
    """Run network-bound work outside the FreeCAD UI thread."""

    finished = QtCore.Signal(str, object)
    failed = QtCore.Signal(str, str)

    def __init__(self, name, callback):
        super().__init__()
        self.name = name
        self.callback = callback

    @QtCore.Slot()
    def run(self):
        try:
            self.finished.emit(self.name, self.callback())
        except Exception:
            self.failed.emit(self.name, traceback.format_exc())


class PromptTextEdit(QtWidgets.QPlainTextEdit):
    """Plain text input that avoids accidental full-selection replacement."""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._clear_full_selection()

    def mousePressEvent(self, event):
        self._clear_full_selection()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self._has_full_selection() and event.key() not in (
            QtCore.Qt.Key_Backspace,
            QtCore.Qt.Key_Delete,
        ):
            self._clear_full_selection()
        super().keyPressEvent(event)

    def _has_full_selection(self):
        cursor = self.textCursor()
        return cursor.hasSelection() and cursor.selectionStart() == 0 and cursor.selectionEnd() == len(
            self.toPlainText()
        )

    def _clear_full_selection(self):
        if not self._has_full_selection():
            return
        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(cursor)


class AIPanel(QtWidgets.QDockWidget):
    """Phase 4 dock widget for local or cloud generation and repair."""

    def __init__(self, parent=None):
        super().__init__("FreeCADAI", parent)
        self.setObjectName(PANEL_OBJECT_NAME)
        self.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.config = load_config()
        self.generated_payload = None
        self.last_failed_script = ""
        self.last_error = ""
        self.cloud_templates = {}
        self.current_cloud_task_id = None
        self.cancel_cloud_task_requested = False
        self._task_thread = None
        self._task_worker = None
        self._task_success_handler = None
        self._task_error_handler = None
        self._running_button = None
        self._running_button_text = ""
        self._running_button_style = ""
        self._spinner_index = 0
        self._spinner_frames = ("|", "/", "-", "\\")
        self._spinner_timer = QtCore.QTimer(self)
        self._spinner_timer.setInterval(180)
        self._spinner_timer.timeout.connect(self._update_running_button)
        self.setWidget(self._build_body())
        self._refresh_history()

    def _build_body(self):
        body = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(body)

        title = QtWidgets.QLabel("AI 智能工作台")
        title.setStyleSheet("font-weight: 600; font-size: 15px;")
        root.addWidget(title)

        description = QtWidgets.QLabel(
            "支持本地直连或企业云端生成脚本、自动校验、自动修复，并在当前 FreeCAD 文档中执行。"
        )
        description.setWordWrap(True)
        root.addWidget(description)

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_generate_tab(), "生成")
        tabs.addTab(self._build_settings_tab(), "设置")
        tabs.addTab(self._build_history_tab(), "历史")
        root.addWidget(tabs)
        return body

    def _section_title(self, text):
        label = QtWidgets.QLabel(text)
        label.setStyleSheet("font-weight: 600; margin-top: 6px;")
        return label

    def _section_group(self, title):
        group = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._section_title(title))
        return group, layout

    def _build_generate_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        layout.addWidget(self._section_title("建模需求输入"))
        template_row = QtWidgets.QHBoxLayout()
        template_row.addWidget(QtWidgets.QLabel("常用模板"))
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.addItem("请选择模板")
        self.template_combo.addItems(template_names())
        template_row.addWidget(self.template_combo)

        self.apply_template_button = QtWidgets.QPushButton("套用模板")
        self.apply_template_button.clicked.connect(self._apply_template)
        template_row.addWidget(self.apply_template_button)

        self.sync_templates_button = QtWidgets.QPushButton("同步云端模板")
        self.sync_templates_button.clicked.connect(self._sync_cloud_templates)
        template_row.addWidget(self.sync_templates_button)
        layout.addLayout(template_row)

        mode_row = QtWidgets.QHBoxLayout()
        mode_row.addWidget(QtWidgets.QLabel("建模模式"))
        self.modeling_mode_combo = QtWidgets.QComboBox()
        self.modeling_mode_combo.addItem("三维实体", "3d_solid")
        self.modeling_mode_combo.addItem("二维草图", "2d_sketch")
        mode_row.addWidget(self.modeling_mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.prompt_box = PromptTextEdit()
        self.prompt_box.setPlaceholderText("描述你想创建或修改的 FreeCAD 模型。")
        self.prompt_box.setPlainText("创建一个 100 x 60 x 10 mm 的底板，并在四角添加直径 8 mm 的安装孔。")
        self.prompt_box.moveCursor(QtGui.QTextCursor.End)
        self.prompt_box.setFixedHeight(64)
        layout.addWidget(self.prompt_box)

        layout.addWidget(self._section_title("生成与执行操作"))
        action_row = QtWidgets.QHBoxLayout()
        self.generate_button = QtWidgets.QPushButton("调用 LLM 生成脚本")
        self.generate_button.setMinimumWidth(140)
        self.generate_button.clicked.connect(self._generate_script)
        action_row.addWidget(self.generate_button)

        self.cancel_task_button = QtWidgets.QPushButton("取消云端任务")
        self.cancel_task_button.setMinimumWidth(120)
        self.cancel_task_button.clicked.connect(self._cancel_cloud_task)
        self.cancel_task_button.setEnabled(False)
        action_row.addWidget(self.cancel_task_button)

        self.execute_button = QtWidgets.QPushButton("执行脚本")
        self.execute_button.setMinimumWidth(96)
        self.execute_button.clicked.connect(self._execute_script)
        action_row.addWidget(self.execute_button)

        self.repair_button = QtWidgets.QPushButton("调用 LLM 修复脚本")
        self.repair_button.setMinimumWidth(140)
        self.repair_button.clicked.connect(self._repair_script)
        self.repair_button.setEnabled(False)
        action_row.addWidget(self.repair_button)
        layout.addLayout(action_row)

        repair_row = QtWidgets.QHBoxLayout()
        self.auto_repair_checkbox = QtWidgets.QCheckBox("执行失败时自动修复")
        self.auto_repair_checkbox.setChecked(True)
        repair_row.addWidget(self.auto_repair_checkbox)

        repair_row.addWidget(QtWidgets.QLabel("最多修复次数"))
        self.max_repair_spin = QtWidgets.QSpinBox()
        self.max_repair_spin.setRange(0, 3)
        self.max_repair_spin.setValue(2)
        repair_row.addWidget(self.max_repair_spin)
        repair_row.addStretch(1)
        layout.addLayout(repair_row)

        fallback_row = QtWidgets.QHBoxLayout()
        self.context_button = QtWidgets.QPushButton("查看当前上下文")
        self.context_button.clicked.connect(self._show_context)
        fallback_row.addWidget(self.context_button)

        self.local_script_button = QtWidgets.QPushButton("本地示例脚本")
        self.local_script_button.clicked.connect(self._generate_local_example_script)
        fallback_row.addWidget(self.local_script_button)
        layout.addLayout(fallback_row)

        layout.addWidget(self._section_title("生成结果摘要"))
        self.summary_box = QtWidgets.QPlainTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumHeight(150)
        self.summary_box.setPlaceholderText("LLM 返回摘要、参数和说明会显示在这里。")
        layout.addWidget(self.summary_box)

        layout.addWidget(self._section_title("参数 JSON 编辑"))
        self.parameters_box = QtWidgets.QPlainTextEdit()
        self.parameters_box.setPlaceholderText("LLM 返回的 parameters 会显示在这里。修改后可点击“按参数重新生成”。")
        self.parameters_box.setFixedHeight(86)
        layout.addWidget(self.parameters_box)

        param_row = QtWidgets.QHBoxLayout()
        self.regenerate_params_button = QtWidgets.QPushButton("按参数重新生成")
        self.regenerate_params_button.clicked.connect(self._regenerate_with_parameters)
        param_row.addWidget(self.regenerate_params_button)
        param_row.addStretch(1)
        layout.addLayout(param_row)

        layout.addWidget(self._section_title("脚本预览与编辑"))
        self.script_box = QtWidgets.QPlainTextEdit()
        self.script_box.setPlaceholderText("生成的 FreeCAD Python 脚本会显示在这里。也可以手动粘贴脚本后校验/执行。")
        self.script_box.setMinimumHeight(220)
        layout.addWidget(self.script_box)

        layout.addWidget(self._section_title("执行状态与错误信息"))
        self.status = QtWidgets.QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setMaximumHeight(140)
        self.status.setPlainText("就绪：填写需求后可以调用 LLM；没有 API 时，也可以先用“本地示例脚本”试试流程。")
        layout.addWidget(self.status)
        return tab

    def _build_settings_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        layout.addWidget(self._section_title("服务模式"))
        mode_form = QtWidgets.QFormLayout()
        self.service_mode_combo = QtWidgets.QComboBox()
        self.service_mode_combo.addItem("本地直连 LLM", "local")
        self.service_mode_combo.addItem("企业云端服务", "cloud")
        current_mode = self.config.get("service_mode", "local")
        index = self.service_mode_combo.findData(current_mode)
        if index >= 0:
            self.service_mode_combo.setCurrentIndex(index)
        self.service_mode_combo.currentIndexChanged.connect(self._update_service_mode_settings_visibility)
        mode_form.addRow("服务模式", self.service_mode_combo)
        layout.addLayout(mode_form)

        self.local_settings_group, local_layout = self._section_group("本地 LLM API 连接设置")
        form = QtWidgets.QFormLayout()
        self.base_url_input = QtWidgets.QLineEdit(self.config.get("base_url", ""))
        self.api_key_input = QtWidgets.QLineEdit(self.config.get("api_key", ""))
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.model_input = QtWidgets.QLineEdit(self.config.get("model", ""))
        self.temperature_input = QtWidgets.QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(float(self.config.get("temperature", 0.1)))

        form.addRow("Base URL（必填）", self.base_url_input)
        form.addRow("API Key（必填）", self.api_key_input)
        form.addRow("Model（必填）", self.model_input)
        form.addRow("Temperature（必填）", self.temperature_input)
        local_layout.addLayout(form)
        layout.addWidget(self.local_settings_group)

        self.cloud_settings_group, cloud_layout = self._section_group("企业云端连接")
        cloud_form = QtWidgets.QFormLayout()
        self.cloud_base_url_input = QtWidgets.QLineEdit(self.config.get("cloud_base_url", ""))
        self._cloud_api_key_value = self.config.get("cloud_api_key", "")
        self.cloud_api_key_input = QtWidgets.QLineEdit(self._mask_secret(self._cloud_api_key_value))
        self.cloud_api_key_input.setPlaceholderText("在企业平台 API Key 页面创建后粘贴完整 Key")
        self.cloud_project_id_input = QtWidgets.QLineEdit(self.config.get("cloud_project_id", ""))
        self.cloud_sync_history_checkbox = QtWidgets.QCheckBox("执行后回传结果和模型信息")
        self.cloud_sync_history_checkbox.setChecked(bool(self.config.get("cloud_sync_history", True)))
        cloud_form.addRow("服务地址（必填）", self.cloud_base_url_input)
        cloud_form.addRow("插件 API Key（平台创建后粘贴）", self.cloud_api_key_input)
        cloud_form.addRow("项目名称（选填）", self.cloud_project_id_input)
        cloud_form.addRow("结果回传", self.cloud_sync_history_checkbox)
        cloud_layout.addLayout(cloud_form)

        cloud_layout.addWidget(self._section_title("企业账号与工作区"))
        account_form = QtWidgets.QFormLayout()
        self.cloud_account_username_input = QtWidgets.QLineEdit(self.config.get("cloud_account_username", ""))
        self.cloud_account_password_input = QtWidgets.QLineEdit("")
        self.cloud_account_password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.cloud_workspace_combo = QtWidgets.QComboBox()
        saved_workspace_id = str(self.config.get("cloud_workspace_id", "") or "")
        saved_workspace_name = self.config.get("cloud_workspace_name", "")
        self.cloud_workspace_map = {}
        if saved_workspace_id:
            self.cloud_workspace_map[saved_workspace_id] = {
                "id": saved_workspace_id,
                "name": saved_workspace_name,
                "plan": self.config.get("cloud_workspace_plan", ""),
                "status": self.config.get("cloud_workspace_status", ""),
            }
            self.cloud_workspace_combo.addItem(
                "{} - {}".format(saved_workspace_id, saved_workspace_name or "已保存工作区"),
                saved_workspace_id,
            )
        account_form.addRow("企业邮箱（必填）", self.cloud_account_username_input)
        account_form.addRow("登录密码（必填）", self.cloud_account_password_input)
        account_form.addRow("工作区（必选）", self.cloud_workspace_combo)
        cloud_layout.addLayout(account_form)

        account_row = QtWidgets.QHBoxLayout()
        self.cloud_login_button = QtWidgets.QPushButton("登录企业账号")
        self.cloud_login_button.setToolTip("使用企业平台账号登录，读取可访问的工作区。")
        self.cloud_login_button.clicked.connect(self._cloud_account_login)
        account_row.addWidget(self.cloud_login_button)

        self.cloud_refresh_workspaces_button = QtWidgets.QPushButton("刷新工作区")
        self.cloud_refresh_workspaces_button.setToolTip("登录成功后读取当前账号可用的工作区。")
        self.cloud_refresh_workspaces_button.clicked.connect(self._cloud_refresh_workspaces)
        account_row.addWidget(self.cloud_refresh_workspaces_button)

        self.cloud_bind_workspace_button = QtWidgets.QPushButton("保存工作区")
        self.cloud_bind_workspace_button.setToolTip("保存当前选择的企业工作区。API Key 请在企业平台创建后粘贴。")
        self.cloud_bind_workspace_button.clicked.connect(self._cloud_save_selected_workspace)
        account_row.addWidget(self.cloud_bind_workspace_button)

        self.cloud_verify_button = QtWidgets.QPushButton("检查连接")
        self.cloud_verify_button.setToolTip("验证当前服务地址和插件 API Key 是否可用。")
        self.cloud_verify_button.clicked.connect(self._cloud_verify_connection)
        account_row.addWidget(self.cloud_verify_button)
        cloud_layout.addLayout(account_row)

        self.cloud_operation_message_label = QtWidgets.QLabel("")
        self.cloud_operation_message_label.setWordWrap(True)
        self.cloud_operation_message_label.setMaximumHeight(44)
        self.cloud_operation_message_label.setStyleSheet("color: #555;")
        cloud_layout.addWidget(self.cloud_operation_message_label)

        self.cloud_binding_status_label = QtWidgets.QLabel("")
        self.cloud_binding_status_label.setWordWrap(True)
        cloud_layout.addWidget(self.cloud_binding_status_label)
        self._update_cloud_binding_status()
        layout.addWidget(self.cloud_settings_group)

        self.save_settings_button = QtWidgets.QPushButton("保存设置")
        self.save_settings_button.clicked.connect(self._save_settings)
        layout.addWidget(self.save_settings_button)

        layout.addWidget(self._section_title("使用说明"))
        note = QtWidgets.QLabel(
            "本地直连 LLM：选择该模式后填写 Base URL、API Key、Model、Temperature，保存后生成会直接调用本地配置的模型服务。\n"
            "企业云端：填写服务地址后，登录企业账号刷新工作区并保存；然后到企业平台 API Key 页面创建带过期时间和权限范围的插件 Key，粘贴到这里后检查连接。\n"
            "项目名称为选填，用于云端任务归类和后续检索。已保存的插件 API Key 仅显示前后几位，中间会自动隐藏。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self._update_service_mode_settings_visibility()
        return tab

    def _build_history_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.addWidget(self._section_title("生成与执行历史记录"))
        self.history_box = QtWidgets.QPlainTextEdit()
        self.history_box.setReadOnly(True)
        layout.addWidget(self.history_box)

        refresh_button = QtWidgets.QPushButton("刷新历史")
        refresh_button.clicked.connect(self._refresh_history)
        layout.addWidget(refresh_button)
        return tab

    def _current_settings(self):
        return {
            "service_mode": self._selected_service_mode(),
            "base_url": self.base_url_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
            "model": self.model_input.text().strip(),
            "temperature": self.temperature_input.value(),
            "cloud_base_url": self.cloud_base_url_input.text().strip(),
            "cloud_api_key": self._cloud_api_key_from_input(),
            "cloud_project_id": self.cloud_project_id_input.text().strip(),
            "cloud_sync_history": self.cloud_sync_history_checkbox.isChecked(),
            "cloud_account_token": self.config.get("cloud_account_token", ""),
            "cloud_account_username": self.cloud_account_username_input.text().strip(),
            "cloud_workspace_id": str(self.cloud_workspace_combo.currentData() or self.config.get("cloud_workspace_id", "")),
            "cloud_workspace_name": self.config.get("cloud_workspace_name", ""),
            "cloud_workspace_plan": self.config.get("cloud_workspace_plan", ""),
            "cloud_workspace_status": self.config.get("cloud_workspace_status", ""),
            "cloud_key_status": self.config.get("cloud_key_status", ""),
        }

    def _save_settings(self):
        self.config = save_config(self._current_settings())
        self._cloud_api_key_value = self.config.get("cloud_api_key", "")
        self._refresh_cloud_api_key_display()
        self._update_cloud_binding_status()
        self._update_service_mode_settings_visibility()
        mode_name = "企业云端服务" if self._using_cloud() else "本地直连 LLM"
        self._set_status("设置已保存。下一次生成会使用：{}。".format(mode_name))

    def _update_service_mode_settings_visibility(self):
        if not hasattr(self, "local_settings_group") or not hasattr(self, "cloud_settings_group"):
            return
        using_cloud = (self.service_mode_combo.currentData() or "local") == "cloud"
        self.local_settings_group.setVisible(not using_cloud)
        self.cloud_settings_group.setVisible(using_cloud)

    def _selected_cloud_workspace_id(self):
        if not hasattr(self, "cloud_workspace_combo"):
            return str(self.config.get("cloud_workspace_id", "") or "")
        return str(self.cloud_workspace_combo.currentData() or self.config.get("cloud_workspace_id", "") or "")

    def _select_cloud_workspace(self, workspace_id):
        if not hasattr(self, "cloud_workspace_combo"):
            return
        workspace_id = str(workspace_id or "")
        if not workspace_id:
            return
        index = self.cloud_workspace_combo.findData(workspace_id)
        if index >= 0:
            self.cloud_workspace_combo.setCurrentIndex(index)

    def _mask_secret(self, secret):
        secret = str(secret or "").strip()
        if not secret:
            return ""
        if len(secret) <= 10:
            return "{}{}".format(secret[:2], "*" * max(4, len(secret) - 2))
        prefix_len = min(8, max(4, len(secret) // 5))
        suffix_len = min(6, max(4, len(secret) // 6))
        hidden_len = max(6, len(secret) - prefix_len - suffix_len)
        return "{}{}{}".format(secret[:prefix_len], "*" * hidden_len, secret[-suffix_len:])

    def _cloud_api_key_from_input(self):
        if not hasattr(self, "cloud_api_key_input"):
            return self.config.get("cloud_api_key", "")
        text = self.cloud_api_key_input.text().strip()
        current = getattr(self, "_cloud_api_key_value", self.config.get("cloud_api_key", ""))
        if not text:
            return ""
        if current and ("*" in text or text == self._mask_secret(current)):
            return current
        return text

    def _refresh_cloud_api_key_display(self):
        if not hasattr(self, "cloud_api_key_input"):
            return
        current = getattr(self, "_cloud_api_key_value", self.config.get("cloud_api_key", ""))
        self.cloud_api_key_input.setText(self._mask_secret(current))

    def _cloud_plan_label(self, plan):
        labels = {
            "free": "免费版",
            "pro": "专业版",
            "team": "团队版",
            "enterprise": "企业版",
        }
        return labels.get(str(plan or "").lower(), plan or "未知")

    def _cloud_status_label(self, status):
        labels = {
            "active": "正常",
            "disabled": "已停用",
            "suspended": "已暂停",
            "expired": "已过期",
            "revoked": "已撤销",
        }
        return labels.get(str(status or "").lower(), status or "未知")

    def _workspace_label(self, workspace):
        parts = [str(workspace.get("id", "")), workspace.get("name", "")]
        detail = []
        if workspace.get("plan"):
            detail.append(self._cloud_plan_label(workspace.get("plan")))
        if workspace.get("status"):
            detail.append(self._cloud_status_label(workspace.get("status")))
        label = " - ".join([part for part in parts if part])
        if detail:
            label = "{} ({})".format(label, " / ".join(detail))
        return label or "未命名工作区"

    def _remember_cloud_workspace(self, workspace):
        workspace = workspace or {}
        if not workspace:
            return
        workspace_id = str(workspace.get("id", "") or "")
        if workspace_id:
            self.config["cloud_workspace_id"] = workspace_id
        self.config["cloud_workspace_name"] = workspace.get("name", "") or ""
        self.config["cloud_workspace_plan"] = workspace.get("plan", "") or ""
        self.config["cloud_workspace_status"] = workspace.get("status", "") or ""
        if workspace_id:
            self._select_cloud_workspace(workspace_id)

    def _update_cloud_binding_status(self):
        if not hasattr(self, "cloud_binding_status_label"):
            return
        username = self.config.get("cloud_account_username", "") or self.cloud_account_username_input.text().strip()
        workspace_id = self.config.get("cloud_workspace_id", "")
        workspace_name = self.config.get("cloud_workspace_name", "")
        workspace_plan = self.config.get("cloud_workspace_plan", "")
        workspace_status = self.config.get("cloud_workspace_status", "")
        key_status = self.config.get("cloud_key_status", "")
        api_key_status = "已配置" if self._cloud_api_key_from_input() else "未配置"
        account_status = "已登录：{}".format(username) if self.config.get("cloud_account_token") else "未登录企业账号"
        workspace_status_text = "未保存工作区"
        if workspace_id:
            workspace_status_text = "{} {}".format(workspace_id, workspace_name or "").strip()
        lines = [
            "企业账号：{}".format(account_status),
            "当前工作区：{}".format(workspace_status_text),
            "工作区套餐：{}，状态：{}".format(self._cloud_plan_label(workspace_plan), self._cloud_status_label(workspace_status)),
            "插件 API Key：{}，Key 状态：{}".format(api_key_status, self._cloud_status_label(key_status)),
        ]
        self.cloud_binding_status_label.setText("\n".join(lines))

    def _set_cloud_operation_message(self, text):
        if hasattr(self, "cloud_operation_message_label"):
            self.cloud_operation_message_label.setText(text)
            self.cloud_operation_message_label.setToolTip(text)
        self._set_status(text)

    def _cloud_account_login(self):
        username = self.cloud_account_username_input.text().strip()
        password = self.cloud_account_password_input.text()
        if not username or not password:
            self._set_cloud_operation_message("请填写企业邮箱和登录密码。")
            return
        self._save_settings()

        def on_success(payload):
            self.config["cloud_account_token"] = payload.get("token", "")
            self.config["cloud_account_username"] = username
            self.config = save_config(self.config)
            self.cloud_account_password_input.clear()
            self._update_cloud_binding_status()
            self._set_cloud_operation_message("企业账号登录成功。请刷新工作区列表，然后选择要连接的工作区。")

        self._set_cloud_operation_message("正在登录企业账号，请稍候...")
        self._start_background_task(
            "企业账号登录",
            "正在登录企业账号，请稍候...",
            lambda: self._build_cloud_client().account_login(username, password),
            on_success,
            lambda error: self._set_cloud_operation_message(format_cloud_error(error)),
            button=self.cloud_login_button,
        )

    def _cloud_refresh_workspaces(self):
        self._save_settings()
        token = self.config.get("cloud_account_token", "")
        if not token:
            self._set_cloud_operation_message("请先登录企业账号，登录成功后再刷新工作区。")
            return

        def on_success(payload):
            workspaces = payload.get("workspaces", [])
            current_id = self._selected_cloud_workspace_id()
            self.cloud_workspace_combo.clear()
            self.cloud_workspace_map = {}
            for workspace in workspaces:
                workspace_id = str(workspace.get("id", ""))
                self.cloud_workspace_map[workspace_id] = workspace
                self.cloud_workspace_combo.addItem(self._workspace_label(workspace), workspace_id)
            self._select_cloud_workspace(current_id)
            if not current_id and workspaces:
                self.cloud_workspace_combo.setCurrentIndex(0)
            self._update_cloud_binding_status()
            self._set_cloud_operation_message("工作区列表已刷新，共找到 {} 个工作区。请选择工作区并保存，然后粘贴企业平台创建的插件 API Key。".format(len(workspaces)))

        self._set_cloud_operation_message("正在从云端读取可用工作区...")
        self._start_background_task(
            "刷新工作区",
            "正在从云端读取可用工作区...",
            lambda: self._build_cloud_client().account_workspaces(token),
            on_success,
            lambda error: self._set_cloud_operation_message(format_cloud_error(error)),
            button=self.cloud_refresh_workspaces_button,
        )

    def _cloud_save_selected_workspace(self):
        self._save_settings()
        token = self.config.get("cloud_account_token", "")
        workspace_id = self._selected_cloud_workspace_id()
        if not token:
            self._set_cloud_operation_message("请先登录企业账号，登录成功后再保存工作区。")
            return
        if not workspace_id:
            self._set_cloud_operation_message("请先在“工作区”下拉框中选择一个工作区。")
            return
        workspace = getattr(self, "cloud_workspace_map", {}).get(workspace_id)
        if not workspace:
            workspace = {
                "id": workspace_id,
                "name": self.config.get("cloud_workspace_name", ""),
                "plan": self.config.get("cloud_workspace_plan", ""),
                "status": self.config.get("cloud_workspace_status", ""),
            }
        self._remember_cloud_workspace(workspace)
        cloud_index = self.service_mode_combo.findData("cloud")
        if cloud_index >= 0:
            self.service_mode_combo.setCurrentIndex(cloud_index)
        self.config = save_config(self._current_settings())
        self._cloud_api_key_value = self.config.get("cloud_api_key", "")
        self._refresh_cloud_api_key_display()
        self._update_cloud_binding_status()
        self._set_cloud_operation_message("工作区已保存。请在企业平台创建插件 API Key 后粘贴到这里，并点击“检查连接”。")

    def _cloud_verify_connection(self):
        self._save_settings()
        if not self.config.get("cloud_api_key", ""):
            self._set_cloud_operation_message("请先在企业平台 API Key 页面创建插件 Key，并粘贴到这里后再检查连接。")
            return

        def on_success(payload):
            workspace = {
                "id": payload.get("workspace_id", ""),
                "name": payload.get("workspace_name", ""),
                "plan": payload.get("workspace_plan", ""),
                "status": payload.get("workspace_status", ""),
            }
            self.config["cloud_key_status"] = payload.get("key_status", "")
            self._remember_cloud_workspace(workspace)
            self.config = save_config(self._current_settings())
            self._update_cloud_binding_status()
            self._set_cloud_operation_message("企业云端连接正常：当前工作区为 {}。".format(self.config.get("cloud_workspace_name") or self.config.get("cloud_workspace_id")))

        self._set_cloud_operation_message("正在检查云端连接和 API Key 状态...")
        self._start_background_task(
            "检查云端连接",
            "正在检查云端连接和 API Key 状态...",
            lambda: self._build_cloud_client().verify(),
            on_success,
            lambda error: self._set_cloud_operation_message(format_cloud_error(error)),
            button=self.cloud_verify_button,
        )

    def _set_busy(self, busy):
        for button in (
            self.generate_button,
            self.execute_button,
            self.repair_button,
            self.local_script_button,
            self.context_button,
            self.regenerate_params_button,
            self.apply_template_button,
            self.sync_templates_button,
        ):
            if button is self._running_button:
                button.setEnabled(True)
                continue
            if button is self.repair_button:
                button.setEnabled((not busy) and bool(self.last_failed_script and self.last_error))
            else:
                button.setEnabled(not busy)
        for optional in (
            "cloud_login_button",
            "cloud_refresh_workspaces_button",
            "cloud_bind_workspace_button",
            "cloud_verify_button",
            "save_settings_button",
        ):
            button = getattr(self, optional, None)
            if button is not None:
                button.setEnabled(not busy)

    def _start_button_spinner(self, button):
        if button is None:
            return
        self._stop_button_spinner()
        self._running_button = button
        self._running_button_text = button.text()
        self._running_button_style = button.styleSheet()
        button.setMinimumWidth(max(button.minimumWidth(), button.sizeHint().width() + 18))
        button.setStyleSheet(
            "QPushButton { background-color: #16734a; color: white; border: 1px solid #0f5b39; font-weight: 600; }"
            "QPushButton:hover { background-color: #1f8a59; }"
            "QPushButton:pressed { background-color: #0f5b39; }"
        )
        button.setEnabled(True)
        self._spinner_index = 0
        QtWidgets.QApplication.processEvents()
        self._spinner_timer.start()

    def _update_running_button(self):
        if self._running_button is None:
            self._spinner_timer.stop()
            return
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)

    def _stop_button_spinner(self):
        if self._spinner_timer.isActive():
            self._spinner_timer.stop()
        if self._running_button is not None:
            self._running_button.setText(self._running_button_text)
            self._running_button.setStyleSheet(self._running_button_style)
        self._running_button = None
        self._running_button_text = ""
        self._running_button_style = ""
        QtWidgets.QApplication.processEvents()

    def _start_background_task(self, name, message, callback, on_success, on_error=None, button=None):
        if self._task_thread is not None:
            self._set_status("已有任务正在运行，请等它完成后再开始新的任务。")
            return
        self.cancel_cloud_task_requested = False
        self.current_cloud_task_id = None
        if hasattr(self, "cancel_task_button"):
            self.cancel_task_button.setEnabled(False)
        self._start_button_spinner(button)
        self._task_success_handler = on_success
        self._task_error_handler = on_error
        self._task_thread = QtCore.QThread(self)
        self._task_worker = BackgroundTask(name, callback)
        self._task_worker.moveToThread(self._task_thread)
        self._task_thread.started.connect(self._task_worker.run)
        self._task_worker.finished.connect(self._on_background_task_finished)
        self._task_worker.failed.connect(self._on_background_task_failed)
        self._task_worker.finished.connect(self._task_thread.quit)
        self._task_worker.failed.connect(self._task_thread.quit)
        self._task_thread.finished.connect(self._cleanup_background_task)
        self._set_busy(True)
        self._set_status(message)
        self._task_thread.start()

    def _cleanup_background_task(self):
        if self._task_worker is not None:
            self._task_worker.deleteLater()
        if self._task_thread is not None:
            self._task_thread.deleteLater()
        self._task_worker = None
        self._task_thread = None
        self._task_success_handler = None
        self._task_error_handler = None
        self._stop_button_spinner()
        self._set_busy(False)
        self.current_cloud_task_id = None
        self.cancel_cloud_task_requested = False
        if hasattr(self, "cancel_task_button"):
            self.cancel_task_button.setEnabled(False)

    def _on_background_task_finished(self, name, result):
        if self._task_success_handler is not None:
            self._task_success_handler(result)

    def _on_background_task_failed(self, name, error):
        if self._task_error_handler is not None:
            self._task_error_handler(error)
        else:
            self._set_status("{} 失败：\n{}".format(name, error))

    def _set_status(self, text):
        self.status.setPlainText(text)
        QtWidgets.QApplication.processEvents()

    def _clear_generation_outputs(self, message):
        self.generated_payload = None
        self.last_failed_script = ""
        self.last_error = ""
        self.summary_box.clear()
        self.parameters_box.clear()
        self.script_box.clear()
        self.repair_button.setEnabled(False)
        self._set_status(message)

    def _apply_template(self):
        name = self.template_combo.currentText()
        prompt = self.cloud_templates.get(name, "") or get_template_prompt(name)
        if not prompt:
            self._set_status("请选择一个模板。")
            return
        self.prompt_box.setPlainText(prompt)
        self.prompt_box.moveCursor(QtGui.QTextCursor.End)
        if name.startswith("二维草图"):
            self.modeling_mode_combo.setCurrentIndex(1)
        self._set_status("已套用模板：{}。可以直接生成，也可以继续修改需求。".format(name))

    def _sync_cloud_templates(self):
        self._save_settings()
        if not self._using_cloud():
            self._set_status("请先在设置中选择“企业云端服务”，再同步企业模板。")
            return

        def success(payload):
            templates = payload.get("templates", []) if isinstance(payload, dict) else []
            if not templates:
                self._set_status("云端没有返回可用模板。")
                return
            self.cloud_templates = {
                item.get("name", ""): item.get("prompt", "")
                for item in templates
                if item.get("name") and item.get("prompt")
            }
            current_names = {self.template_combo.itemText(i) for i in range(self.template_combo.count())}
            for name in sorted(self.cloud_templates):
                if name not in current_names:
                    self.template_combo.addItem(name)
            self._set_status("云端模板同步完成：已加载 {} 个模板。".format(len(self.cloud_templates)))

        def failed(error):
            self._set_status("云端模板同步失败：\n{}".format(self._format_request_error(error)))

        self._start_background_task(
            "同步云端模板",
            "正在后台拉取云端模板库，FreeCAD 界面可以继续操作。",
            lambda: self._build_cloud_client().templates(),
            success,
            failed,
            button=self.sync_templates_button,
        )

    def _modeling_mode(self):
        return self.modeling_mode_combo.currentData() or "3d_solid"

    def _selected_service_mode(self):
        if hasattr(self, "service_mode_combo"):
            data = self.service_mode_combo.currentData()
            if data in ("local", "cloud"):
                return data
            text = self.service_mode_combo.currentText().strip().lower()
            if "云端" in text or "cloud" in text or "saas" in text:
                return "cloud"
            if "本地" in text or "local" in text:
                return "local"
        return self.config.get("service_mode", "local")

    def _using_cloud(self):
        return self._selected_service_mode() == "cloud" or self.config.get("service_mode", "local") == "cloud"

    def _validate_generation_settings(self):
        if self._using_cloud():
            if not self.config.get("cloud_base_url", ""):
                self._set_status("企业云端服务地址不能为空。请在“设置”页填写服务地址后再生成。")
                return False
            if not self.config.get("cloud_api_key", ""):
                self._set_status("插件 API Key 不能为空。请先在企业平台创建 API Key，粘贴到“设置”页并检查连接。")
                return False
            return True
        if not self.config.get("base_url", ""):
            self._set_status("本地直连 LLM 的 Base URL 不能为空。请在“设置”页填写后再生成。")
            return False
        if not self.config.get("api_key", ""):
            self._set_status("本地直连 LLM 的 API Key 不能为空。当前如果要使用企业云端，请先在“设置”页选择“企业云端服务”。")
            return False
        if not self.config.get("model", ""):
            self._set_status("本地直连 LLM 的 Model 不能为空。请在“设置”页填写后再生成。")
            return False
        return True


    def _provider_label(self):
        if self._using_cloud():
            return "cloud:{}".format(self.config.get("cloud_base_url", ""))
        return self.config.get("model", "")

    def _format_request_error(self, error):
        formatter = format_cloud_error if self._using_cloud() else format_llm_error
        return formatter(Exception(error))

    def _show_context(self):
        self._set_status("正在读取当前 FreeCAD 文档和选中对象信息...")
        try:
            self._set_status("当前上下文：\n{}".format(collect_context()))
        except Exception:
            self._set_status("读取上下文失败：\n{}".format(traceback.format_exc()))

    def _generate_script(self):
        if self._task_thread is not None:
            self._set_status("已有任务正在运行，请等待完成，或在云端任务提交后点击取消云端任务。")
            return
        prompt = self.prompt_box.toPlainText().strip()
        if not prompt:
            self.status.setPlainText("请输入建模需求。")
            return

        self._save_settings()
        if not self._validate_generation_settings():
            return
        self._clear_generation_outputs("已清空旧结果。正在整理需求、读取当前模型上下文，并准备调用 LLM...")
        try:
            context = collect_context()
        except Exception:
            self._set_status("读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_generate(prompt, context)
            task_message = "上下文已读取，正在后台请求企业云端生成 FreeCAD Python 脚本；界面可以继续操作。"
        else:
            messages = build_generation_messages(prompt, context, self._modeling_mode())
            request_callback = lambda: self._request_payload(messages)
            task_message = "上下文已读取，正在后台请求 LLM 生成 FreeCAD Python 脚本；界面不会再卡住。"

        def success(payload):
            self._set_status("LLM 已返回脚本，已自动完成基础安全校验，正在更新预览窗口...")
            self.generated_payload = payload
            self.last_failed_script = ""
            self.last_error = ""
            self._show_payload(payload)
            append_history(
                {
                    "prompt": prompt,
                    "summary": payload.get("summary", ""),
                    "parameters": payload.get("parameters", {}),
                    "expected_objects": payload.get("expected_objects", []),
                    "model": self._provider_label(),
                    "status": "generated",
                    "task_id": payload.get("task_id", ""),
                }
            )
            self._refresh_history()
            self._set_status("生成完成：脚本已自动校验通过。你可以检查参数和脚本，然后点击“执行脚本”。")

        def failed(error):
            self._set_status("生成失败：\n{}".format(self._format_request_error(error)))

        self._start_background_task(
            "LLM 生成脚本",
            task_message,
            request_callback,
            success,
            failed,
            button=self.generate_button,
        )

    def _generate_local_example_script(self):
        prompt = self.prompt_box.toPlainText().strip()
        self._clear_generation_outputs("正在准备本地示例脚本，不会调用 LLM API...")
        try:
            payload = build_local_example_payload(prompt)
            validate_script(payload["script"])
            self.generated_payload = payload
            self.last_failed_script = ""
            self.last_error = ""
            self._show_payload(payload)
            append_history(
                {
                    "prompt": prompt,
                    "summary": payload.get("summary", ""),
                    "parameters": payload.get("parameters", {}),
                    "expected_objects": payload.get("expected_objects", []),
                    "model": "local-example",
                    "status": "generated",
                }
            )
            self._refresh_history()
            self._set_status("本地示例脚本已准备好，并已自动校验通过。可以直接点击“执行脚本”。")
        except Exception:
            self._set_status("本地示例脚本生成失败：\n{}".format(traceback.format_exc()))

    def _format_payload_summary(self, payload):
        visible = {
            "summary": payload.get("summary", ""),
            "expected_objects": payload.get("expected_objects", []),
            "notes": payload.get("notes", []),
        }
        return json.dumps(visible, ensure_ascii=False, indent=2)

    def _show_payload(self, payload):
        self.script_box.setPlainText(payload["script"])
        self.summary_box.setPlainText(self._format_payload_summary(payload))
        self.parameters_box.setPlainText(
            json.dumps(payload.get("parameters", {}), ensure_ascii=False, indent=2)
        )

    def _build_client(self):
        return OpenAICompatibleClient(
            self.config["base_url"],
            self.config["api_key"],
            self.config["model"],
        )

    def _build_cloud_client(self):
        client = FreeCADAICloudClient(
            self.config.get("cloud_base_url", ""),
            self.config.get("cloud_api_key", ""),
            self.config.get("cloud_project_id", ""),
            self.config.get("cloud_account_token", ""),
        )
        client.on_task_submitted = self._on_cloud_task_submitted
        client.should_cancel = lambda: self.cancel_cloud_task_requested
        return client

    def _on_cloud_task_submitted(self, task_id):
        self.current_cloud_task_id = task_id
        if hasattr(self, "cancel_task_button"):
            self.cancel_task_button.setEnabled(True)
        self._set_status("云端任务已提交，Task ID：{}。正在轮询任务状态...".format(task_id))

    def _cancel_cloud_task(self):
        if not self.current_cloud_task_id:
            self._set_status("当前没有可取消的云端任务。")
            return
        self.cancel_cloud_task_requested = True
        try:
            self._build_cloud_client().cancel_task(self.current_cloud_task_id)
            self._set_status("已发送取消请求，Task ID：{}。".format(self.current_cloud_task_id))
        except Exception as exc:
            self._set_status("取消云端任务失败：\n{}".format(self._format_request_error(exc)))

    def _request_payload(self, messages):
        client = self._build_client()
        raw = client.chat(messages, temperature=self.config.get("temperature", 0.1))
        payload = parse_generation_response(raw)
        validate_script(payload["script"])
        return payload

    def _request_cloud_generate(self, prompt, context):
        payload = self._build_cloud_client().generate(prompt, context, self._modeling_mode())
        validate_script(payload["script"])
        return payload

    def _request_cloud_repair(self, prompt, context, failed_script, error):
        payload = self._build_cloud_client().repair(
            prompt,
            context,
            failed_script,
            error,
            self._modeling_mode(),
        )
        validate_script(payload["script"])
        return payload

    def _request_cloud_regenerate(self, prompt, context, parameters_text):
        payload = self._build_cloud_client().regenerate(
            prompt,
            context,
            parameters_text,
            self._modeling_mode(),
        )
        validate_script(payload["script"])
        return payload

    def _report_execution(self, status, execution_result, error_text):
        if not self._using_cloud() or not self.config.get("cloud_sync_history", True):
            return
        payload = self.generated_payload or {}
        task_id = payload.get("task_id")
        script_id = payload.get("script_id")
        if not task_id:
            return
        report = {
            "task_id": task_id,
            "script_id": script_id,
            "status": status,
            "plugin_version": "phase-4",
            "freecad_version": getattr(App, "Version", lambda: ["unknown"])(),
            "document_name": execution_result.get("document", ""),
            "object_count": execution_result.get("object_count", 0),
            "new_objects": execution_result.get("new_objects", []),
            "error_trace": error_text,
        }
        try:
            self._build_cloud_client().execution_report(report)
        except Exception as exc:
            App.Console.PrintWarning("FreeCADAI cloud execution report failed: {}\n".format(exc))

    def _execute_script(self):
        script = self.script_box.toPlainText().strip()
        if not script:
            self._set_status("还没有可执行脚本。请先生成脚本，或粘贴脚本到预览区。")
            return

        self._set_busy(True)
        self._start_button_spinner(self.execute_button)
        self._set_status("我先自动校验脚本；通过后会立即写入当前 FreeCAD 文档...")
        repair_attempts = self.max_repair_spin.value() if self.auto_repair_checkbox.isChecked() else 0
        current_script = script
        background_repair_started = False
        try:
            validate_script(current_script)
            view_label = "二维草图" if self._modeling_mode() == "2d_sketch" else "三维实体"
            self._set_status("脚本校验通过，正在执行并刷新{}视图...".format(view_label))
            execution_result = execute_script(current_script, self._modeling_mode())
            self.last_failed_script = ""
            self.last_error = ""
            self.repair_button.setEnabled(False)
            append_history(
                {
                    "prompt": self.prompt_box.toPlainText().strip(),
                    "summary": (self.generated_payload or {}).get("summary", "manual script"),
                    "model": self._provider_label(),
                    "status": "executed",
                }
            )
            self._refresh_history()
            self._report_execution("succeeded", execution_result, "")
            self._set_status(self._format_execution_success(execution_result))
        except Exception:
            error = traceback.format_exc()
            self.last_failed_script = current_script
            self.last_error = error
            self.repair_button.setEnabled(True)
            App.Console.PrintError(error)
            append_history(
                {
                    "prompt": self.prompt_box.toPlainText().strip(),
                    "summary": "execution failed",
                    "model": self._provider_label(),
                    "status": "failed",
                    "error": error,
                }
            )
            self._report_execution("failed", {}, error)
            if repair_attempts > 0:
                self._set_status("执行失败：错误信息已保留。正在后台生成修复脚本，FreeCAD 界面仍可操作...\n{}".format(error))
                self._stop_button_spinner()
                self._set_busy(False)
                background_repair_started = True
                self._start_auto_repair(current_script, error)
                return
            self._set_status("执行失败：错误信息已保留，可以点击“调用 LLM 修复脚本”。\n{}".format(error))
        finally:
            if not background_repair_started:
                self._stop_button_spinner()
                self._set_busy(False)

    def _start_auto_repair(self, failed_script, error):
        self._save_settings()
        if not self._validate_generation_settings():
            return
        try:
            prompt = self.prompt_box.toPlainText().strip()
            context = collect_context()
        except Exception:
            self._set_status("自动修复前读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_repair(prompt, context, failed_script, error)
            task_message = "正在后台请求企业云端生成修复脚本，FreeCAD 界面可以继续操作。"
        else:
            messages = build_repair_messages(prompt, context, failed_script, error, self._modeling_mode())
            request_callback = lambda: self._request_payload(messages)
            task_message = "正在后台生成修复脚本，FreeCAD 界面可以继续操作。"

        def success(payload):
            self.generated_payload = payload
            self._show_payload(payload)
            append_history(
                {
                    "prompt": self.prompt_box.toPlainText().strip(),
                    "summary": payload.get("summary", "自动修复脚本"),
                    "parameters": payload.get("parameters", {}),
                    "expected_objects": payload.get("expected_objects", []),
                    "model": self._provider_label(),
                    "status": "auto-repaired",
                    "attempt": 1,
                    "task_id": payload.get("task_id", ""),
                }
            )
            self._refresh_history()
            self._set_status("自动修复完成：修复脚本已放入预览区并通过基础安全校验。请检查后再次点击“执行脚本”。")

        def failed(error_text):
            self._set_status("自动修复失败：\n{}".format(self._format_request_error(error_text)))

        self._start_background_task(
            "自动修复脚本",
            task_message,
            request_callback,
            success,
            failed,
            button=self.repair_button,
        )

    def _format_execution_success(self, result):
        document = result.get("document", "")
        new_objects = result.get("new_objects", [])
        object_count = result.get("object_count", 0)
        if new_objects:
            return (
                "执行完成：已在文档 `{}` 中新增 {} 个对象：\n{}\n\n"
                "视图已刷新。如果仍看不到，请在模型树中确认这些对象是否可见。"
            ).format(document, len(new_objects), "\n".join("- " + name for name in new_objects))
        return (
            "执行完成：文档 `{}` 当前共有 {} 个对象，但没有检测到新增对象。\n\n"
            "这通常表示脚本修改了已有对象，或生成内容很小/位置较远。"
            "请查看模型树对象可见性，或点击“查看当前上下文”确认对象列表。"
        ).format(document, object_count)

    def _repair_script(self):
        if not self.last_failed_script or not self.last_error:
            self._set_status("现在没有可修复的失败脚本。请先执行脚本并产生错误。")
            return

        self._save_settings()
        if not self._validate_generation_settings():
            return
        failed_script = self.last_failed_script
        last_error = self.last_error
        try:
            prompt = self.prompt_box.toPlainText().strip()
            context = collect_context()
        except Exception:
            self._set_status("修复前读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_repair(prompt, context, failed_script, last_error)
            task_message = "正在后台请求企业云端修复失败脚本，FreeCAD 界面可以继续操作。"
        else:
            messages = build_repair_messages(prompt, context, failed_script, last_error, self._modeling_mode())
            request_callback = lambda: self._request_payload(messages)
            task_message = "正在后台把失败脚本和错误信息交给 LLM 修复，FreeCAD 界面可以继续操作。"

        def success(payload):
            self.generated_payload = payload
            self._set_status("LLM 已返回修复脚本，并已自动完成基础安全校验，正在更新预览...")
            self._show_payload(payload)
            append_history(
                {
                    "prompt": self.prompt_box.toPlainText().strip(),
                    "summary": payload.get("summary", "修复脚本"),
                    "parameters": payload.get("parameters", {}),
                    "expected_objects": payload.get("expected_objects", []),
                    "model": self._provider_label(),
                    "status": "repaired",
                    "task_id": payload.get("task_id", ""),
                }
            )
            self._refresh_history()
            self._set_status("修复完成：脚本已自动校验通过。检查无误后可以再次执行。")

        def failed(error):
            self._set_status("修复失败：\n{}".format(self._format_request_error(error)))

        self._start_background_task(
            "LLM 修复脚本",
            task_message,
            request_callback,
            success,
            failed,
            button=self.repair_button,
        )

    def _regenerate_with_parameters(self):
        prompt = self.prompt_box.toPlainText().strip()
        parameters_text = self.parameters_box.toPlainText().strip()
        if not prompt:
            self._set_status("请输入建模需求。")
            return
        if not parameters_text:
            self._set_status("参数 JSON 为空，无法按参数重新生成。")
            return
        try:
            json.loads(parameters_text)
        except json.JSONDecodeError as exc:
            self._set_status("参数 JSON 格式错误：\n{}".format(exc))
            return

        self._save_settings()
        if not self._validate_generation_settings():
            return
        self.summary_box.clear()
        self.script_box.clear()
        try:
            context = collect_context()
        except Exception:
            self._set_status("读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_regenerate(prompt, context, parameters_text)
            task_message = "已读取编辑后的参数，正在后台请求企业云端重新生成脚本。"
        else:
            messages = build_regeneration_with_parameters_messages(
                prompt,
                context,
                parameters_text,
                self._modeling_mode(),
            )
            request_callback = lambda: self._request_payload(messages)
            task_message = "已读取编辑后的参数，正在后台重新生成脚本；界面可以继续响应。"

        def success(payload):
            self.generated_payload = payload
            self.last_failed_script = ""
            self.last_error = ""
            self._show_payload(payload)
            append_history(
                {
                    "prompt": prompt,
                    "summary": payload.get("summary", "按参数重新生成"),
                    "parameters": payload.get("parameters", {}),
                    "expected_objects": payload.get("expected_objects", []),
                    "model": self._provider_label(),
                    "status": "regenerated-with-parameters",
                    "task_id": payload.get("task_id", ""),
                }
            )
            self._refresh_history()
            self._set_status("已按参数重新生成：脚本已自动校验通过，可以执行。")

        def failed(error):
            self._set_status("按参数重新生成失败：\n{}".format(self._format_request_error(error)))

        self._start_background_task(
            "按参数重新生成",
            task_message,
            request_callback,
            success,
            failed,
            button=self.regenerate_params_button,
        )

    def _refresh_history(self):
        if not hasattr(self, "history_box"):
            return
        items = load_recent_history(limit=20)
        if not items:
            self.history_box.setPlainText("暂无历史记录。")
            return
        lines = []
        for item in reversed(items):
            lines.append(
                "[{created_at}] {status} | {model}\n{summary}\n".format(
                    created_at=item.get("created_at", ""),
                    status=item.get("status", ""),
                    model=item.get("model", ""),
                    summary=item.get("summary", ""),
                )
            )
        self.history_box.setPlainText("\n".join(lines))


def _find_existing_panel(main_window):
    return main_window.findChild(QtWidgets.QDockWidget, PANEL_OBJECT_NAME)


def show_ai_panel():
    main_window = Gui.getMainWindow()
    panel = _find_existing_panel(main_window)
    if panel is None:
        panel = AIPanel(main_window)
        main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, panel)
    panel.show()
    panel.raise_()
    return panel
