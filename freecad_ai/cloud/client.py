"""Minimal client for the FreeCADAI SaaS plugin API."""

import json
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

    def verify(self):
        return self._post("/api/v1/plugin/auth/verify", {"project_id": self.project_id}, timeout=20)

    def templates(self):
        return self._get("/api/v1/plugin/templates", timeout=30)

    def generate(self, prompt, context, modeling_mode):
        return self._post(
            "/api/v1/plugin/generate",
            {
                "prompt": prompt,
                "context": context,
                "modeling_mode": modeling_mode,
                "project_id": self.project_id,
            },
        )

    def repair(self, prompt, context, failed_script, error_text, modeling_mode):
        return self._post(
            "/api/v1/plugin/repair",
            {
                "prompt": prompt,
                "context": context,
                "failed_script": failed_script,
                "error_text": error_text,
                "modeling_mode": modeling_mode,
                "project_id": self.project_id,
            },
        )

    def regenerate(self, prompt, context, parameters_text, modeling_mode):
        return self._post(
            "/api/v1/plugin/regenerate",
            {
                "prompt": prompt,
                "context": context,
                "parameters": parameters_text,
                "modeling_mode": modeling_mode,
                "project_id": self.project_id,
            },
        )

    def execution_report(self, report):
        return self._post("/api/v1/plugin/execution-reports", report, timeout=20)

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
