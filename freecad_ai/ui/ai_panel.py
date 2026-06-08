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
        self._task_thread = None
        self._task_worker = None
        self._task_success_handler = None
        self._task_error_handler = None
        self._running_button = None
        self._running_button_text = ""
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

        title = QtWidgets.QLabel("AI 智能工作台 - 阶段 4")
        title.setStyleSheet("font-weight: 600; font-size: 15px;")
        root.addWidget(title)

        description = QtWidgets.QLabel(
            "支持本地直连或云端 SaaS 生成脚本、自动校验、自动修复，并在当前 FreeCAD 文档中执行。"
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
        self.generate_button.clicked.connect(self._generate_script)
        action_row.addWidget(self.generate_button)

        self.execute_button = QtWidgets.QPushButton("执行脚本")
        self.execute_button.clicked.connect(self._execute_script)
        action_row.addWidget(self.execute_button)

        self.repair_button = QtWidgets.QPushButton("调用 LLM 修复脚本")
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
        self.service_mode_combo.addItem("云端 SaaS 服务", "cloud")
        current_mode = self.config.get("service_mode", "local")
        index = self.service_mode_combo.findData(current_mode)
        if index >= 0:
            self.service_mode_combo.setCurrentIndex(index)
        mode_form.addRow("服务模式", self.service_mode_combo)
        layout.addLayout(mode_form)

        layout.addWidget(self._section_title("本地 LLM API 连接设置"))
        form = QtWidgets.QFormLayout()
        self.base_url_input = QtWidgets.QLineEdit(self.config.get("base_url", ""))
        self.api_key_input = QtWidgets.QLineEdit(self.config.get("api_key", ""))
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.model_input = QtWidgets.QLineEdit(self.config.get("model", ""))
        self.temperature_input = QtWidgets.QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(float(self.config.get("temperature", 0.1)))

        form.addRow("Base URL", self.base_url_input)
        form.addRow("API Key", self.api_key_input)
        form.addRow("Model", self.model_input)
        form.addRow("Temperature", self.temperature_input)
        layout.addLayout(form)

        layout.addWidget(self._section_title("云端 SaaS 连接设置"))
        cloud_form = QtWidgets.QFormLayout()
        self.cloud_base_url_input = QtWidgets.QLineEdit(self.config.get("cloud_base_url", ""))
        self.cloud_api_key_input = QtWidgets.QLineEdit(self.config.get("cloud_api_key", ""))
        self.cloud_api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.cloud_project_id_input = QtWidgets.QLineEdit(self.config.get("cloud_project_id", ""))
        self.cloud_sync_history_checkbox = QtWidgets.QCheckBox("执行后回传结果")
        self.cloud_sync_history_checkbox.setChecked(bool(self.config.get("cloud_sync_history", True)))
        cloud_form.addRow("SaaS Base URL", self.cloud_base_url_input)
        cloud_form.addRow("SaaS API Key", self.cloud_api_key_input)
        cloud_form.addRow("Project ID", self.cloud_project_id_input)
        cloud_form.addRow("云端同步", self.cloud_sync_history_checkbox)
        layout.addLayout(cloud_form)

        self.save_settings_button = QtWidgets.QPushButton("保存设置")
        self.save_settings_button.clicked.connect(self._save_settings)
        layout.addWidget(self.save_settings_button)

        layout.addWidget(self._section_title("设置说明"))
        note = QtWidgets.QLabel(
            "本地 Base URL 示例：https://api.openai.com/v1。云端 SaaS Base URL 示例：http://127.0.0.1:8000。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
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
            "service_mode": self.service_mode_combo.currentData() or "local",
            "base_url": self.base_url_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
            "model": self.model_input.text().strip(),
            "temperature": self.temperature_input.value(),
            "cloud_base_url": self.cloud_base_url_input.text().strip(),
            "cloud_api_key": self.cloud_api_key_input.text().strip(),
            "cloud_project_id": self.cloud_project_id_input.text().strip(),
            "cloud_sync_history": self.cloud_sync_history_checkbox.isChecked(),
        }

    def _save_settings(self):
        self.config = save_config(self._current_settings())
        mode_name = "云端 SaaS 服务" if self._using_cloud() else "本地直连 LLM"
        self._set_status("设置已保存。下一次生成会使用：{}。".format(mode_name))

    def _set_busy(self, busy):
        for button in (
            self.generate_button,
            self.execute_button,
            self.repair_button,
            self.local_script_button,
            self.context_button,
            self.regenerate_params_button,
            self.apply_template_button,
        ):
            if button is self.repair_button:
                button.setEnabled((not busy) and bool(self.last_failed_script and self.last_error))
            else:
                button.setEnabled(not busy)

    def _start_button_spinner(self, button):
        if button is None:
            return
        self._stop_button_spinner()
        self._running_button = button
        self._running_button_text = button.text()
        self._spinner_index = 0
        button.setText("{} {}".format(self._spinner_frames[self._spinner_index], self._running_button_text))
        QtWidgets.QApplication.processEvents()
        self._spinner_timer.start()

    def _update_running_button(self):
        if self._running_button is None:
            self._spinner_timer.stop()
            return
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self._running_button.setText("{} {}".format(self._spinner_frames[self._spinner_index], self._running_button_text))

    def _stop_button_spinner(self):
        if self._spinner_timer.isActive():
            self._spinner_timer.stop()
        if self._running_button is not None:
            self._running_button.setText(self._running_button_text)
        self._running_button = None
        self._running_button_text = ""
        QtWidgets.QApplication.processEvents()

    def _start_background_task(self, name, message, callback, on_success, on_error=None, button=None):
        if self._task_thread is not None:
            self._set_status("已有任务正在运行，请等它完成后再开始新的任务。")
            return
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
        prompt = get_template_prompt(name)
        if not prompt:
            self._set_status("请选择一个模板。")
            return
        self.prompt_box.setPlainText(prompt)
        self.prompt_box.moveCursor(QtGui.QTextCursor.End)
        if name.startswith("二维草图"):
            self.modeling_mode_combo.setCurrentIndex(1)
        self._set_status("已套用模板：{}。可以直接生成，也可以继续修改需求。".format(name))

    def _modeling_mode(self):
        return self.modeling_mode_combo.currentData() or "3d_solid"

    def _using_cloud(self):
        return self.config.get("service_mode", "local") == "cloud"

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
        prompt = self.prompt_box.toPlainText().strip()
        if not prompt:
            self.status.setPlainText("请输入建模需求。")
            return

        self._save_settings()
        self._clear_generation_outputs("已清空旧结果。正在整理需求、读取当前模型上下文，并准备调用 LLM...")
        try:
            context = collect_context()
        except Exception:
            self._set_status("读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_generate(prompt, context)
            task_message = "上下文已读取，正在后台请求云端 SaaS 生成 FreeCAD Python 脚本；界面可以继续操作。"
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
        return FreeCADAICloudClient(
            self.config.get("cloud_base_url", ""),
            self.config.get("cloud_api_key", ""),
            self.config.get("cloud_project_id", ""),
        )

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
        try:
            prompt = self.prompt_box.toPlainText().strip()
            context = collect_context()
        except Exception:
            self._set_status("自动修复前读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_repair(prompt, context, failed_script, error)
            task_message = "正在后台请求云端 SaaS 生成修复脚本，FreeCAD 界面可以继续操作。"
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
            task_message = "正在后台请求云端 SaaS 修复失败脚本，FreeCAD 界面可以继续操作。"
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
        self.summary_box.clear()
        self.script_box.clear()
        try:
            context = collect_context()
        except Exception:
            self._set_status("读取上下文失败：\n{}".format(traceback.format_exc()))
            return
        if self._using_cloud():
            request_callback = lambda: self._request_cloud_regenerate(prompt, context, parameters_text)
            task_message = "已读取编辑后的参数，正在后台请求云端 SaaS 重新生成脚本。"
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
