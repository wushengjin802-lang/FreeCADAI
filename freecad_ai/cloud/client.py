"""Minimal client for the FreeCADAI SaaS plugin API."""

import json
import time
import urllib.error
import urllib.request

from freecad_ai.llm.client import LLMClientError


class CloudClientError(RuntimeError):
    pass


class FreeCADAICloudClient:
    """Call the FreeCADAI SaaS plugin API using only Python stdlib."""

    def __init__(self, base_url, api_key, project_id="", timeout=90):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.project_id = project_id.strip()
        self.timeout = timeout
        self.poll_timeout = 900
        self.poll_interval = 2.0
        self.on_task_submitted = None
        self.should_cancel = None

    def verify(self):
        return self._post("/api/v1/plugin/auth/verify", {"project_id": self.project_id}, timeout=20)

    def templates(self):
        return self._get("/api/v1/plugin/templates", timeout=30)

    def generate(self, prompt, context, modeling_mode):
        return self._submit_and_wait(self.submit_generate(prompt, context, modeling_mode))

    def submit_generate(self, prompt, context, modeling_mode):
        return self._post(
            "/api/v1/plugin/generate/submit",
            {
                "prompt": prompt,
                "context": context,
                "modeling_mode": modeling_mode,
                "project_id": self.project_id,
            },
            timeout=20,
        )

    def repair(self, prompt, context, failed_script, error_text, modeling_mode):
        return self._submit_and_wait(self.submit_repair(prompt, context, failed_script, error_text, modeling_mode))

    def submit_repair(self, prompt, context, failed_script, error_text, modeling_mode):
        return self._post(
            "/api/v1/plugin/repair/submit",
            {
                "prompt": prompt,
                "context": context,
                "failed_script": failed_script,
                "error_text": error_text,
                "modeling_mode": modeling_mode,
                "project_id": self.project_id,
            },
            timeout=20,
        )

    def regenerate(self, prompt, context, parameters_text, modeling_mode):
        return self._submit_and_wait(self.submit_regenerate(prompt, context, parameters_text, modeling_mode))

    def submit_regenerate(self, prompt, context, parameters_text, modeling_mode):
        return self._post(
            "/api/v1/plugin/regenerate/submit",
            {
                "prompt": prompt,
                "context": context,
                "parameters": parameters_text,
                "modeling_mode": modeling_mode,
                "project_id": self.project_id,
            },
            timeout=20,
        )

    def _old_generate_payload(self, prompt, context, modeling_mode):
        return {
            "prompt": prompt,
            "context": context,
            "modeling_mode": modeling_mode,
            "project_id": self.project_id,
        }

    def execution_report(self, report):
        return self._post("/api/v1/plugin/execution-reports", report, timeout=20)

    def task_status(self, task_id):
        return self._get("/api/v1/plugin/tasks/{}".format(int(task_id)), timeout=20)

    def cancel_task(self, task_id):
        return self._post("/api/v1/plugin/tasks/{}/cancel".format(int(task_id)), {}, timeout=20)

    def retry_task(self, task_id):
        return self._post("/api/v1/plugin/tasks/{}/retry".format(int(task_id)), {}, timeout=20)

    def _submit_and_wait(self, submitted):
        task_id = submitted.get("task_id")
        if not task_id:
            raise CloudClientError("Cloud task submission did not return task_id: {}".format(submitted))
        if self.on_task_submitted:
            self.on_task_submitted(task_id)
        deadline = time.time() + self.poll_timeout
        last_status = submitted.get("status", "queued")
        while time.time() < deadline:
            if self.should_cancel and self.should_cancel():
                self.cancel_task(task_id)
                raise CloudClientError("Cloud task canceled by user. task_id={}".format(task_id))
            status = self.task_status(task_id)
            last_status = status.get("status", last_status)
            if last_status == "succeeded":
                return status
            if last_status in {"failed", "canceled"}:
                detail = status.get("error_message") or status.get("message") or "Task {}".format(last_status)
                raise CloudClientError("Cloud task {}: {}".format(last_status, detail))
            time.sleep(self.poll_interval)
        raise CloudClientError("Cloud task polling timed out after {} seconds. task_id={}, last_status={}".format(self.poll_timeout, task_id, last_status))

    def account_login(self, username, password):
        return self._post_public(
            "/api/v1/plugin/account/login",
            {"username": username, "password": password},
            timeout=20,
        )

    def account_workspaces(self, account_token):
        return self._get_with_token("/api/v1/plugin/account/workspaces", account_token, timeout=30)

    def bind_workspace(self, account_token, workspace_id, key_name="FreeCAD Plugin Key"):
        return self._post_with_token(
            "/api/v1/plugin/account/bind-workspace",
            {"workspace_id": int(workspace_id), "key_name": key_name},
            account_token,
            timeout=30,
        )

    def _post(self, path, payload, timeout=None):
        if not self.base_url:
            raise CloudClientError("SaaS Base URL is required.")
        if not self.api_key:
            raise CloudClientError("SaaS API Key is required.")

        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CloudClientError("Cloud HTTP {}: {}".format(exc.code, detail))
        except Exception as exc:
            raise CloudClientError(str(exc))

    def _post_public(self, path, payload, timeout=None):
        if not self.base_url:
            raise CloudClientError("SaaS Base URL is required.")
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._open_json(request, timeout or self.timeout)

    def _post_with_token(self, path, payload, token, timeout=None):
        if not self.base_url:
            raise CloudClientError("SaaS Base URL is required.")
        if not token:
            raise CloudClientError("Account token is required.")
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._open_json(request, timeout or self.timeout)

    def _get_with_token(self, path, token, timeout=None):
        if not self.base_url:
            raise CloudClientError("SaaS Base URL is required.")
        if not token:
            raise CloudClientError("Account token is required.")
        request = urllib.request.Request(
            self.base_url + path,
            headers={"Authorization": "Bearer " + token},
            method="GET",
        )
        return self._open_json(request, timeout or self.timeout)

    def _get(self, path, timeout=None):
        if not self.base_url:
            raise CloudClientError("SaaS Base URL is required.")
        if not self.api_key:
            raise CloudClientError("SaaS API Key is required.")
        request = urllib.request.Request(
            self.base_url + path,
            headers={"Authorization": "Bearer " + self.api_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CloudClientError("Cloud HTTP {}: {}".format(exc.code, detail))
        except Exception as exc:
            raise CloudClientError(str(exc))

    def _open_json(self, request, timeout):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CloudClientError("Cloud HTTP {}: {}".format(exc.code, detail))
        except Exception as exc:
            raise CloudClientError(str(exc))


def format_cloud_error(exc):
    text = str(exc)
    if isinstance(exc, LLMClientError):
        text = str(exc)
    if "HTTP 401" in text or "HTTP 403" in text:
        return "云端鉴权失败：请检查 SaaS API Key 是否正确、是否已启用。\n\n原始错误：\n{}".format(text)
    if "HTTP 404" in text:
        return "云端接口不存在：请检查 SaaS Base URL 是否填写为服务根地址。\n\n原始错误：\n{}".format(text)
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "云端请求超时：请检查网络或稍后重试。\n\n原始错误：\n{}".format(text)
    return text
