"""Minimal OpenAI-compatible chat completions client."""

import json
import time
import urllib.error
import urllib.request


class LLMClientError(RuntimeError):
    pass


def format_llm_error(exc):
    """Return a user-friendly Chinese message for common API failures."""
    text = str(exc)
    if "HTTP 429" in text and ("insufficient_quota" in text or "exceeded your current quota" in text):
        return (
            "LLM 服务返回 429：当前 API Key 额度不足或账号账单不可用。\n\n"
            "处理建议：\n"
            "1. 登录服务商控制台检查余额、套餐、账单和调用额度。\n"
            "2. 如果使用 OpenAI，请确认该 API Key 所属项目仍有可用额度。\n"
            "3. 也可以在“设置”页切换到 DeepSeek、通义千问或私有 OpenAI-compatible 网关。\n"
            "4. 暂时没有可用额度时，可点击“本地示例脚本”继续测试脚本预览、校验和 FreeCAD 执行链路。\n\n"
            "原始错误：\n{}".format(text)
        )
    if "HTTP 401" in text or "invalid_api_key" in text:
        return "LLM 鉴权失败：请检查 API Key 是否正确、是否属于当前 Base URL。\n\n原始错误：\n{}".format(text)
    if "HTTP 404" in text:
        return "LLM 接口或模型不存在：请检查 Base URL 是否以 /v1 结尾，以及 Model 名称是否正确。\n\n原始错误：\n{}".format(text)
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "LLM 请求超时：请检查网络、Base URL 或稍后重试。\n\n原始错误：\n{}".format(text)
    if (
        "unexpected_eof_while_reading" in text.lower()
        or "eof occurred in violation of protocol" in text.lower()
        or "ssl:" in text.lower()
        or "connection reset" in text.lower()
    ):
        return (
            "LLM HTTPS/SSL 连接被中途断开。\n\n"
            "常见原因：\n"
            "1. Base URL 写错，例如缺少 /v1，或把 https:// 写给了只支持 http:// 的本地网关。\n"
            "2. 代理、VPN、公司网络或安全软件拦截了 TLS 连接。\n"
            "3. 当前模型服务网关临时不稳定。\n"
            "4. 使用了不兼容 OpenAI /chat/completions 的地址。\n\n"
            "建议先检查：\n"
            "- OpenAI 官方地址应为：https://api.openai.com/v1\n"
            "- 本地 Ollama/Open WebUI/私有网关如果只开了 HTTP，请用 http://...\n"
            "- 浏览器或 curl 是否能访问同一个 Base URL。\n"
            "- 暂时关闭代理/VPN 后再试，或换一个 OpenAI-compatible 服务。\n\n"
            "原始错误：\n{}".format(text)
        )
    return str(exc)


class OpenAICompatibleClient:
    """Call an OpenAI-compatible `/chat/completions` endpoint."""

    def __init__(self, base_url, api_key, model, timeout=90):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout = timeout

    def chat(self, messages, temperature=0.1):
        return self.chat_with_usage(messages, temperature=temperature)["content"]

    def chat_with_usage(self, messages, temperature=0.1):
        if not self.base_url:
            raise LLMClientError("Base URL is required.")
        if not self.api_key:
            raise LLMClientError("API Key is required.")
        if not self.model:
            raise LLMClientError("Model is required.")

        url = self.base_url + "/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
            "response_format": {"type": "json_object"},
        }

        try:
            return self._post_chat_with_retry(url, body)
        except LLMClientError as exc:
            if "HTTP 400" not in str(exc) or "response_format" not in str(exc):
                raise
            fallback_body = dict(body)
            fallback_body.pop("response_format", None)
            return self._post_chat_with_retry(url, fallback_body)

    def _post_chat_with_retry(self, url, body):
        last_error = None
        for attempt in range(3):
            try:
                return self._post_chat(url, body)
            except LLMClientError as exc:
                last_error = exc
                text = str(exc).lower()
                transient = (
                    "unexpected_eof_while_reading" in text
                    or "eof occurred in violation of protocol" in text
                    or "connection reset" in text
                    or "remote end closed connection" in text
                    or "timed out" in text
                    or "timeout" in text
                )
                if not transient or attempt == 2:
                    raise
                time.sleep(0.6 * (attempt + 1))
        raise last_error

    def _post_chat(self, url, body):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMClientError("LLM HTTP {}: {}".format(exc.code, detail))
        except Exception as exc:
            raise LLMClientError(str(exc))

        try:
            return {
                "content": payload["choices"][0]["message"]["content"],
                "usage": payload.get("usage") or {},
            }
        except (KeyError, IndexError, TypeError):
            raise LLMClientError("Unexpected LLM response: {}".format(payload))
